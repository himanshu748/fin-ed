from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from livekit import rtc
from livekit.agents import (
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    cli,
    metrics,
    room_io,
    tokenize,
)
from livekit.plugins import deepgram, google, murf, noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from fined.agent import (
    FinEdAssistant,
    ParticipantProfile,
    SessionState,
    build_system_prompt,
    parse_participant_profile,
)
from fined.chat_model import create_gemini_llm
from fined.knowledge.embeddings import GeminiEmbedder
from fined.knowledge.index import KnowledgeIndex, UnavailableKnowledgeRetriever
from fined.market_data.angel_one import create_market_data_provider
from fined.memory import SQLiteCallerMemoryStore
from fined.murf_falcon import install_current_websocket_serializer
from fined.paper_trading import LiveKitPaperTradingBridge
from fined.paper_trading.models import decode_paper_order_result

logger = logging.getLogger("agent")

KNOWLEDGE_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "data" / "knowledge" / "generated"
)
MEMORY_DATABASE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "memory" / "fined.sqlite3"
)
KNOWLEDGE_UNAVAILABLE_WARNING = (
    "Knowledge index is unavailable; starting in evidence-unavailable mode"
)
PAPER_ORDER_RESULT_METHOD = "fined.paper.v1.order_result"
PAPER_RESULT_ACK = '{"version":1,"paper":true,"acknowledged":true}'
PAPER_RESULT_SENTENCE = "The browser confirmed the simulated paper result."
MEMORY_GREETING_INSTRUCTIONS = (
    "Look up this caller's saved learning memory, then greet them. "
    "If found, use their name and one relevant saved learning fact. "
    "If not found, introduce FinEd Saathi as an Indian markets "
    "learning companion and ask what they want to understand. "
    "State that this is education, not investment advice."
)
MEMORY_LOOKUP_TOOL_CHOICE = {
    "type": "function",
    "function": {"name": "lookup_caller_memory"},
}

# Preserve the starter's evaluation import and prompt seams.
Assistant = FinEdAssistant
SYSTEM_PROMPT = build_system_prompt(ParticipantProfile())

server = AgentServer()


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
    await ctx.connect()
    participant = await ctx.wait_for_participant()
    profile = parse_participant_profile(participant.metadata)

    ctx.log_context_fields = {
        "room": ctx.room.name,
        "mode": profile.learning_mode.value,
    }

    load_dotenv(".env.local")
    memory_path = Path(os.getenv("FINED_MEMORY_DB_PATH", str(MEMORY_DATABASE_PATH)))
    memory_store = SQLiteCallerMemoryStore(memory_path)
    embedding_client = genai.Client()
    client_closed = False
    paper_result_rpc_registered = False
    paper_result_rpc_unregistered = False

    async def close_client_once() -> None:
        nonlocal client_closed
        if client_closed:
            return
        client_closed = True
        await _close_embedding_client(embedding_client)

    def unregister_paper_result_rpc_once() -> None:
        nonlocal paper_result_rpc_unregistered
        if not paper_result_rpc_registered or paper_result_rpc_unregistered:
            return
        paper_result_rpc_unregistered = True
        try:
            ctx.room.local_participant.unregister_rpc_method(PAPER_ORDER_RESULT_METHOD)
        except Exception:
            logger.warning("Paper result RPC cleanup failed")

    try:
        install_current_websocket_serializer()
        embedder = GeminiEmbedder(embedding_client)
        index = _load_knowledge_retriever(KNOWLEDGE_DIRECTORY, embedder)
        paper_trading = LiveKitPaperTradingBridge(
            ctx.room.local_participant, participant.identity
        )
        state = SessionState(
            profile=profile,
            retriever=index,
            market_data=create_market_data_provider(),
            paper_trading=paper_trading,
            caller_id=participant.identity,
            memory_store=memory_store,
        )
        session = AgentSession[SessionState](
            userdata=state,
            stt=deepgram.STT(
                model="nova-3",
                language="multi",
                endpointing_ms=100,
            ),
            llm=create_gemini_llm(google.LLM),
            tts=murf.TTS(
                voice="Nikhil",
                style="Conversational",
                model="falcon-2",
                locale="en-IN",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True,
            ),
            turn_detection=MultilingualModel(),
            vad=ctx.proc.userdata["vad"],
            preemptive_generation=True,
        )

        usage = metrics.UsageCollector()

        @session.on("metrics_collected")
        def on_metrics(event: MetricsCollectedEvent) -> None:
            metrics.log_metrics(event.metrics, logger=logger)
            usage.collect(event.metrics)
            _log_latency_components(event.metrics)

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

        ctx.room.local_participant.register_rpc_method(
            PAPER_ORDER_RESULT_METHOD, on_paper_order_result
        )
        paper_result_rpc_registered = True

        async def on_shutdown(reason: str) -> None:
            del reason
            try:
                logger.info("Agent usage summary: %s", usage.get_summary())
            finally:
                try:
                    unregister_paper_result_rpc_once()
                finally:
                    await close_client_once()

        ctx.add_shutdown_callback(on_shutdown)

        await session.start(
            agent=FinEdAssistant(profile),
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
        await session.generate_reply(
            instructions=MEMORY_GREETING_INSTRUCTIONS,
            tool_choice=MEMORY_LOOKUP_TOOL_CHOICE,
        )
    except BaseException:
        try:
            unregister_paper_result_rpc_once()
        finally:
            await close_client_once()
        raise


if __name__ == "__main__":
    cli.run_app(server)
