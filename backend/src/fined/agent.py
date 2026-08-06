"""Testable FinEd Saathi profile, prompt, and LiveKit tool contracts."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, DecimalException, InvalidOperation
from typing import Protocol

from livekit.agents import (
    Agent,
    ModelSettings,
    RunContext,
    ToolError,
    function_tool,
)

from fined.calculator import (
    BSE_GROUPS,
    DeliveryTrade,
    ScheduleConfigurationError,
    UnsupportedScheduleError,
    calculate_delivery_trade,
)
from fined.knowledge.index import SearchHit
from fined.modes import LearningMode, parse_learning_mode
from fined.speech import strip_markdown_links_for_speech

MAX_PARTICIPANT_METADATA_BYTES = 1024
MAX_SEARCH_QUERY_BYTES = 4096
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_TOPIC_NAMES = {
    LearningMode.STOCKS: "Stocks",
    LearningMode.MUTUAL_FUNDS: "Mutual Funds & SIPs",
    LearningMode.ETFS: "ETFs",
    LearningMode.GOLD: "Gold",
    LearningMode.FNO: "F&O",
    LearningMode.IPOS: "IPOs",
    LearningMode.BONDS: "Bonds",
    LearningMode.GENERAL: "Ask Anything",
}


class KnowledgeRetriever(Protocol):
    async def search(
        self,
        query: str,
        learning_mode: LearningMode,
        as_of_date: date | None = None,
        broker: str | None = None,
        top_k: int = 4,
    ) -> list[SearchHit]: ...


@dataclass(frozen=True)
class ParticipantProfile:
    learning_mode: LearningMode = LearningMode.GENERAL


@dataclass
class SessionState:
    profile: ParticipantProfile
    retriever: KnowledgeRetriever


def parse_participant_profile(metadata: str | None) -> ParticipantProfile:
    """Parse the sole allowlisted metadata field without exposing raw input."""
    default = ParticipantProfile()
    if not isinstance(metadata, str) or not metadata.strip():
        return default
    try:
        encoded = metadata.encode("utf-8")
    except UnicodeEncodeError:
        return default
    if len(encoded) > MAX_PARTICIPANT_METADATA_BYTES:
        return default
    try:
        value = json.loads(metadata)
    except (json.JSONDecodeError, TypeError):
        return default
    if not isinstance(value, dict) or set(value) != {"learning_mode"}:
        return default
    return ParticipantProfile(parse_learning_mode(value["learning_mode"]))


def build_system_prompt(profile: ParticipantProfile) -> str:
    """Build the fixed safety contract with mode-specific session context."""
    return f"""You are FinEd Saathi, a voice-first Indian financial-markets tutor.

Selected learning mode: {profile.learning_mode.value}.
The supported concepts/modes are: stocks, mutual_funds, etfs, gold, fno, ipos, bonds, general.

Safety and privacy:
- This is education only. Never provide recommendations, targets, signals, assured returns, portfolio allocation, or trade execution.
- Never ask for a broker password, PIN, OTP, full account number, or credentials.
- For F&O, clearly say it is high risk. Keep it education and simulation only; never give a live strategy or calls.

Signature fee lesson:
- Keep this exact remembered input internally for the example: Maine ₹6 mein stock liya, ₹6 mein hi bech diya, phir bhi mujhe ₹50 ka loss hua.
- Do not repeat the remembered romanized-Hindi sentence. Paraphrase its meaning entirely in the response language.
- Treat ₹50 as unresolved. The remembered historical ₹50 is not reconstructed. Do not guess or invent a scenario that matches ₹50, and never assert it as the exact current result.
- First determine where ₹50 appeared: contract-note total charges, ledger or available funds, or P&L.
- Then ask for one missing calculation input at a time: trade date, delivery versus intraday, executed buy order count, executed sell order count, sell-side DP transaction or debit count, promotion status, and any separate account or service charge.
- Contract-note or Trades & Charges rows outrank a generic estimate.
- Current standard delivery brokerage is the lower of ₹20 or 0.1% per executed order, subject to a ₹5 minimum. Never imply that every buy and sell costs ₹20 plus GST.
- Under explicit current assumptions of one executed buy order, one executed sell order, and one sell-side DP debit, a one-share ₹6 buy and ₹6 sell NSE delivery illustrates ₹5 buy brokerage, ₹5 sell brokerage, ₹20 DP charge before GST, about ₹35.41 total charges, a 590.22% fee-to-investment ratio, and ₹41.46 break-even sell price.
- Before calculation, confirm broker, delivery versus intraday, date, exchange, quantity, buy price, and sell price.
- The deterministic calculator is delivery-only. Do not call it for intraday or F&O, and do not fabricate those charges.
- Use the calculator for Angel One delivery arithmetic and never reconstruct fee math in the LLM.

Grounding and response style:
- Use retrieval for factual market concepts, charges, taxes, and risks.
- Regulator and government sources outrank exchanges, which outrank broker pricing, support, and education.
- Cite concise Markdown source links in the visible transcript.
- Reply entirely in English when the user speaks English.
- Reply entirely in Hindi, written in Devanagari, when the user speaks Hindi.
- Never mix English and Hindi in one response, and never write Hindi in Latin characters.
- If the user mixes languages or their preference is unclear, ask them to choose English or Hindi using English only.
- Keep spoken answers concise with no spoken URLs.
- If current official support is missing, say it could not be verified instead of guessing.
"""


def build_greeting(profile: ParticipantProfile) -> str:
    """Return a brief, mode-aware greeting for the post-start speech turn."""
    topic = _TOPIC_NAMES[profile.learning_mode]
    greeting = (
        f"Hello! This is the Financial Services track. Today we can learn about {topic}. "
        "Ask your first question in English or Hindi."
    )
    if profile.learning_mode is LearningMode.FNO:
        greeting += (
            " F&O is high risk. This mode is for education and simulation only, "
            "not live trading calls."
        )
    return greeting


class FinEdAssistant(Agent):
    def __init__(self, profile: ParticipantProfile | None = None) -> None:
        self.profile = profile or ParticipantProfile()
        super().__init__(instructions=build_system_prompt(self.profile))

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

    @function_tool(name="search_market_knowledge")
    async def search_market_knowledge(
        self,
        context: RunContext[SessionState],
        query: str,
        as_of_date: str | None = None,
        broker: str | None = None,
    ) -> dict[str, object]:
        """Search the curated market corpus for current, attributable evidence.

        Args:
            query: The market concept, charge, tax, or risk question.
            as_of_date: Optional applicability date in strict YYYY-MM-DD form.
            broker: Optional supported Angel One spelling for broker-specific facts.
        """
        if not isinstance(query, str) or not query.strip():
            raise ToolError("Please provide a market question to search for.")
        try:
            query_size = len(query.encode("utf-8"))
        except UnicodeEncodeError:
            raise ToolError("The market question must be valid UTF-8 text.") from None
        if query_size > MAX_SEARCH_QUERY_BYTES:
            raise ToolError("The market question must be at most 4096 UTF-8 bytes.")
        parsed_date = _parse_optional_iso_date(as_of_date, "as_of_date")
        normalized_broker = _normalize_broker(broker)
        state = context.userdata
        try:
            hits = await state.retriever.search(
                query,
                learning_mode=state.profile.learning_mode,
                as_of_date=parsed_date,
                broker=normalized_broker,
                top_k=4,
            )
        except Exception:
            raise ToolError("Market knowledge is temporarily unavailable.") from None
        if not hits:
            return {
                "verified": False,
                "hits": [],
                "message": (
                    "No supported current evidence was found. Tell the user it could "
                    "not be verified and do not guess."
                ),
            }
        return {
            "verified": True,
            "hits": [_search_hit_result(hit) for hit in hits],
        }

    @function_tool(name="calculate_angel_one_trade_cost")
    async def calculate_angel_one_trade_cost(
        self,
        context: RunContext[SessionState],
        trade_date: str,
        exchange: str,
        quantity: int,
        buy_price: str,
        sell_price: str | None = None,
        demat_debit: bool = True,
        brokerage_promotion_applies: bool | None = None,
        executed_buy_orders: int = 1,
        executed_sell_orders: int = 1,
        demat_debits: int = 1,
        bse_group: str | None = None,
    ) -> dict[str, object]:
        """Calculate a schedule-backed Angel One equity-delivery estimate.

        Args:
            trade_date: Trade date in strict YYYY-MM-DD form.
            exchange: Equity exchange, exactly NSE or BSE.
            quantity: Positive share quantity.
            buy_price: Positive finite per-share buy price as decimal text.
            sell_price: Optional positive finite sell price as decimal text.
            demat_debit: Whether a sell-side demat debit applies.
            brokerage_promotion_applies: Whether the documented promotion applies.
            executed_buy_orders: Positive count of executed buy orders.
            executed_sell_orders: Positive count of executed sell orders.
            demat_debits: Positive count of sell-side demat debits.
            bse_group: Allowlisted BSE scrip group when exchange is BSE.
        """
        if context.userdata.profile.learning_mode is LearningMode.FNO:
            raise ToolError(
                "The delivery calculator is unavailable in F&O mode; use education "
                "and simulation only."
            )
        parsed_date = _parse_iso_date(trade_date, "trade_date")
        if not isinstance(exchange, str) or exchange not in {"NSE", "BSE"}:
            raise ToolError("exchange must be NSE or BSE.")
        parsed_quantity = _positive_integer(quantity, "quantity")
        parsed_buy_price = _positive_decimal(buy_price, "buy_price")
        parsed_sell_price = (
            _positive_decimal(sell_price, "sell_price")
            if sell_price is not None
            else None
        )
        if not isinstance(demat_debit, bool):
            raise ToolError("demat_debit must be true or false.")
        if brokerage_promotion_applies is not None and not isinstance(
            brokerage_promotion_applies, bool
        ):
            raise ToolError("brokerage promotion must be true, false, or omitted.")
        parsed_buy_orders = _positive_integer(
            executed_buy_orders, "executed_buy_orders"
        )
        parsed_sell_orders = _positive_integer(
            executed_sell_orders, "executed_sell_orders"
        )
        parsed_demat_debits = _positive_integer(demat_debits, "demat_debits")
        parsed_bse_group = _validate_bse_group(exchange, bse_group)

        trade = DeliveryTrade(
            trade_date=parsed_date,
            exchange=exchange,
            quantity=parsed_quantity,
            buy_price=parsed_buy_price,
            sell_price=parsed_sell_price,
            demat_debit=demat_debit,
            brokerage_promotion_applies=brokerage_promotion_applies,
            executed_buy_orders=parsed_buy_orders,
            executed_sell_orders=parsed_sell_orders,
            demat_debits=parsed_demat_debits,
            bse_group=parsed_bse_group,
        )
        try:
            breakdown = calculate_delivery_trade(trade)
        except UnsupportedScheduleError:
            raise ToolError(
                "No verified Angel One schedule covers that trade date."
            ) from None
        except ScheduleConfigurationError:
            raise ToolError("The verified charge schedule is unavailable.") from None
        except DecimalException:
            raise ToolError(
                "Trade values are outside the supported calculation range."
            ) from None
        except ValueError:
            raise ToolError("The equity-delivery inputs are not supported.") from None

        result = breakdown.to_tool_result()
        result.update(
            {
                "product": "equity_delivery",
                "applicability_status": "schedule_backed_for_trade_date",
                "estimate_status": (
                    "illustrative_estimate" if breakdown.is_estimate else "exact"
                ),
                "applicability": {
                    "broker": "Angel One",
                    "product": "equity_delivery",
                    "trade_date": parsed_date.isoformat(),
                    "exchange": exchange,
                },
                "source_links": [
                    f"[{source.title}]({source.url})"
                    for source in breakdown.schedule_sources
                ],
            }
        )
        return result


def _parse_optional_iso_date(value: str | None, field: str) -> date | None:
    if value is None:
        return None
    return _parse_iso_date(value, field)


def _parse_iso_date(value: object, field: str) -> date:
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value):
        raise ToolError(f"{field} must use YYYY-MM-DD.")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"{field} must use a valid YYYY-MM-DD date.") from None


def _normalize_broker(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolError("broker must be Angel One or omitted.")
    compact = re.sub(r"[\s._-]+", "", value.casefold())
    if compact != "angelone":
        raise ToolError("Only Angel One broker filtering is supported.")
    return "Angel One"


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ToolError(f"{field} must be a positive integer.")
    return value


def _positive_decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"{field} must be a positive finite decimal string.")
    try:
        parsed = Decimal(value.strip())
    except InvalidOperation:
        raise ToolError(f"{field} must be a positive finite decimal string.") from None
    if not parsed.is_finite() or parsed <= 0:
        raise ToolError(f"{field} must be a positive finite decimal string.")
    return parsed


def _validate_bse_group(exchange: str, value: str | None) -> str | None:
    if value is None:
        if exchange == "BSE":
            raise ToolError("BSE scrip group is required and must be allowlisted.")
        return None
    if not isinstance(value, str) or not value.strip():
        raise ToolError("BSE scrip group must be allowlisted.")
    normalized = value.strip().upper()
    if normalized not in BSE_GROUPS:
        raise ToolError("BSE scrip group must be allowlisted.")
    return normalized


def _search_hit_result(hit: SearchHit) -> dict[str, object]:
    return {
        "source_id": hit.source_id,
        "authority": hit.authority,
        "broker": hit.broker,
        "effective_from": (
            hit.effective_from.isoformat() if hit.effective_from else None
        ),
        "effective_to": hit.effective_to.isoformat() if hit.effective_to else None,
        "title": hit.title,
        "url": hit.url,
        "publisher": hit.publisher,
        "verified_on": hit.verified_on.isoformat(),
        "applicability": hit.applicability,
        "passage": hit.passage,
        "score": hit.score,
        "confidence": hit.confidence,
        "source_link": f"[{hit.title}]({hit.url})",
    }
