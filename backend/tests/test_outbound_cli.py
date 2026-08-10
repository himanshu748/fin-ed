from __future__ import annotations

from types import SimpleNamespace

import pytest

import outbound_call
from fined.outbound import OUTBOUND_REMINDER_PAPER_PRACTICE, OutboundConfigurationError


def _environment(**changes: str) -> dict[str, str]:
    values = {
        "SIP_OUTBOUND_TRUNK_ID": "ST_abc12345",
        "FINED_OUTBOUND_AGENT_NAME": "my-agent",
    }
    values.update(changes)
    return values


def test_command_configuration_accepts_only_private_server_environment() -> None:
    # Catches a browser-side or missing-trunk configuration path.
    request = outbound_call.build_request_from_environment(
        "+919876543210", _environment()
    )

    assert request.phone_number == "+919876543210"
    assert request.sip_trunk_id == "ST_abc12345"
    assert request.agent_name == "my-agent"
    assert request.reminder.name == OUTBOUND_REMINDER_PAPER_PRACTICE

    with pytest.raises(OutboundConfigurationError):
        outbound_call.build_request_from_environment(
            "+919876543210", _environment(SIP_OUTBOUND_TRUNK_ID="")
        )


def test_outbound_client_disables_transport_failover_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches the LiveKit client's default replay behavior duplicating a dial.
    options: dict[str, object] = {}

    class FakeClient:
        pass

    def client_constructor(**kwargs: object) -> FakeClient:
        options.update(kwargs)
        return FakeClient()

    monkeypatch.setattr(outbound_call.api, "LiveKitAPI", client_constructor)

    assert isinstance(outbound_call.create_outbound_client(), FakeClient)
    assert options == {"failover": False}


def test_private_command_requires_operator_consent_acknowledgement_and_tty_input() -> (
    None
):
    # Catches recipient numbers entering shell history, CI logs, or a call without attestation.
    parser = outbound_call._argument_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--dry-run"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--consent-confirmed", "--to", "+919876543210"])


def test_recipient_prompt_refuses_noninteractive_shells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Catches a real recipient number leaking through automation or shell history.
    monkeypatch.setattr(outbound_call.sys.stdin, "isatty", lambda: False)

    with pytest.raises(OutboundConfigurationError, match="private terminal"):
        outbound_call.read_recipient_phone_number()


@pytest.mark.asyncio
async def test_dry_run_never_initializes_a_livekit_client_or_reveals_number() -> None:
    # Catches a supposedly safe preview that can place a real outbound call.
    request = outbound_call.build_request_from_environment(
        "+919876543210", _environment()
    )
    client_created = False

    def client_factory() -> object:
        nonlocal client_created
        client_created = True
        raise AssertionError("dry run must not create a network client")

    result = await outbound_call.run_operator_call(
        request,
        dry_run=True,
        client_factory=client_factory,
    )

    assert client_created is False
    assert result.exit_code == 0
    assert result.message == "Dry run passed. No phone call was made."
    assert request.phone_number not in result.message


class _FakeDispatchService:
    async def create_dispatch(self, request: object) -> SimpleNamespace:
        return SimpleNamespace(id="dispatch-123")

    async def delete_dispatch(self, dispatch_id: str, room_name: str) -> None:
        del dispatch_id, room_name


class _FakeSIPService:
    async def create_sip_participant(
        self, request: object, *, timeout: float | None = None
    ) -> SimpleNamespace:
        del request, timeout
        return SimpleNamespace(sip_call_id="call-123")


class _FakeLiveKitClient:
    def __init__(self) -> None:
        self.agent_dispatch = _FakeDispatchService()
        self.sip = _FakeSIPService()
        self.entered = False
        self.closed = False

    async def __aenter__(self) -> _FakeLiveKitClient:
        self.entered = True
        return self

    async def __aexit__(self, *args: object) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_real_command_attempt_is_single_call_and_returns_safe_acknowledgement() -> (
    None
):
    # Catches retry loops or an operator-facing log that includes contact data.
    request = outbound_call.build_request_from_environment(
        "+919876543210", _environment()
    )
    client = _FakeLiveKitClient()

    result = await outbound_call.run_operator_call(
        request,
        dry_run=False,
        client_factory=lambda: client,
    )

    assert client.entered is True
    assert client.closed is True
    assert result.exit_code == 0
    assert result.message == "Outbound learning reminder was answered."
    assert request.phone_number not in result.message
