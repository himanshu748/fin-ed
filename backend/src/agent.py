from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from time import monotonic
from typing import Protocol

from dotenv import load_dotenv
from google import genai
from livekit import api, rtc
from livekit.agents import (
    AgentServer,
    AgentSession,
    AgentStateChangedEvent,
    ErrorEvent,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    cli,
    inference,
    llm,
    metrics,
    room_io,
    tokenize,
)
from livekit.plugins import deepgram, google, murf, noise_cancellation, silero

from fined.agent import (
    FinEdAssistant,
    FinEdTTSLocaleController,
    ParticipantProfile,
    SessionState,
    build_greeting,
    build_system_prompt,
    parse_participant_profile,
)
from fined.agent_status_bridge import (
    AGENT_STATUS_QUERY_RPC_METHOD,
    AGENT_STATUS_QUERY_UNAVAILABLE_MESSAGE,
    LiveKitAgentStatusBridge,
    decode_agent_status_query,
    encode_active_agent_status,
)
from fined.call_analytics import (
    AgentTalkTimeTracker,
    CallAnalyticsInput,
    SQLiteCallAnalyticsStore,
    new_call_id,
)
from fined.chat_model import create_gemini_llm
from fined.escalation_bridge import LiveKitHumanHelpBridge
from fined.escalation_callback import LiveKitHumanHelpCallback
from fined.escalations import SQLiteEscalationStore
from fined.handoff import normalize_tax_locale
from fined.knowledge.embeddings import GeminiEmbedder
from fined.knowledge.index import KnowledgeIndex, UnavailableKnowledgeRetriever
from fined.market_data.angel_one import create_market_data_provider
from fined.market_data.models import QuoteRequest
from fined.market_data.provider import MarketDataUnavailableError
from fined.memory import CallerMemory, SQLiteCallerMemoryStore
from fined.murf_falcon import install_current_websocket_serializer
from fined.outbound import (
    OUTBOUND_RECIPIENT_JOIN_TIMEOUT_SECONDS,
    PAPER_PRACTICE_REMINDER,
    OutboundConfigurationError,
    build_outbound_greeting,
    parse_outbound_metadata,
)
from fined.paper_trading import CallPaperTradingBridge, LiveKitPaperTradingBridge
from fined.paper_trading.models import (
    PaperHoldingQuote,
    PaperHoldingQuoteRequest,
    decode_paper_holding_quote_request,
    decode_paper_order_result,
    paper_holding_quotes_rpc_payload,
)
from fined.tax_rules import load_packaged_tax_rules
from fined.taxed_agent import TaxEdAssistant

logger = logging.getLogger("agent")

KNOWLEDGE_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "data" / "knowledge" / "generated"
)
MEMORY_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "memory" / "fined.sqlite3"
)
ESCALATION_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "escalations" / "fined.sqlite3"
)
ANALYTICS_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "analytics" / "fined.sqlite3"
)
ANALYTICS_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "analytics" / "public-summary.json"
)
KNOWLEDGE_UNAVAILABLE_WARNING = (
    "Knowledge index is unavailable; starting in evidence-unavailable mode"
)
TAX_REGISTRY_UNAVAILABLE_WARNING = (
    "Tax rule registry is unavailable; starting FinEd without TaxEd"
)
TAXED_TTS_CLEANUP_WARNING = "TaxEd voice cleanup failed"
PAPER_ORDER_RESULT_METHOD = "fined.paper.v1.order_result"
PAPER_HOLDING_QUOTES_METHOD = "fined.paper.v1.quote_holdings"
PAPER_RESULT_ACK = '{"version":1,"paper":true,"acknowledged":true}'
PAPER_RESULT_SENTENCE = "The browser confirmed the simulated paper result."
LLM_UNAVAILABLE_SENTENCE = (
    "The language model is temporarily busy. Please wait a moment, then ask again."
)


class _JobOwnedTaxEdTTS(Protocol):
    def prewarm(self) -> None: ...

    async def aclose(self) -> None: ...


class _TaxEdTTSManager:
    """Own each per-handoff TaxEd voice for one LiveKit job."""

    def __init__(self) -> None:
        self._instances: dict[int, _JobOwnedTaxEdTTS] = {}
        self._cleanup_tasks: set[asyncio.Task[None]] = set()

    def track(self, taxed_tts: _JobOwnedTaxEdTTS) -> None:
        self._instances[id(taxed_tts)] = taxed_tts

    async def close(self, taxed_tts: _JobOwnedTaxEdTTS) -> None:
        owned_tts = self._instances.pop(id(taxed_tts), None)
        if owned_tts is None:
            return
        try:
            await owned_tts.aclose()
        except Exception:
            logger.warning(TAXED_TTS_CLEANUP_WARNING)

    def close_soon(self, taxed_tts: _JobOwnedTaxEdTTS) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self.close(taxed_tts))
        self._cleanup_tasks.add(task)
        task.add_done_callback(self._cleanup_tasks.discard)

    async def close_all(self) -> None:
        pending_cleanup = tuple(self._cleanup_tasks)
        if pending_cleanup:
            await asyncio.gather(*pending_cleanup)
        for taxed_tts in tuple(self._instances.values()):
            await self.close(taxed_tts)


class _JobTaxEdAssistant(TaxEdAssistant):
    """TaxEd agent whose LiveKit exit hook releases its job-owned voice."""

    def __init__(
        self,
        *,
        close_taxed_tts: Callable[[], Awaitable[None]],
        **kwargs: object,
    ) -> None:
        self._close_taxed_tts = close_taxed_tts
        super().__init__(**kwargs)  # type: ignore[arg-type]

    async def on_exit(self) -> None:
        try:
            await super().on_exit()
        finally:
            await self._close_taxed_tts()


class _LiveKitOutboundCallControl:
    """Speak a short goodbye, then remove the isolated SIP room."""

    def __init__(
        self,
        session: AgentSession[SessionState],
        ctx: JobContext,
        participant_identity: str,
    ) -> None:
        self._session = session
        self._ctx = ctx
        self._participant_identity = participant_identity

    async def end_call(self) -> None:
        try:
            await asyncio.wait_for(
                self._session.say("Okay. I will end this call now."), timeout=2.0
            )
        finally:
            try:
                await self._ctx.api.room.remove_participant(
                    api.RoomParticipantIdentity(
                        room=self._ctx.room.name,
                        identity=self._participant_identity,
                    )
                )
            finally:
                self._ctx.shutdown("outbound recipient requested stop")


def build_caller_greeting(
    profile: ParticipantProfile,
    memory: CallerMemory | None,
) -> str:
    """Build the first turn after the server-side memory lookup.

    Keeping this lookup outside the LLM avoids a provider tool round trip before
    the first audio while preserving the same consented-memory behavior.
    """
    if memory is None:
        return build_greeting(profile)
    fact = next(
        (
            memory.facts[key]
            for key in (
                "learning_goal",
                "topic_covered",
                "experience_level",
                "preferred_explanation_style",
            )
            if key in memory.facts
        ),
        "Indian market concepts",
    )
    if memory.language_preference == "hindi":
        return (
            f"फिर से स्वागत है, {memory.name}। "
            f"पिछली बार आपका सीखने का लक्ष्य था: {fact}। "
            "यह केवल शिक्षा है, निवेश सलाह नहीं। "
            "आज आप क्या समझना चाहेंगे?"
        )
    return (
        f"Welcome back, {memory.name}. "
        f"Your saved learning goal is {fact}. "
        "This is education, not investment advice. "
        "What would you like to understand today?"
    )


# Preserve the starter's evaluation import and prompt seams.
Assistant = FinEdAssistant
SYSTEM_PROMPT = build_system_prompt(ParticipantProfile())

server = AgentServer(num_idle_processes=1)


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


def _load_knowledge_retriever(
    directory: Path, embedder: GeminiEmbedder
) -> KnowledgeIndex | UnavailableKnowledgeRetriever:
    if not os.path.lexists(directory / "current"):
        logger.warning(KNOWLEDGE_UNAVAILABLE_WARNING)
        return UnavailableKnowledgeRetriever()
    return KnowledgeIndex.load(directory, embedder)


async def _close_embedding_client(client: genai.Client) -> None:
    try:
        await client.aio.aclose()
    except Exception:
        logger.warning("Embedding client cleanup failed")


def _log_latency_components(metric: metrics.AgentMetrics) -> None:
    if isinstance(metric, metrics.EOUMetrics):
        logger.info(
            "Turn latency components: end_of_utterance_delay=%.3f "
            "transcription_delay=%.3f user_turn_completion_delay=%.3f",
            metric.end_of_utterance_delay,
            metric.transcription_delay,
            metric.on_user_turn_completed_delay,
        )
    elif isinstance(metric, metrics.TTSMetrics):
        logger.info("TTS latency component: ttfb=%.3f", metric.ttfb)


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext) -> None:
    analytics_started_at = datetime.now(UTC)
    analytics_call_id = new_call_id()
    await ctx.connect()
    outbound_reminder = parse_outbound_metadata(
        getattr(getattr(ctx, "job", None), "metadata", None)
    )
    if outbound_reminder is None:
        participant = await ctx.wait_for_participant()
        profile = parse_participant_profile(participant.metadata)
    else:
        try:
            participant = await asyncio.wait_for(
                ctx.wait_for_participant(),
                timeout=OUTBOUND_RECIPIENT_JOIN_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning("Outbound recipient did not join the reminder room")
            ctx.shutdown("outbound recipient unavailable")
            return
        profile = ParticipantProfile(outbound_reminder.learning_mode)

    ctx.log_context_fields = {
        "room": ctx.room.name,
        "mode": profile.learning_mode.value,
        "call_type": "outbound" if outbound_reminder is not None else "browser",
    }

    load_dotenv(".env.local")
    memory_store = (
        SQLiteCallerMemoryStore(
            Path(os.getenv("FINED_MEMORY_DB_PATH", str(MEMORY_DATABASE_PATH)))
        )
        if outbound_reminder is None
        else None
    )
    escalation_store = (
        SQLiteEscalationStore(
            Path(os.getenv("FINED_ESCALATION_DB_PATH", str(ESCALATION_DATABASE_PATH)))
        )
        if outbound_reminder is None
        else None
    )
    analytics_store = SQLiteCallAnalyticsStore(
        Path(os.getenv("FINED_ANALYTICS_DB_PATH", str(ANALYTICS_DATABASE_PATH))),
        snapshot_path=Path(
            os.getenv("FINED_ANALYTICS_SNAPSHOT_PATH", str(ANALYTICS_SNAPSHOT_PATH))
        ),
    )
    embedding_client = genai.Client()
    client_closed = False
    registered_browser_rpc_methods: list[str] = []
    browser_rpcs_unregistered = False
    analytics_recorded = False
    llm_fallback_task: asyncio.Task[None] | None = None
    taxed_tts_manager = _TaxEdTTSManager()

    async def close_client_once() -> None:
        nonlocal client_closed
        if client_closed:
            return
        client_closed = True
        await _close_embedding_client(embedding_client)

    def unregister_browser_rpcs_once() -> None:
        nonlocal browser_rpcs_unregistered
        if browser_rpcs_unregistered:
            return
        browser_rpcs_unregistered = True
        for method in reversed(registered_browser_rpc_methods):
            try:
                ctx.room.local_participant.unregister_rpc_method(method)
            except Exception:
                logger.warning("Browser RPC cleanup failed for %s", method)

    try:
        install_current_websocket_serializer()
        embedder = GeminiEmbedder(embedding_client)
        index = _load_knowledge_retriever(KNOWLEDGE_DIRECTORY, embedder)
        status_bridge = None
        tax_registry = None
        if outbound_reminder is None:
            status_bridge = LiveKitAgentStatusBridge(
                ctx.room.local_participant, participant.identity
            )
            try:
                tax_registry = load_packaged_tax_rules()
            except Exception:
                logger.warning(TAX_REGISTRY_UNAVAILABLE_WARNING)
        state = SessionState(
            profile=profile,
            retriever=index,
            caller_id=participant.identity,
            outbound_reminder=outbound_reminder,
        )
        state.market_data = create_market_data_provider()
        if outbound_reminder is None:
            assert memory_store is not None
            assert escalation_store is not None
            state.memory_store = memory_store
            state.escalation_store = escalation_store
            state.human_help = LiveKitHumanHelpBridge(
                ctx.room.local_participant, participant.identity
            )
            with suppress(OutboundConfigurationError):
                state.human_help_callback = LiveKitHumanHelpCallback.from_environment(
                    os.environ
                )
            state.paper_trading = LiveKitPaperTradingBridge(
                ctx.room.local_participant, participant.identity
            )
        elif outbound_reminder == PAPER_PRACTICE_REMINDER:
            state.paper_trading = CallPaperTradingBridge()

        fined_stt = deepgram.STT(
            model="nova-3",
            language="multi",
            endpointing_ms=100,
        )
        fined_llm = create_gemini_llm(google.LLM)
        fined_tts = murf.TTS(
            voice="Nikhil",
            style="Conversational",
            model="falcon-2",
            locale="en-IN",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        )
        fined_tts_locale_controller = FinEdTTSLocaleController(fined_tts)

        if tax_registry is not None:

            def create_fined(
                chat_ctx: llm.ChatContext | None = None,
                announce_entry: bool = False,
            ) -> FinEdAssistant:
                return FinEdAssistant(
                    profile,
                    chat_ctx=chat_ctx,
                    taxed_factory=create_taxed,
                    status_bridge=status_bridge,
                    tts_locale_controller=fined_tts_locale_controller,
                    announce_entry=announce_entry,
                )

            def create_taxed(locale: str, chat_ctx: llm.ChatContext) -> TaxEdAssistant:
                taxed_tts = murf.TTS(
                    voice="en-IN-anusha",
                    style="Conversational",
                    model="falcon-2",
                    locale=normalize_tax_locale(locale),
                    tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                    text_pacing=True,
                )
                taxed_tts_manager.track(taxed_tts)
                try:
                    taxed_tts.prewarm()
                    return _JobTaxEdAssistant(
                        registry=tax_registry,
                        chat_ctx=chat_ctx,
                        fined_factory=create_fined,
                        status_bridge=status_bridge,
                        tts=taxed_tts,
                        close_taxed_tts=lambda: taxed_tts_manager.close(taxed_tts),
                    )
                except BaseException:
                    taxed_tts_manager.close_soon(taxed_tts)
                    raise

        session = AgentSession[SessionState](
            userdata=state,
            stt=fined_stt,
            llm=fined_llm,
            tts=fined_tts,
            turn_detection=inference.TurnDetector(version="v1-mini"),
            vad=ctx.proc.userdata["vad"],
            preemptive_generation=True,
        )
        if outbound_reminder is not None:
            state.outbound_call_control = _LiveKitOutboundCallControl(
                session,
                ctx,
                participant.identity,
            )
        if tax_registry is not None:
            initial_agent = create_fined()
        else:
            initial_agent = FinEdAssistant(
                profile,
                outbound_reminder=outbound_reminder,
                outbound_call_control=state.outbound_call_control,
                status_bridge=status_bridge,
                tts_locale_controller=fined_tts_locale_controller,
            )

        usage = metrics.UsageCollector()
        talk_time_tracker = AgentTalkTimeTracker(clock=monotonic)

        @session.on("metrics_collected")
        def on_metrics(event: MetricsCollectedEvent) -> None:
            metrics.log_metrics(event.metrics, logger=logger)
            usage.collect(event.metrics)
            _log_latency_components(event.metrics)

        @session.on("error")
        def on_error(event: ErrorEvent) -> None:
            nonlocal llm_fallback_task
            error = event.error
            if (
                getattr(error, "type", None) != "llm_error"
                or getattr(error, "recoverable", True)
                or (llm_fallback_task is not None and not llm_fallback_task.done())
            ):
                return

            async def speak_llm_fallback() -> None:
                try:
                    await session.say(LLM_UNAVAILABLE_SENTENCE)
                except Exception:
                    logger.warning("LLM fallback speech failed")

            llm_fallback_task = asyncio.create_task(speak_llm_fallback())

        @session.on("agent_state_changed")
        def on_agent_state_changed(event: AgentStateChangedEvent) -> None:
            talk_time_tracker.on_agent_state_changed(
                event.old_state,
                event.new_state,
                state.active_agent_name,
            )

        async def on_paper_order_result(data: rtc.RpcInvocationData) -> str:
            if data.caller_identity != participant.identity:
                raise rtc.RpcError(2001, "Paper result caller is not authorized.")
            try:
                result = decode_paper_order_result(data.payload)
            except Exception:
                raise rtc.RpcError(2002, "Invalid paper result.") from None
            draft = state.pending_paper_drafts.get(result.draft_id)
            if (
                draft is None
                or draft.expires_at <= datetime.now(UTC)
                or result.side != draft.side
                or result.trading_symbol != draft.trading_symbol
                or result.quantity != draft.quantity
                or result.fill_price_paise != draft.price_paise
            ):
                raise rtc.RpcError(2002, "Invalid paper result.")
            del state.pending_paper_drafts[result.draft_id]
            await session.say(PAPER_RESULT_SENTENCE)
            return PAPER_RESULT_ACK

        async def on_agent_status_query(data: rtc.RpcInvocationData) -> str:
            try:
                if data.caller_identity != participant.identity:
                    raise ValueError
                decode_agent_status_query(data.payload)
                return encode_active_agent_status(state.active_agent_name)
            except Exception:
                raise rtc.RpcError(
                    2002, AGENT_STATUS_QUERY_UNAVAILABLE_MESSAGE
                ) from None

        async def on_paper_holding_quotes(data: rtc.RpcInvocationData) -> str:
            if data.caller_identity != participant.identity:
                raise rtc.RpcError(2001, "Paper quote caller is not authorized.")
            try:
                holdings = decode_paper_holding_quote_request(data.payload)
            except Exception:
                raise rtc.RpcError(2002, "Invalid paper quote request.") from None

            async def quote_holding(
                holding: PaperHoldingQuoteRequest,
            ) -> PaperHoldingQuote | None:
                try:
                    quote = await state.market_data.get_quote(
                        QuoteRequest(
                            exchange=holding.exchange,
                            symbol_token=holding.symbol_token,
                        )
                    )
                except (MarketDataUnavailableError, ValueError):
                    return None
                price_paise = int(
                    (quote.last_traded_price * Decimal("100")).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                )
                return PaperHoldingQuote(
                    exchange=holding.exchange,
                    symbol_token=holding.symbol_token,
                    trading_symbol=quote.trading_symbol,
                    price_paise=price_paise,
                    quote_time=quote.exchange_time,
                    provider=quote.provider,
                )

            quote_results = await asyncio.gather(
                *(quote_holding(holding) for holding in holdings)
            )
            quotes = tuple(quote for quote in quote_results if quote is not None)
            return json.dumps(
                paper_holding_quotes_rpc_payload(quotes),
                separators=(",", ":"),
                ensure_ascii=False,
            )

        if outbound_reminder is None:
            ctx.room.local_participant.register_rpc_method(
                AGENT_STATUS_QUERY_RPC_METHOD, on_agent_status_query
            )
            registered_browser_rpc_methods.append(AGENT_STATUS_QUERY_RPC_METHOD)
            ctx.room.local_participant.register_rpc_method(
                PAPER_ORDER_RESULT_METHOD, on_paper_order_result
            )
            registered_browser_rpc_methods.append(PAPER_ORDER_RESULT_METHOD)
            ctx.room.local_participant.register_rpc_method(
                PAPER_HOLDING_QUOTES_METHOD, on_paper_holding_quotes
            )
            registered_browser_rpc_methods.append(PAPER_HOLDING_QUOTES_METHOD)

        async def on_shutdown(reason: str) -> None:
            nonlocal analytics_recorded
            if not analytics_recorded:
                analytics_recorded = True
                failure_type = state.analytics_failure_type
                if state.analytics_success_condition is None and failure_type is None:
                    if "unavailable" in reason.casefold():
                        failure_type = "no_response"
                    elif "error" in reason.casefold():
                        failure_type = "system_error"
                    else:
                        failure_type = "no_completed_action"
                try:
                    talk_times = talk_time_tracker.close()
                    analytics_store.record(
                        CallAnalyticsInput(
                            call_id=analytics_call_id,
                            channel="sip"
                            if outbound_reminder is not None
                            else "browser",
                            started_at=analytics_started_at,
                            ended_at=datetime.now(UTC),
                            success_condition=state.analytics_success_condition,
                            failure_type=failure_type,
                            fined_talk_seconds=talk_times["fined_talk_seconds"],
                            taxed_talk_seconds=talk_times["taxed_talk_seconds"],
                            handoff_count=state.agent_handoff_count,
                        )
                    )
                except Exception:
                    logger.warning("Call analytics recording failed")
            try:
                logger.info("Agent usage summary: %s", usage.get_summary())
            finally:
                try:
                    unregister_browser_rpcs_once()
                finally:
                    try:
                        await taxed_tts_manager.close_all()
                    finally:
                        await close_client_once()

        ctx.add_shutdown_callback(on_shutdown)

        await session.start(
            agent=initial_agent,
            room=ctx.room,
            room_options=room_io.RoomOptions(
                audio_input=room_io.AudioInputOptions(
                    noise_cancellation=lambda params: (
                        noise_cancellation.BVCTelephony()
                        if params.participant.kind
                        == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                        else noise_cancellation.BVC()
                    ),
                ),
            ),
        )
        if outbound_reminder is not None:
            await session.say(build_outbound_greeting(outbound_reminder))
        else:
            assert memory_store is not None
            try:
                caller_memory = memory_store.lookup(participant.identity)
            except Exception:
                logger.warning("Caller memory lookup failed before greeting")
                caller_memory = None
            await session.say(build_caller_greeting(profile, caller_memory))
    except BaseException:
        try:
            unregister_browser_rpcs_once()
        finally:
            try:
                await taxed_tts_manager.close_all()
            finally:
                await close_client_once()
        raise


if __name__ == "__main__":
    cli.run_app(server)
