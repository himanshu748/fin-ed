"""Narrow, sourced Indian investment-tax specialist agent."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterable, Callable
from datetime import date
from typing import Literal, cast

from livekit.agents import (
    Agent,
    ModelSettings,
    RunContext,
    ToolError,
    function_tool,
    llm,
)

from fined.agent import (
    SessionState,
    _commit_agent_activation,
    classify_prohibited_agent_intent,
    render_prohibited_agent_refusal,
)
from fined.agent_status_bridge import (
    AgentStatus,
    AgentStatusBridge,
)
from fined.handoff import (
    TaxLocale,
    build_handoff_chat_context,
    classify_tax_route,
    create_pending_handoff,
    is_direct_handoff_request,
    normalize_tax_locale,
    validate_handoff_agreement,
)
from fined.speech import strip_markdown_links_for_speech
from fined.tax_rules import TaxRuleRegistry

logger = logging.getLogger(__name__)

FinEdFactory = Callable[[llm.ChatContext, bool], Agent]
TaxRuleCategory = Literal[
    "capital_assets",
    "debt_instruments",
    "derivatives_stt",
    "dividends",
    "equity_oriented_fund",
    "listed_bonds",
    "physical_gold",
    "share_buyback",
    "tax_year_transition",
]
TaxRuleCategoryInput = Literal[
    "capital_assets",
    "debt_instruments",
    "derivatives_stt",
    "dividends",
    "equity_oriented_fund",
    "listed_bonds",
    "physical_gold",
    "share_buyback",
    "tax_year_transition",
    "ETF",
    "shares",
    "bonds",
]

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CALENDAR_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_CANONICAL_TAX_CATEGORIES = frozenset(
    {
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
)
_CATEGORY_ALIASES: dict[str, TaxRuleCategory] = {
    "etf": "equity_oriented_fund",
    "shares": "equity_oriented_fund",
}
_CATEGORY_LABELS: dict[str, str] = {
    "capital_assets": "capital assets",
    "debt_instruments": "debt instruments",
    "derivatives_stt": "equity derivatives",
    "dividends": "dividends",
    "equity_oriented_fund": "listed equity shares and equity-oriented funds",
    "listed_bonds": "listed bonds",
    "physical_gold": "physical gold",
    "share_buyback": "share buybacks",
    "tax_year_transition": "tax-year transition",
}
_EXPLICIT_LISTED_BONDS = re.compile(r"(?<!\w)listed[\s-]+bonds?(?!\w)", re.IGNORECASE)
_EXPLICIT_EQUITY_ASSET = re.compile(
    r"(?<!\w)(?:equity(?:[\s-]+shares?)?|shares?|stocks?)(?!\w)",
    re.IGNORECASE,
)
_ASSET_TERMS = tuple(
    re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
    for term in (
        "share",
        "shares",
        "stock",
        "stocks",
        "equity",
        "etf",
        "mutual fund",
        "gold",
        "bond",
        "bonds",
        "debt fund",
        "futures",
        "option",
        "options",
        "derivative",
        "buyback",
        "dividend",
        "dividends",
    )
)
_GENERIC_TAX_EVENT = re.compile(
    r"(?<!\w)(?:capital[\s-]+gains?|stt|securities transaction tax)(?!\w)",
    re.IGNORECASE,
)
_UNVERIFIED_RESULT: dict[str, object] = {
    "verified": False,
    "rules": [],
    "message": (
        "I cannot verify an applicable current rule from the official registry. "
        "Please check with a qualified Indian tax professional."
    ),
}
_UNKNOWN_CATEGORY_RESULT: dict[str, object] = {
    "verified": False,
    "clarification_required": True,
    "rules": [],
    "message": "Please clarify the supported investment category before lookup.",
}


def build_taxed_prompt() -> str:
    """Build TaxEd's complete specialist-only instruction boundary."""
    return """IDENTITY
- You are TaxEd, an Indian investment-tax education specialist.
- You explain only general verified rules from the local official-source registry.

SOURCE CONTRACT
- Call search_tax_rules before every substantive tax explanation.
- Use only records returned with verified true. Never fill a gap from model memory.
- State the investment category, tax event and applicability date.
- Use the human-readable investment category returned by the tool.
- Copy official_source exactly as Markdown in the visible transcript. Never output a raw URL.
- If a lookup is unverified, stale or unsupported, say you cannot verify the rule.
- Ask which asset or investment category applies before searching a generic capital-gains or STT question.

BOUNDARIES
- Never calculate personal tax liability or provide personalised tax advice.
- Never file, prepare, submit or amend an ITR.
- Never help evade tax, conceal income or fabricate a deduction.
- Never recommend a tax-saving transaction, product or scheme.
- Refuse every paper order and every real order. Never buy, sell, prepare, confirm or execute a trade.
- Do not use market quotes, broker access, memory, outbound calls or human-help tools.

HANDOFF
- For a non-tax learning question, call offer_fined_return and speak its exact permission question.
- Call handoff_to_fined after the learner agrees to that connection question.

STYLE
- Keep speech concise and conversational.
- Name the official source naturally but never speak a URL.
- Do not use an Oxford comma or an em dash."""


class TaxEdAssistant(Agent):
    def __init__(
        self,
        *,
        registry: TaxRuleRegistry,
        fined_factory: FinEdFactory | None,
        status_bridge: AgentStatusBridge,
        tts: object,
        chat_ctx: llm.ChatContext | None = None,
        today: Callable[[], date] = date.today,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.registry = registry
        self.fined_factory = fined_factory
        self.status_bridge = status_bridge
        self._today = today
        self._monotonic_clock = monotonic_clock
        self.locale = _locale_from_context(chat_ctx)
        agent_options: dict[str, object] = {
            "instructions": build_taxed_prompt(),
            "tts": tts,
        }
        if chat_ctx is not None:
            agent_options["chat_ctx"] = chat_ctx
        super().__init__(**agent_options)  # type: ignore[arg-type]

    async def on_enter(self) -> None:
        state = self.session.userdata
        _commit_agent_activation(state, "taxed")
        await self.session.say(_taxed_introduction(self.locale))
        try:
            await self.status_bridge.publish(AgentStatus.taxed())
        except Exception:
            logger.warning("Agent status update was unavailable.")
        self.session.generate_reply(
            instructions=(
                "Answer the transferred tax question. Call search_tax_rules before "
                "stating any substantive rule and abstain if it is unverified."
            )
        )

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        model_settings: ModelSettings,
    ):
        """Refuse personal tax and all order actions before provider inference."""
        user_text = _latest_user_text(chat_ctx)
        prohibited_intent = classify_prohibited_agent_intent(user_text)
        if prohibited_intent is not None:
            yield render_prohibited_agent_refusal(prohibited_intent)
            return
        async for chunk in Agent.default.llm_node(
            self, chat_ctx, tools, model_settings
        ):
            yield chunk

    def tts_node(
        self,
        text: AsyncIterable[str],
        model_settings: ModelSettings,
    ):
        return Agent.default.tts_node(
            self,
            strip_markdown_links_for_speech(text),
            model_settings,
        )

    @function_tool(name="search_tax_rules")
    async def search_tax_rules(
        self,
        context: RunContext[SessionState],
        query: str,
        as_of_date: str | None,
        category: TaxRuleCategoryInput | None,
    ) -> dict[str, object]:
        """Return at most four verified official registry records."""
        if not isinstance(query, str) or not query.strip() or len(query) > 1_000:
            raise ToolError("A bounded tax-rule query is required.")
        current_date = self._today()
        requested_date = _strict_iso_date(as_of_date, current_date)
        parsed_date = (
            requested_date
            if as_of_date is None
            or str(requested_date.year) in _CALENDAR_YEAR.findall(query)
            else current_date
        )
        try:
            safe_category = _normalize_tax_category(category, query=query)
        except ValueError:
            logger.info("Tax rule lookup rejected an unsupported category")
            return dict(_UNKNOWN_CATEGORY_RESULT)
        if safe_category is None and _generic_event_needs_asset(query):
            logger.info("Tax rule lookup requires an asset category")
            return {
                "verified": False,
                "clarification_required": True,
                "rules": [],
                "message": (
                    "Which asset or investment category is this capital-gains "
                    "or STT question about?"
                ),
            }
        try:
            rules = self.registry.search(
                query.strip(),
                as_of_date=parsed_date,
                category=safe_category,
                limit=4,
                checked_on=self._today(),
            )
        except Exception:
            logger.warning(
                "Tax rule registry search failed; category=%s as_of_date=%s",
                safe_category,
                parsed_date.isoformat(),
            )
            return dict(_UNVERIFIED_RESULT)
        if not rules:
            logger.info(
                "Tax rule lookup returned no matches; category=%s as_of_date=%s",
                safe_category,
                parsed_date.isoformat(),
            )
            return dict(_UNVERIFIED_RESULT)
        logger.info(
            "Tax rule lookup verified %d record(s); category=%s as_of_date=%s",
            len(rules),
            safe_category,
            parsed_date.isoformat(),
        )
        context.userdata.mark_analytics_success("tax_rule_delivered")
        return {
            "verified": True,
            "rules": [_format_tax_rule_for_agent(rule) for rule in rules[:4]],
        }

    @function_tool(name="offer_fined_return")
    async def offer_fined_return(
        self,
        context: RunContext[SessionState],
        language: str,
    ) -> dict[str, object] | Agent:
        """Offer FinEd for the newest non-tax learning request."""
        if self.fined_factory is None:
            raise ToolError("FinEd is unavailable right now.")
        message = _latest_user_message(self.chat_ctx)
        if message is None:
            raise ToolError("A current learning question is required before a return.")
        question = message.text_content or ""
        prohibited_intent = classify_prohibited_agent_intent(question)
        if prohibited_intent is not None:
            raise ToolError(render_prohibited_agent_refusal(prohibited_intent))
        if classify_tax_route(question) != "fined":
            raise ToolError("This question remains within TaxEd's tax scope.")
        try:
            pending = create_pending_handoff(
                direction="fined",
                question=question,
                locale=language,
                question_turn_id=message.id,
                now=self._monotonic_clock(),
            )
        except Exception:
            raise ToolError("FinEd return is unavailable right now.") from None
        if is_direct_handoff_request(question, "fined"):
            transferred_context = build_handoff_chat_context(self.chat_ctx, pending)
            try:
                fined = self.fined_factory(transferred_context, True)
                await context.session.say(_connecting_fined_message(pending.locale))
            except Exception:
                raise ToolError(
                    "FinEd is unavailable right now. Please try again."
                ) from None
            context.userdata.pending_handoff = None
            return fined
        context.userdata.pending_handoff = pending
        return {"offered": True, "permission": pending.permission_text}

    @function_tool(name="handoff_to_fined")
    async def handoff_to_fined(
        self,
        context: RunContext[SessionState],
    ) -> Agent:
        """Return a FinEd agent after the learner agrees to the connection."""
        pending = context.userdata.pending_handoff
        if (
            self.fined_factory is None
            or pending is None
            or pending.direction != "fined"
            or not validate_handoff_agreement(
                pending, self.chat_ctx, now=self._monotonic_clock()
            )
        ):
            raise ToolError(
                "Please answer the FinEd connection question before switching."
            )
        transferred_context = build_handoff_chat_context(self.chat_ctx, pending)
        try:
            fined = self.fined_factory(transferred_context, True)
            await context.session.say(_connecting_fined_message(pending.locale))
        except Exception:
            raise ToolError(
                "FinEd is unavailable right now. Please try again."
            ) from None
        context.userdata.pending_handoff = None
        return fined


def _latest_user_message(chat_ctx: llm.ChatContext) -> llm.ChatMessage | None:
    for item in reversed(chat_ctx.items):
        if isinstance(item, llm.ChatMessage) and item.role == "user":
            return item
    return None


def _latest_user_text(chat_ctx: llm.ChatContext) -> str:
    message = _latest_user_message(chat_ctx)
    return message.text_content or "" if message is not None else ""


def _strict_iso_date(value: str | None, default: date) -> date:
    if value is None:
        return default
    if not isinstance(value, str) or _ISO_DATE.fullmatch(value) is None:
        raise ToolError("as_of_date must use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError("as_of_date must use YYYY-MM-DD.") from None


def _normalize_tax_category(
    category: TaxRuleCategoryInput | str | None,
    *,
    query: str,
) -> TaxRuleCategory | None:
    if category is None:
        return None
    if not isinstance(category, str):
        raise ValueError("unknown tax category")
    normalized = category.strip().casefold()
    if normalized == "capital_assets" and _EXPLICIT_EQUITY_ASSET.search(query):
        return "equity_oriented_fund"
    if normalized in _CANONICAL_TAX_CATEGORIES:
        return cast(TaxRuleCategory, normalized)
    if normalized == "bonds":
        if _EXPLICIT_LISTED_BONDS.search(query) is not None:
            return "listed_bonds"
        raise ValueError("ambiguous bonds category")
    if normalized in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[normalized]
    raise ValueError("unknown tax category")


def _format_tax_rule_for_agent(rule: object) -> dict[str, object]:
    public = rule.to_public_dict()  # type: ignore[attr-defined]
    category = str(public.get("investment_category", ""))
    return {
        "rule_id": public.get("rule_id"),
        "topic": public.get("topic"),
        "investment_category": _CATEGORY_LABELS.get(
            category, category.replace("_", " ")
        ),
        "plain_explanation": public.get("plain_explanation"),
        "effective_from": public.get("effective_from"),
        "effective_to": public.get("effective_to"),
        "applicability_note": public.get("applicability_note"),
        "last_verified_on": public.get("last_verified_on"),
        "review_due_on": public.get("review_due_on"),
        "official_source": public.get("source_link"),
    }


def _generic_event_needs_asset(query: str) -> bool:
    normalized = query.casefold()
    return _GENERIC_TAX_EVENT.search(normalized) is not None and not any(
        pattern.search(normalized) for pattern in _ASSET_TERMS
    )


def _locale_from_context(chat_ctx: llm.ChatContext | None) -> TaxLocale:
    if chat_ctx is None:
        return "en-IN"
    for message in chat_ctx.messages():
        content = message.text_content or ""
        if content.startswith("Response locale: "):
            return normalize_tax_locale(content.removeprefix("Response locale: "))
    return "en-IN"


def _taxed_introduction(locale: TaxLocale) -> str:
    if locale == "hi-IN":
        return "मैं TaxEd हूँ। मैं आधिकारिक स्रोतों से निवेश कर के सामान्य नियम समझाऊँगी।"
    if locale == "hi-LATN":
        return (
            "Main TaxEd hoon. Main official sources se investment tax rules samjhaungi."
        )
    return "I am TaxEd. I explain general investment-tax rules from official sources."


def _connecting_fined_message(locale: TaxLocale) -> str:
    if locale == "hi-IN":
        return "मैं आपको अब FinEd से वापस जोड़ रही हूँ।"
    if locale == "hi-LATN":
        return "Main aapko ab FinEd se wapas connect kar rahi hoon."
    return "I am connecting you back to FinEd now."
