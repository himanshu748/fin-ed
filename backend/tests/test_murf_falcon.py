from types import SimpleNamespace

from fined.murf_falcon import build_websocket_packet


def test_falcon_packet_uses_current_nikhil_voice_and_locale_fields() -> None:
    # Catches Murf silently ignoring legacy voice_id and multi_native_locale fields.
    options = SimpleNamespace(
        voice="Nikhil",
        style="Conversational",
        speed=None,
        pitch=None,
        locale="en-IN",
        min_buffer_size=3,
        max_buffer_delay_in_ms=0,
    )

    packet = build_websocket_packet(options)

    assert packet == {
        "voice_config": {
            "voiceId": "Nikhil",
            "style": "Conversational",
            "locale": "en-IN",
        },
        "min_buffer_size": 3,
        "max_buffer_delay_in_ms": 0,
    }
    assert "voice_id" not in packet["voice_config"]
    assert "multi_native_locale" not in packet["voice_config"]
