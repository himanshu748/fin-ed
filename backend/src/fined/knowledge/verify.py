from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fined.knowledge.index import KnowledgeIndex, SearchHit
from fined.modes import LearningMode


class KnowledgeRetriever(Protocol):
    async def search(
        self,
        query: str,
        learning_mode: LearningMode,
        as_of_date: object | None = None,
        broker: str | None = None,
        top_k: int = 4,
    ) -> list[SearchHit]: ...


@dataclass(frozen=True)
class VerificationQuery:
    label: str
    query: str
    learning_mode: LearningMode
    broker: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    label: str
    source_ids: tuple[str, ...]


class KnowledgeVerificationError(RuntimeError):
    """Raised when a required topic has no attributable evidence."""


DEFAULT_VERIFICATION_QUERIES = (
    VerificationQuery("etf", "exchange traded fund ETF", LearningMode.ETFS),
    VerificationQuery(
        "dp_charges",
        "DP charges demat debit",
        LearningMode.STOCKS,
        broker="Angel One",
    ),
    VerificationQuery(
        "sip",
        "systematic investment plan SIP mutual fund",
        LearningMode.MUTUAL_FUNDS,
    ),
    VerificationQuery("gold_tax", "gold jewellery GST", LearningMode.GOLD),
    VerificationQuery(
        "fno_risk",
        "derivatives futures options risks",
        LearningMode.FNO,
    ),
)


async def verify_queries(
    retriever: KnowledgeRetriever,
    queries: tuple[VerificationQuery, ...] = DEFAULT_VERIFICATION_QUERIES,
) -> list[VerificationResult]:
    results: list[VerificationResult] = []
    for item in queries:
        hits = await retriever.search(
            item.query,
            item.learning_mode,
            broker=item.broker,
            top_k=4,
        )
        source_ids = tuple(dict.fromkeys(hit.source_id for hit in hits if hit.url))
        if not source_ids:
            raise KnowledgeVerificationError(
                f"knowledge verification failed for {item.label}"
            )
        results.append(VerificationResult(item.label, source_ids))
    return results


def _parser() -> argparse.ArgumentParser:
    backend_dir = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(
        description="Verify representative queries against the published index."
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=backend_dir / "data" / "knowledge" / "generated",
    )
    return parser


async def _run_cli() -> int:
    from dotenv import load_dotenv
    from google import genai

    from fined.knowledge.embeddings import GeminiEmbedder

    args = _parser().parse_args()
    backend_dir = Path(__file__).resolve().parents[3]
    load_dotenv(backend_dir / ".env.local")
    client = genai.Client()
    try:
        index = KnowledgeIndex.load(args.directory, GeminiEmbedder(client))
        results = await verify_queries(index)
    finally:
        await client.aio.aclose()
    print(
        json.dumps(
            {
                "status": "verified",
                "queries": [
                    {"label": result.label, "source_ids": list(result.source_ids)}
                    for result in results
                ],
            },
            indent=2,
        )
    )
    return 0


def main() -> int:
    try:
        return asyncio.run(_run_cli())
    except (KnowledgeVerificationError, OSError, ValueError) as exc:
        print(f"knowledge verification failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
