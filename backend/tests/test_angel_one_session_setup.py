from __future__ import annotations

import json
import stat
from pathlib import Path

import httpx
import pytest

import fined.market_data.session_setup as session_setup


def login_environment() -> dict[str, str]:
    return {
        "ANGEL_ONE_API_KEY": "app-key",
        "ANGEL_ONE_CLIENT_LOCAL_IP": "192.168.1.20",
        "ANGEL_ONE_CLIENT_PUBLIC_IP": "203.0.113.10",
        "ANGEL_ONE_MAC_ADDRESS": "00:11:22:33:44:55",
    }


@pytest.mark.asyncio
async def test_create_session_access_token_posts_exact_login_contract() -> None:
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(
            200,
            json={
                "status": True,
                "message": "SUCCESS",
                "errorcode": "",
                "data": {
                    "jwtToken": "signed.jwt.token",
                    "refreshToken": "unused-refresh-token",
                    "feedToken": "unused-feed-token",
                },
            },
            request=request,
        )

    token = await session_setup.create_session_access_token(
        environment=login_environment(),
        client_code="A123456",
        pin="4321",
        totp="123456",
        transport=httpx.MockTransport(handler),
    )

    assert token == "signed.jwt.token"
    assert captured is not None
    assert captured.url == httpx.URL(session_setup.LOGIN_ENDPOINT)
    assert json.loads(captured.content) == {
        "clientcode": "A123456",
        "password": "4321",
        "totp": "123456",
    }
    assert captured.headers["x-privatekey"] == "app-key"
    assert captured.headers["x-clientlocalip"] == "192.168.1.20"
    assert captured.headers["x-clientpublicip"] == "203.0.113.10"
    assert captured.headers["x-macaddress"] == "00:11:22:33:44:55"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"message": "wrong secret-pin"}),
        httpx.Response(
            200,
            json={"status": False, "message": "totp 123456 expired"},
        ),
        httpx.Response(200, json={"status": True, "data": {}}),
    ],
)
async def test_session_login_failure_uses_one_secret_free_message(
    response: httpx.Response,
) -> None:
    with pytest.raises(session_setup.AngelOneSessionSetupError) as failure:
        await session_setup.create_session_access_token(
            environment=login_environment(),
            client_code="A123456",
            pin="secret-pin",
            totp="123456",
            transport=httpx.MockTransport(lambda request: response),
        )

    assert str(failure.value) == "Angel One authentication failed."
    assert "secret-pin" not in str(failure.value)
    assert "123456" not in str(failure.value)


def test_save_access_token_replaces_only_token_and_restricts_file(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "GOOGLE_API_KEY=keep-me\n"
        "ANGEL_ONE_ACCESS_TOKEN=old-token\n"
        "GEMINI_MODEL=gemini-2.5-flash\n",
        encoding="utf-8",
    )

    session_setup.save_access_token(env_path, "new.jwt.token")

    assert env_path.read_text(encoding="utf-8") == (
        "GOOGLE_API_KEY=keep-me\n"
        "ANGEL_ONE_ACCESS_TOKEN=new.jwt.token\n"
        "GEMINI_MODEL=gemini-2.5-flash\n"
    )
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_save_access_token_appends_when_missing(tmp_path: Path) -> None:
    env_path = tmp_path / ".env.local"
    env_path.write_text("GEMINI_MODEL=gemini-2.5-flash\n", encoding="utf-8")

    session_setup.save_access_token(env_path, "new.jwt.token")

    assert env_path.read_text(encoding="utf-8") == (
        "GEMINI_MODEL=gemini-2.5-flash\nANGEL_ONE_ACCESS_TOKEN=new.jwt.token\n"
    )


@pytest.mark.asyncio
async def test_configure_session_reads_local_headers_and_persists_only_jwt(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "ANGEL_ONE_API_KEY=app-key\n"
        "ANGEL_ONE_CLIENT_LOCAL_IP=192.168.1.20\n"
        "ANGEL_ONE_CLIENT_PUBLIC_IP=203.0.113.10\n"
        "ANGEL_ONE_MAC_ADDRESS=00:11:22:33:44:55\n",
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": True,
                "message": "SUCCESS",
                "errorcode": "",
                "data": {
                    "jwtToken": "configured.jwt.token",
                    "refreshToken": "unused-refresh-token",
                    "feedToken": "unused-feed-token",
                },
            },
            request=request,
        )

    await session_setup.configure_session_access_token(
        env_path=env_path,
        client_code="A123456",
        pin="secret-pin",
        totp="123456",
        transport=httpx.MockTransport(handler),
    )

    saved = env_path.read_text(encoding="utf-8")
    assert "ANGEL_ONE_ACCESS_TOKEN=configured.jwt.token\n" in saved
    assert "secret-pin" not in saved
    assert "123456" not in saved
    assert "A123456" not in saved


def test_local_setup_command_never_prints_prompted_secrets(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_path = tmp_path / ".env.local"
    env_path.write_text(
        "ANGEL_ONE_API_KEY=app-key\n"
        "ANGEL_ONE_CLIENT_LOCAL_IP=192.168.1.20\n"
        "ANGEL_ONE_CLIENT_PUBLIC_IP=203.0.113.10\n"
        "ANGEL_ONE_MAC_ADDRESS=00:11:22:33:44:55\n",
        encoding="utf-8",
    )
    entered = iter(("A123456", "secret-pin", "123456"))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": True,
                "message": "SUCCESS",
                "errorcode": "",
                "data": {
                    "jwtToken": "configured.jwt.token",
                    "refreshToken": "unused-refresh-token",
                    "feedToken": "unused-feed-token",
                },
            },
            request=request,
        )

    exit_code = session_setup.run_session_setup(
        env_path=env_path,
        input_fn=lambda prompt: next(entered),
        secret_fn=lambda prompt: next(entered),
        transport=httpx.MockTransport(handler),
    )

    output = capsys.readouterr()
    assert exit_code == 0
    assert output.out == "Angel One session token saved locally.\n"
    assert output.err == ""
    assert "secret-pin" not in output.out
    assert "123456" not in output.out
    assert "A123456" not in output.out
    assert "ANGEL_ONE_ACCESS_TOKEN=configured.jwt.token\n" in env_path.read_text(
        encoding="utf-8"
    )


def test_local_setup_command_cancels_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_path = tmp_path / ".env.local"
    env_path.write_text("ANGEL_ONE_API_KEY=app-key\n", encoding="utf-8")

    def cancelled(prompt: str) -> str:
        raise EOFError

    exit_code = session_setup.run_session_setup(
        env_path=env_path,
        input_fn=cancelled,
        secret_fn=cancelled,
    )

    output = capsys.readouterr()
    assert exit_code == 130
    assert output.out == ""
    assert output.err == "Angel One session setup cancelled.\n"
