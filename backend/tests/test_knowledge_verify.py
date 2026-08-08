from __future__ import annotations

from datetime import date

import pytest

from fined.knowledge.index import SearchHit
from fined.knowledge.verify import (
    DEFAULT_VERIFICATION_QUERIES,
    KnowledgeVerificationError,
    verify_queries,
)
from fined.modes import LearningMode


class RecordingRetriever:
    def __init__(self, missing_label: str | None = None) -> None:
        self.calls: list[tuple[str, LearningMode, str | None]] = []
        self.missing_label = missing_label

    async def search(
        self,
        query: str,
        learning_mode: LearningMode,
        as_of_date: date | None = None,
        broker: str | None = None,
        top_k: int = 4,
    ) -> list[SearchHit]:
        del as_of_date, top_k
        self.calls.append((query, learning_mode, broker))
        label = next(
            item.label for item in DEFAULT_VERIFICATION_QUERIES if item.query == query
        )
        if label == self.missing_label:
            return []
        return [
            SearchHit(
                source_id=f"source-{label}",
                authority="regulator",
                broker=broker,
                effective_from=None,
                effective_to=None,
                title=f"Source for {label}",
                url="https://example.test/source",
                publisher="Example authority",
                verified_on=date(2026, 8, 8),
                applicability="market-wide",
                passage="Attributable evidence.",
                score=1.0,
                confidence="high",
            )
        ]


@pytest.mark.asyncio
async def test_verify_queries_covers_each_required_topic() -> None:
    retriever = RecordingRetriever()

    results = await verify_queries(retriever)

    assert [result.label for result in results] == [
        "etf",
        "dp_charges",
        "sip",
        "gold_tax",
        "fno_risk",
    ]
    assert all(result.source_ids for result in results)
    assert len(retriever.calls) == len(DEFAULT_VERIFICATION_QUERIES)
    assert (
        "DP charges demat debit",
        LearningMode.STOCKS,
        "Angel One",
    ) in retriever.calls


@pytest.mark.asyncio
async def test_verify_queries_fails_when_a_topic_has_no_evidence() -> None:
    retriever = RecordingRetriever(missing_label="fno_risk")

    with pytest.raises(KnowledgeVerificationError, match="fno_risk"):
        await verify_queries(retriever)
