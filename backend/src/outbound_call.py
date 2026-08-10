"""Private operator command for one consented FinEd Saathi reminder call."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from dotenv import load_dotenv
from livekit import api

from fined.outbound import (
    OUTBOUND_REMINDER_PAPER_PRACTICE,
    LiveKitOutboundAPI,
    OutboundCallError,
    OutboundCallRequest,
    OutboundConfigurationError,
    initiate_outbound_call,
)


@dataclass(frozen=True)
class OperatorCallResult:
    exit_code: int
    message: str


def create_outbound_client() -> api.LiveKitAPI:
    """Disable transport failover because a dial attempt must never replay."""
    return api.LiveKitAPI(failover=False)


def build_request_from_environment(
    phone_number: str,
    environment: Mapping[str, str] | None = None,
) -> OutboundCallRequest:
    """Read only the stored outbound trunk and existing private LiveKit config."""
    source = os.environ if environment is None else environment
    return OutboundCallRequest(
        phone_number=phone_number,
        sip_trunk_id=source.get("SIP_OUTBOUND_TRUNK_ID", ""),
        agent_name=source.get("FINED_OUTBOUND_AGENT_NAME", "my-agent"),
        reminder=OUTBOUND_REMINDER_PAPER_PRACTICE,
    )


async def run_operator_call(
    request: OutboundCallRequest,
    *,
    dry_run: bool,
    client_factory: Callable[
        [], AbstractAsyncContextManager[LiveKitOutboundAPI]
    ] = create_outbound_client,
) -> OperatorCallResult:
    """Perform one explicitly requested dial, with no retry or contact logging."""
    if dry_run:
        return OperatorCallResult(0, "Dry run passed. No phone call was made.")
    try:
        async with client_factory() as client:
            await initiate_outbound_call(client, request)
    except OutboundCallError as error:
        return OperatorCallResult(
            1,
            f"Outbound learning reminder was not started: {error.outcome}.",
        )
    except Exception:
        return OperatorCallResult(1, "Outbound learning reminder was not started.")
    return OperatorCallResult(0, "Outbound learning reminder was answered.")


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Place one consented FinEd Saathi paper-trading practice reminder call."
        )
    )
    parser.add_argument(
        "--consent-confirmed",
        action="store_true",
        required=True,
        help=(
            "Confirm a current, specific opt-in and no do-not-call request before "
            "this one manual attempt."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate private configuration without creating a LiveKit client or call.",
    )
    return parser


def read_recipient_phone_number() -> str:
    """Read a recipient number from a private terminal, never argv or a pipeline."""
    if not sys.stdin.isatty():
        raise OutboundConfigurationError(
            "Recipient number must be entered from a private terminal."
        )
    return getpass.getpass("Recipient E.164 phone number: ")


def main(arguments: list[str] | None = None) -> int:
    args = _argument_parser().parse_args(arguments)
    load_dotenv(".env.local")
    try:
        request = build_request_from_environment(read_recipient_phone_number())
    except OutboundConfigurationError:
        print("Outbound calling is not configured safely.")
        return 2
    result = asyncio.run(run_operator_call(request, dry_run=args.dry_run))
    print(result.message)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
