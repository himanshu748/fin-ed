from __future__ import annotations

import asyncio
import getpass
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import NamedTemporaryFile

import httpx
from dotenv import dotenv_values

from fined.market_data.angel_one import (
    MAX_RESPONSE_BYTES,
    AngelOneMarketDataConfig,
)

LOGIN_ENDPOINT = (
    "https://apiconnect.angelone.in/rest/auth/angelbroking/user/v1/loginByPassword"
)
SESSION_SETUP_ERROR = "Angel One authentication failed."


class AngelOneSessionSetupError(RuntimeError):
    """Safe boundary error for local Angel One session setup."""


async def create_session_access_token(
    *,
    environment: Mapping[str, str],
    client_code: str,
    pin: str,
    totp: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Authenticate directly with Angel One and return only the session JWT."""
    try:
        config = AngelOneMarketDataConfig(
            api_key=environment["ANGEL_ONE_API_KEY"],
            access_token="pending-session",
            client_local_ip=environment["ANGEL_ONE_CLIENT_LOCAL_IP"],
            client_public_ip=environment["ANGEL_ONE_CLIENT_PUBLIC_IP"],
            mac_address=environment["ANGEL_ONE_MAC_ADDRESS"],
        )
        credentials = (client_code, pin, totp)
        if any(
            not value.strip() or "\n" in value or "\r" in value for value in credentials
        ):
            raise ValueError("invalid credential input")
        payload = {
            "clientcode": client_code.strip(),
            "password": pin.strip(),
            "totp": totp.strip(),
        }
        headers = {
            "X-PrivateKey": config.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": config.client_local_ip,
            "X-ClientPublicIP": config.client_public_ip,
            "X-MACAddress": config.mac_address,
        }
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            follow_redirects=False,
            transport=transport,
        ) as client:
            response = await client.post(
                LOGIN_ENDPOINT,
                content=json.dumps(payload, separators=(",", ":")),
                headers=headers,
            )
        if response.status_code != 200 or len(response.content) > MAX_RESPONSE_BYTES:
            raise ValueError("invalid login response")
        body = response.json()
        if not isinstance(body, dict) or body.get("status") is not True:
            raise ValueError("login was not successful")
        data = body.get("data")
        if not isinstance(data, dict):
            raise ValueError("login data is missing")
        token = data.get("jwtToken")
        if (
            not isinstance(token, str)
            or not token.strip()
            or "\n" in token
            or "\r" in token
        ):
            raise ValueError("login token is invalid")
        return token.strip()
    except Exception:
        raise AngelOneSessionSetupError(SESSION_SETUP_ERROR) from None


def save_access_token(env_path: Path, token: str) -> None:
    """Atomically save only the short-lived JWT in a local environment file."""
    if not token.strip() or "\n" in token or "\r" in token:
        raise AngelOneSessionSetupError(SESSION_SETUP_ERROR)
    path = Path(env_path)
    original = path.read_text(encoding="utf-8")
    line = f"ANGEL_ONE_ACCESS_TOKEN={token.strip()}"
    pattern = re.compile(r"^ANGEL_ONE_ACCESS_TOKEN=.*$", re.MULTILINE)
    if pattern.search(original):
        updated = pattern.sub(line, original, count=1)
    else:
        updated = f"{original.rstrip()}\n{line}\n"

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            os.fchmod(temporary.fileno(), 0o600)
            temporary.write(updated)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


async def configure_session_access_token(
    *,
    env_path: Path,
    client_code: str,
    pin: str,
    totp: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Authenticate from local prompts and persist only the returned JWT."""
    values = dotenv_values(env_path)
    environment = {key: value or "" for key, value in values.items()}
    token = await create_session_access_token(
        environment=environment,
        client_code=client_code,
        pin=pin,
        totp=totp,
        transport=transport,
    )
    save_access_token(env_path, token)


def run_session_setup(
    *,
    env_path: Path,
    input_fn: Callable[[str], str] = input,
    secret_fn: Callable[[str], str] = getpass.getpass,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """Run the local prompt flow without echoing or retaining broker secrets."""
    try:
        client_code = input_fn("Angel One client ID: ").strip()
        pin = secret_fn("Angel One PIN: ").strip()
        totp = secret_fn("Current Angel One TOTP: ").strip()
        asyncio.run(
            configure_session_access_token(
                env_path=env_path,
                client_code=client_code,
                pin=pin,
                totp=totp,
                transport=transport,
            )
        )
    except (EOFError, KeyboardInterrupt):
        print("Angel One session setup cancelled.", file=sys.stderr)
        return 130
    except AngelOneSessionSetupError:
        print(SESSION_SETUP_ERROR, file=sys.stderr)
        return 1
    print("Angel One session token saved locally.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_session_setup(env_path=Path(".env.local")))
