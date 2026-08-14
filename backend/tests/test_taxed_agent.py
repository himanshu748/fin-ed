from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace
from typing import cast

import pytest
from livekit.agents import Agent, ModelSettings, RunContext, ToolError, llm
from livekit.agents.llm.utils import build_legacy_openai_schema

from fined.agent import ParticipantProfile, SessionState
from fined.agent_status_bridge import AgentStatus
from fined.handoff import permission_prompt
from fined.knowledge.index import SearchHit
from fined.modes import LearningMode
from fined.tax_rules import load_packaged_tax_rules
from fined.taxed_agent import TaxEdAssistant, build_taxed_prompt

_CANONICAL_TAX_CATEGORIES = {
    "capital_assets",
    "debt_instruments",
    "derivatives_stt",
    "dividends",
    "equity_oriented_fund",
    "listed_bonds",
    "physical_gold",
    "share_buyback",
    "tax_year_transition",
}


@dataclass
class FakeRetriever:
    async def search(
        self,
        query: str,
        learning_mode: LearningMode,
        as_of_date: date | None = None,
        broker: str | None = None,
        top_k: int = 4,
    ) -> list[SearchHit]:
        del query, learning_mode, as_of_date, broker, top_k
        return []


@dataclass(frozen=True)
class FakeRule:
    rule_id: str = "rule-equity-ltcg"

    def to_public_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "topic": "Equity-oriented fund long-term capital gains",
            "investment_category": "equity_oriented_fund",
            "plain_explanation": "A verified general rule explanation.",
            "effective_from": "2026-04-01",
            "effective_to": None,
            "applicability_note": "Applies from 1 April 2026.",
            "official_source_title": "Income-tax Act, 2025",
            "official_source_url": "https://www.incometaxindia.gov.in/example",
            "last_verified_on": "2026-08-14",
            "review_due_on": "2026-09-14",
            "source_link": (
                "[Income-tax Act, 2025](https://www.incometaxindia.gov.in/example)"
            ),
        }


@dataclass
class FakeRegistry:
    results: list[FakeRule] = field(default_factory=list)
    calls: list[dict[str, object]] = field(default_factory=list)
    fail: bool = False

    def search(self, query: str, **kwargs: object) -> list[FakeRule]:
        self.calls.append({"query": query, **kwargs})
        if self.fail:
            raise RuntimeError("/private/registry/path must stay hidden")
        return self.results


@dataclass
class FakeStatusBridge:
    statuses: list[AgentStatus] = field(default_factory=list)
    fail: bool = False

    async def publish(self, status: AgentStatus) -> None:
        self.statuses.append(status)
        if self.fail:
            raise RuntimeError("private UI failure")


@dataclass
class FakeSession:
    userdata: SessionState
    said: list[str] = field(default_factory=list)
    generated_instructions: list[str] = field(default_factory=list)

    async def say(self, text: str) -> None:
        self.said.append(text)

    def generate_reply(self, *, instructions: str) -> None:
        self.generated_instructions.append(instructions)


def _state() -> SessionState:
    return SessionState(
        profile=ParticipantProfile(LearningMode.GENERAL),
        retriever=FakeRetriever(),
    )


def _context(state: SessionState, session: FakeSession | None = None):
    active_session = session or FakeSession(state)
    return cast(
        RunContext[SessionState],
        SimpleNamespace(userdata=state, session=active_session),
    )


def _assistant(
    *,
    registry: FakeRegistry | None = None,
    chat_ctx: llm.ChatContext | None = None,
    fined_factory=None,
    status_bridge: FakeStatusBridge | None = None,
) -> TaxEdAssistant:
    return TaxEdAssistant(
        registry=registry or FakeRegistry(),
        fined_factory=fined_factory,
        status_bridge=status_bridge or FakeStatusBridge(),
        chat_ctx=chat_ctx,
        tts=cast(object, SimpleNamespace()),
        today=lambda: date(2026, 8, 14),
        monotonic_clock=lambda: 20.0,
    )


def test_taxed_exposes_only_three_specialist_tools() -> None:
    # Catches TaxEd inheriting market, broker, memory, help or outbound capabilities.
    assistant = _assistant()

    assert {tool.info.name for tool in assistant.tools} == {
        "search_tax_rules",
        "offer_fined_return",
        "handoff_to_fined",
    }


def test_taxed_prompt_requires_sourced_date_bound_fail_closed_answers() -> None:
    # Catches a prompt regression that allows model-memory tax answers or advice.
    prompt = build_taxed_prompt().casefold()

    for required in (
        "search_tax_rules",
        "before every substantive tax",
        "applicability date",
        "markdown",
        "official source",
        "cannot verify",
        "personal tax liability",
        "itr",
        "tax-saving",
        "paper order",
        "real order",
    ):
        assert required in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_request",
    [
        "Calculate my personal tax liability on these shares.",
        "What tax do I personally owe after selling 100 Reliance shares?",
        "What will my tax bill be after selling these shares?",
        "Please file my ITR.",
        "Can you do my ITR for me?",
        "How do I leave share gains off my ITR?",
        "मेरा ITR फाइल कर दो।",
        "मेरा आयकर रिटर्न भर दो।",
        "Mera ITR file kar do.",
        "Mera ITR bhar do.",
        "How can I conceal gains and evade tax?",
        "मेरे शेयर का मुनाफा छुपाकर टैक्स बचा दो।",
        "मेरी शेयर कमाई रिटर्न में मत दिखाओ।",
        "Mere share gains chhupa ke tax bacha do.",
        "Income mat dikhao ITR mein.",
        "Recommend a tax-saving transaction for me.",
        "Which tax-saving fund should I buy?",
        "मेरे लिए टैक्स बचाने वाला फंड चुन दो।",
        "कर बचाने के लिए कौन सी योजना लूँ?",
        "Mere liye tax-saving fund suggest karo.",
        "Tax bachane ke liye kaunsa fund loon?",
        "Prepare a paper order to buy this ETF.",
        "Put in a paper order for 10 Reliance shares.",
        "Paper trade mein 10 Reliance shares buy kar do.",
        "Place a real sell order for my shares.",
        "Buy 10 Reliance shares for me.",
        "मेरे लिए 10 रिलायंस शेयर खरीद दो।",
        "Mere liye 10 Reliance shares buy kar do.",
        "Reliance ke 10 shares le lo mere liye.",
    ],
)
async def test_taxed_refuses_prohibited_requests_before_provider_inference(
    user_request: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Catches provider inference receiving prohibited personal or trading requests.
    provider_called = False

    async def fake_llm_node(*args, **kwargs):
        nonlocal provider_called
        del args, kwargs
        provider_called = True
        yield "unsafe provider answer"

    monkeypatch.setattr(Agent.default, "llm_node", fake_llm_node)
    chat_ctx = llm.ChatContext.empty()
    chat_ctx.add_message(role="user", content=user_request)

    output = [
        chunk async for chunk in _assistant().llm_node(chat_ctx, [], ModelSettings())
    ]

    assert provider_called is False
    assert len(output) == 1
    assert "can't" in output[0].casefold()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "education_request",
    [
        "What is a tax-saving fund?",
        "How does ITR filing work?",
        "Why is hiding gains from tax illegal?",
        "How do people buy shares on an exchange?",
        "टैक्स बचाने वाला फंड क्या है?",
        "आयकर रिटर्न भरना क्या होता है?",
        "शेयर खरीदना कैसे काम करता है?",
        "Tax-saving fund kya hota hai?",
        "ITR filing kaise kaam karti hai?",
        "Paper order kaise kaam karta hai?",
    ],
)
async def test_taxed_shared_boundary_keeps_neutral_education_with_provider(
    education_request: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Catches shared classification turning neutral explanations into refusals.
    async def fake_llm_node(*args, **kwargs):
        del args, kwargs
        yield "safe educational answer"

    monkeypatch.setattr(Agent.default, "llm_node", fake_llm_node)
    chat_ctx = llm.ChatContext.empty()
    chat_ctx.add_message(role="user", content=education_request)

    output = [
        chunk async for chunk in _assistant().llm_node(chat_ctx, [], ModelSettings())
    ]

    assert output == ["safe educational answer"]


def test_tax_lookup_tool_schema_exposes_only_canonical_categories_and_aliases() -> None:
    # Catches a free-form category schema that lets the model invent taxonomy values.
    schema = build_legacy_openai_schema(_assistant().search_tax_rules)
    category_schema = schema["function"]["parameters"]["properties"]["category"]
    variants = category_schema.get("anyOf", [category_schema])
    exposed_values = {
        value for variant in variants for value in variant.get("enum", [])
    }

    assert exposed_values == _CANONICAL_TAX_CATEGORIES | {
        "ETF",
        "shares",
        "bonds",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("category", sorted(_CANONICAL_TAX_CATEGORIES))
async def test_tax_lookup_preserves_every_canonical_registry_category(
    category: str,
) -> None:
    # Catches a supported stored category being rewritten or dropped.
    registry = FakeRegistry(results=[FakeRule()])

    result = await _assistant(registry=registry).search_tax_rules(
        _context(_state()),
        query="Explain the applicable investment tax rule.",
        as_of_date="2026-08-14",
        category=category,
    )

    assert result["verified"] is True
    assert registry.calls[0]["category"] == category


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("ETF", "equity_oriented_fund"),
        ("shares", "equity_oriented_fund"),
    ],
)
async def test_tax_lookup_normalizes_public_category_aliases(
    alias: str, canonical: str
) -> None:
    # Catches a public label being sent to the registry as an unknown category.
    registry = FakeRegistry(results=[FakeRule()])

    result = await _assistant(registry=registry).search_tax_rules(
        _context(_state()),
        query="Explain the applicable investment tax rule.",
        as_of_date="2026-08-14",
        category=alias,
    )

    assert result["verified"] is True
    assert registry.calls[0]["category"] == canonical


@pytest.mark.asyncio
async def test_tax_lookup_maps_explicit_listed_bonds_alias() -> None:
    # Catches the public bonds alias selecting the packaged unlisted-debt rule.
    registry = FakeRegistry(results=[FakeRule()])

    result = await _assistant(registry=registry).search_tax_rules(
        _context(_state()),
        query="How are gains on listed bonds taxed?",
        as_of_date="2026-08-14",
        category="bonds",
    )

    assert result["verified"] is True
    assert registry.calls[0]["category"] == "listed_bonds"


@pytest.mark.asyncio
async def test_tax_lookup_requires_clarification_for_ambiguous_bonds_alias() -> None:
    # Catches a plain bonds label silently selecting listed or unlisted treatment.
    registry = FakeRegistry(results=[FakeRule()])

    result = await _assistant(registry=registry).search_tax_rules(
        _context(_state()),
        query="How are bonds taxed?",
        as_of_date="2026-08-14",
        category="bonds",
    )

    assert result["verified"] is False
    assert result["clarification_required"] is True
    assert registry.calls == []


@pytest.mark.asyncio
async def test_tax_lookup_rejects_unknown_category_before_registry_search() -> None:
    # Catches silent fallback from an invented category to a broad tax rule.
    registry = FakeRegistry(results=[FakeRule()])

    result = await _assistant(registry=registry).search_tax_rules(
        _context(_state()),
        query="How is crypto taxed?",
        as_of_date="2026-08-14",
        category="crypto",
    )

    assert result["verified"] is False
    assert result["clarification_required"] is True
    assert registry.calls == []


@pytest.mark.asyncio
async def test_natural_etf_alias_retrieves_official_equity_fund_rule() -> None:
    # Catches alias normalization that still misses the packaged ETF rule category.
    assistant = _assistant(registry=load_packaged_tax_rules())  # type: ignore[arg-type]

    result = await assistant.search_tax_rules(
        _context(_state()),
        query="How is a long-term equity ETF gain taxed?",
        as_of_date="2026-08-14",
        category="ETF",
    )

    assert result["verified"] is True
    assert [rule["rule_id"] for rule in result["rules"][:2]] == [
        "ita2025_section198_equity_ltcg",
        "ita2025_equity_fund_classification",
    ]


@pytest.mark.asyncio
async def test_listed_bonds_alias_retrieves_packaged_listed_bond_rule() -> None:
    # Catches public bonds normalization missing the official listed-bond record.
    assistant = _assistant(registry=load_packaged_tax_rules())  # type: ignore[arg-type]

    result = await assistant.search_tax_rules(
        _context(_state()),
        query="How is a listed bond gain taxed?",
        as_of_date="2026-08-14",
        category="bonds",
    )

    assert result["verified"] is True
    assert result["rules"][0]["rule_id"] == "ita2025_listed_bond_long_term_boundary"


@pytest.mark.asyncio
async def test_verified_lookup_returns_public_records_and_marks_success() -> None:
    # Catches a sourced answer failing to record the privacy-safe success condition.
    registry = FakeRegistry(results=[FakeRule()])
    state = _state()

    result = await _assistant(registry=registry).search_tax_rules(
        _context(state),
        query="How are equity ETF long-term gains taxed?",
        as_of_date="2026-08-14",
        category="equity_oriented_fund",
    )

    assert result == {"verified": True, "rules": [FakeRule().to_public_dict()]}
    assert registry.calls == [
        {
            "query": "How are equity ETF long-term gains taxed?",
            "as_of_date": date(2026, 8, 14),
            "category": "equity_oriented_fund",
            "limit": 4,
            "checked_on": date(2026, 8, 14),
        }
    ]
    assert state.analytics_success_condition == "tax_rule_delivered"


@pytest.mark.asyncio
async def test_empty_or_failed_lookup_abstains_without_marking_success() -> None:
    # Catches unverified registry output being treated as a successful tax answer.
    state = _state()
    empty = await _assistant(registry=FakeRegistry()).search_tax_rules(
        _context(state),
        query="How are listed bond gains taxed?",
        as_of_date="2026-08-14",
        category="listed_bond",
    )
    failed = await _assistant(registry=FakeRegistry(fail=True)).search_tax_rules(
        _context(state),
        query="How are listed bond gains taxed?",
        as_of_date="2026-08-14",
        category="listed_bond",
    )

    assert empty["verified"] is False
    assert failed == empty
    assert "/private/" not in str(failed)
    assert state.analytics_success_condition is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "How are capital gains taxed?",
        "What is STT?",
        "What securities transaction tax applies?",
    ],
)
async def test_generic_tax_event_requires_asset_clarification_before_lookup(
    query: str,
) -> None:
    # Catches an asset-free query searching broad rules and inventing applicability.
    registry = FakeRegistry(results=[FakeRule()])

    result = await _assistant(registry=registry).search_tax_rules(
        _context(_state()), query=query, as_of_date=None, category=None
    )

    assert result["verified"] is False
    assert result["clarification_required"] is True
    assert "asset" in str(result["message"]).casefold()
    assert registry.calls == []


@pytest.mark.asyncio
async def test_lookup_uses_injected_current_date_and_strict_iso_dates() -> None:
    # Catches stale system time or permissive date parsing selecting the wrong rule.
    registry = FakeRegistry(results=[FakeRule()])
    assistant = _assistant(registry=registry)

    await assistant.search_tax_rules(
        _context(_state()),
        query="How are equity ETF gains taxed?",
        as_of_date=None,
        category="equity_oriented_fund",
    )
    with pytest.raises(ToolError, match="YYYY-MM-DD"):
        await assistant.search_tax_rules(
            _context(_state()),
            query="How are equity ETF gains taxed?",
            as_of_date="14-08-2026",
            category="equity_oriented_fund",
        )

    assert registry.calls[0]["as_of_date"] == date(2026, 8, 14)


@pytest.mark.asyncio
async def test_taxed_return_requires_fresh_offer_and_consumes_it_once() -> None:
    # Catches a return agent being constructed without immediate explicit consent.
    source = llm.ChatContext.empty()
    source.add_message(role="user", content="What is an ETF?", id="return-question")
    created: list[tuple[llm.ChatContext, bool]] = []

    def create_fined(chat_ctx: llm.ChatContext, announce_entry: bool) -> Agent:
        created.append((chat_ctx, announce_entry))
        return Agent(instructions="returning FinEd")

    assistant = _assistant(chat_ctx=source, fined_factory=create_fined)
    state = _state()
    context = _context(state)

    with pytest.raises(ToolError, match="permission"):
        await assistant.handoff_to_fined(context)
    offer = await assistant.offer_fined_return(context, "en-IN")

    assert offer == {
        "offered": True,
        "permission": permission_prompt("fined", "en-IN"),
    }
    assert created == []

    assistant._chat_ctx.items.extend(  # type: ignore[attr-defined]
        [
            llm.FunctionCall(
                call_id="return-offer",
                name="offer_fined_return",
                arguments='{"language":"en-IN"}',
            ),
            llm.FunctionCallOutput(
                call_id="return-offer",
                name="offer_fined_return",
                output=(
                    '{"offered":true,"permission":"'
                    + permission_prompt("fined", "en-IN")
                    + '"}'
                ),
                is_error=False,
            ),
        ]
    )
    assistant._chat_ctx.add_message(  # type: ignore[attr-defined]
        role="assistant", content=permission_prompt("fined", "en-IN")
    )
    assistant._chat_ctx.add_message(role="user", content="yes")  # type: ignore[attr-defined]

    returned = await assistant.handoff_to_fined(context)

    assert isinstance(returned, Agent)
    assert len(created) == 1
    assert created[0][1] is True
    copied_text = "\n".join(
        message.text_content or "" for message in created[0][0].messages()
    )
    assert "What is an ETF?" in copied_text
    with pytest.raises(ToolError, match="permission"):
        await assistant.handoff_to_fined(context)


@pytest.mark.asyncio
async def test_taxed_on_enter_commits_agent_change_before_speech_and_status() -> None:
    # Catches analytics attribution changing late or counting duplicate activation.
    state = _state()
    state.active_agent_name = "fined"
    session = FakeSession(state)
    status_bridge = FakeStatusBridge()
    assistant = _assistant(status_bridge=status_bridge)
    assistant._activity = SimpleNamespace(session=session)  # type: ignore[attr-defined]

    await assistant.on_enter()

    assert state.active_agent_name == "taxed"
    assert state.agent_handoff_count == 1
    assert session.said
    assert len(session.generated_instructions) == 1
    assert "transferred tax question" in session.generated_instructions[0]
    assert status_bridge.statuses == [AgentStatus.taxed()]

    await assistant.on_enter()
    assert state.agent_handoff_count == 1
