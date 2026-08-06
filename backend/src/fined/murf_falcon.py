from __future__ import annotations

from typing import Any


def build_websocket_packet(options: Any) -> dict[str, Any]:
    """Serialize Murf's current Falcon 2 WebSocket voice configuration."""
    voice_config: dict[str, Any] = {}
    if options.voice:
        voice_config["voiceId"] = options.voice
    if options.style:
        voice_config["style"] = options.style
    if options.speed is not None:
        voice_config["rate"] = options.speed
    if options.pitch is not None:
        voice_config["pitch"] = options.pitch
    if options.locale:
        voice_config["locale"] = options.locale

    return {
        "voice_config": voice_config,
        "min_buffer_size": options.min_buffer_size,
        "max_buffer_delay_in_ms": options.max_buffer_delay_in_ms,
    }


def install_current_websocket_serializer() -> None:
    """Bridge LiveKit's Murf adapter to Murf's current Falcon 2 field names."""
    from livekit.plugins.murf import tts as murf_tts

    murf_tts._to_murf_websocket_pkt = build_websocket_packet
