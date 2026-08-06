from __future__ import annotations

import logging
import os
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
    build_greeting,
    build_system_prompt,
    parse_participant_profile,
)
from fined.chat_model import create_gemini_llm
from fined.knowledge.embeddings import GeminiEmbedder
from fined.knowledge.index import KnowledgeIndex, UnavailableKnowledgeRetriever
from fined.murf_falcon import install_current_websocket_serializer

logger = logging.getLogger("agent")

KNOWLEDGE_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "data" / "knowledge" / "generated"
)
KNOWLEDGE_UNAVAILABLE_WARNING = (
    "Knowledge index is unavailable; starting in evidence-unavailable mode"
)

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
    embedding_client = genai.Client()
    client_closed = False

    async def close_client_once() -> None:
        nonlocal client_closed
        if client_closed:
            return
        client_closed = True
        await _close_embedding_client(embedding_client)

    try:
        install_current_websocket_serializer()
        embedder = GeminiEmbedder(embedding_client)
        index = _load_knowledge_retriever(KNOWLEDGE_DIRECTORY, embedder)
        session = AgentSession[SessionState](
            userdata=SessionState(profile=profile, retriever=index),
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

        async def on_shutdown(reason: str) -> None:
            del reason
            try:
                logger.info("Agent usage summary: %s", usage.get_summary())
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
        await session.say(build_greeting(profile))
    except BaseException:
        await close_client_once()
        raise


if __name__ == "__main__":
    cli.run_app(server)
