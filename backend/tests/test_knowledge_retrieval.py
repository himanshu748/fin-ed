from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest
from google.genai import types

from fined.knowledge.embeddings import (
    ARTIFACT_SCHEMA_VERSION,
    EmbeddingArtifactBuilder,
    EmbeddingInput,
    GeminiEmbedder,
)
from fined.knowledge.index import KnowledgeIndex
from fined.knowledge.ingest import (
    BuildError,
    FetchedPage,
    build_snapshots,
    resolve_current_build,
)
from fined.knowledge.lexical import BM25Index, tokenize
from fined.knowledge.models import KnowledgeChunk, SourceSpec
from fined.modes import LearningMode

BUILD_METADATA_LIMIT = 2 * 1024 * 1024
ARTIFACT_BYTES_LIMIT = 64 * 1024 * 1024
JSONL_LINE_LIMIT = 256 * 1024
KNOWLEDGE_ROW_LIMIT = 10_000


class FakeEmbedder:
    model = "fake-embedding-001"
    dimensions = 2

    def __init__(self) -> None:
        self.query_calls = 0

    async def embed_documents(
        self, documents: list[EmbeddingInput]
    ) -> list[list[float]]:
        return [
            _unit([float(index), 1.0]) for index, _ in enumerate(documents, start=1)
        ]

    async def embed_query(self, query: str) -> list[float]:
        self.query_calls += 1
        if query.startswith("fail embedding"):
            raise RuntimeError("offline")
        return _unit([1.0, 1.0])


class MinimalFakeEmbedder:
    async def embed_documents(
        self, documents: list[EmbeddingInput]
    ) -> list[list[float]]:
        return [[float(index), 1.0] for index, _ in enumerate(documents, start=1)]

    async def embed_query(self, query: str) -> list[float]:
        return [1.0, 1.0]


def _unit(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def _chunk(
    chunk_id: str,
    text: str,
    *,
    title: str,
    authority: str,
    topics: tuple[LearningMode, ...],
    broker: str | None = None,
    effective_from: date | None = None,
    effective_to: date | None = None,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=chunk_id,
        source_id=f"source_{chunk_id}",
        publisher="SEBI" if authority == "regulator" else (broker or "NSE"),
        authority=authority,
        title=title,
        heading_path=(title,),
        text=text,
        url=f"https://example.test/{chunk_id}",
        topics=topics,
        broker=broker,
        verified_on=date(2026, 8, 6),
        effective_from=effective_from,
        effective_to=effective_to,
    )


def _write_index(
    root: Path,
    chunks: list[KnowledgeChunk],
    embedder: FakeEmbedder,
    *,
    build_changes: dict[str, object] | None = None,
    embedding_changes: dict[str, object] | None = None,
) -> Path:
    build_id = "build-0123456789abcdef01234567"
    build_dir = root / "builds" / build_id
    build_dir.mkdir(parents=True)
    chunk_rows = [_chunk_row(chunk) for chunk in chunks]
    vectors = [_unit([float(index), 1.0]) for index in range(1, len(chunks) + 1)]
    embedding_rows = [
        {"chunk_id": chunk.chunk_id, "vector": vector}
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    if embedding_changes:
        embedding_rows[0].update(embedding_changes)
    chunks_path = build_dir / "chunks.jsonl"
    embeddings_path = build_dir / "embeddings.jsonl"
    _write_jsonl(chunks_path, chunk_rows)
    _write_jsonl(embeddings_path, embedding_rows)
    build = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "embedding_model": embedder.model,
        "embedding_dimension": embedder.dimensions,
        "chunk_count": len(chunks),
        "chunk_ids": [chunk.chunk_id for chunk in chunks],
        "source_hashes": {chunk.source_id: "0" * 64 for chunk in chunks},
        "chunks_sha256": hashlib.sha256(chunks_path.read_bytes()).hexdigest(),
        "embeddings_sha256": hashlib.sha256(embeddings_path.read_bytes()).hexdigest(),
    }
    if build_changes:
        build.update(build_changes)
    (build_dir / "build.json").write_text(
        json.dumps(build, sort_keys=True), encoding="utf-8"
    )
    os.symlink(Path("builds") / build_id, root / "current")
    return build_dir


def _change_build(
    build_dir: Path,
    *,
    changes: dict[str, object] | None = None,
    remove: tuple[str, ...] = (),
) -> None:
    path = build_dir / "build.json"
    build = json.loads(path.read_text(encoding="utf-8"))
    for key in remove:
        build.pop(key, None)
    if changes:
        build.update(changes)
    path.write_text(json.dumps(build, sort_keys=True), encoding="utf-8")


def _replace_artifact(build_dir: Path, name: str, content: bytes) -> None:
    path = build_dir / name
    path.write_bytes(content)
    hash_key = {
        "chunks.jsonl": "chunks_sha256",
        "embeddings.jsonl": "embeddings_sha256",
    }[name]
    _change_build(
        build_dir,
        changes={hash_key: hashlib.sha256(content).hexdigest()},
    )


def _chunk_row(chunk: KnowledgeChunk) -> dict[str, object]:
    return {
        "chunk_id": chunk.chunk_id,
        "source_id": chunk.source_id,
        "publisher": chunk.publisher,
        "authority": chunk.authority,
        "title": chunk.title,
        "heading_path": list(chunk.heading_path),
        "text": chunk.text,
        "url": chunk.url,
        "topics": [topic.value for topic in chunk.topics],
        "broker": chunk.broker,
        "verified_on": chunk.verified_on.isoformat(),
        "effective_from": (
            chunk.effective_from.isoformat() if chunk.effective_from else None
        ),
        "effective_to": chunk.effective_to.isoformat() if chunk.effective_to else None,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_bm25_normalizes_unicode_case_and_preserves_indian_finance_terms() -> None:
    index = BM25Index(
        [
            "F&O margin kya hota hai?",
            "Mutual fund ka expense ratio samjho.",
        ]
    )

    assert tokenize("\uff26\uff06\uff2f MARGIN Kya Hota Hai") == [
        "f&o",
        "margin",
        "kya",
        "hota",
        "hai",
    ]
    scores = index.score("f&o margin")
    assert scores[0] > scores[1]


@pytest.fixture
def chunks() -> list[KnowledgeChunk]:
    return [
        _chunk(
            "etf_definition",
            "ETF kya hota hai: exchange traded fund ek pooled investment hai.",
            title="ETF definition",
            authority="exchange",
            topics=(LearningMode.ETFS,),
        ),
        _chunk(
            "angel_dp_current",
            "Angel One DP charge current schedule: ₹20 plus GST per debit.",
            title="Current DP charges",
            authority="broker_pricing",
            topics=(LearningMode.STOCKS,),
            broker="Angel One",
            effective_from=date(2026, 1, 1),
        ),
        _chunk(
            "angel_dp_old",
            "Angel One DP charge old schedule: ₹10 per debit.",
            title="Old DP charges",
            authority="broker_pricing",
            topics=(LearningMode.STOCKS,),
            broker="Angel One",
            effective_to=date(2025, 12, 31),
        ),
        _chunk(
            "digital_gold_tax",
            "Physical or digital gold kharidne par 3% GST tax lagta hai.",
            title="Gold purchase tax",
            authority="regulator",
            topics=(LearningMode.GOLD,),
        ),
        _chunk(
            "gold_etf",
            "Gold ETF aur SGB securities hain; in par physical gold ka 3% GST nahi.",
            title="Gold ETF and SGB",
            authority="exchange",
            topics=(LearningMode.GOLD, LearningMode.ETFS),
        ),
        _chunk(
            "regulator_etf",
            "ETF investor units ko exchange par trade karta hai; market risk applies.",
            title="Official ETF definition",
            authority="regulator",
            topics=(LearningMode.ETFS,),
        ),
        _chunk(
            "broker_etf",
            "ETF guaranteed return dene wala product hai.",
            title="Broker ETF lesson",
            authority="broker_education",
            topics=(LearningMode.ETFS,),
            broker="Other Broker",
        ),
    ]


@pytest.fixture
def loaded_index(
    tmp_path: Path, chunks: list[KnowledgeChunk]
) -> tuple[KnowledgeIndex, FakeEmbedder]:
    embedder = FakeEmbedder()
    _write_index(tmp_path, chunks, embedder)
    return KnowledgeIndex.load(tmp_path, embedder), embedder


@pytest.mark.asyncio
async def test_etf_query_returns_definition(
    loaded_index: tuple[KnowledgeIndex, FakeEmbedder],
) -> None:
    index, _ = loaded_index

    hits = await index.search("ETF kya hota hai?", LearningMode.ETFS)

    assert hits[0].title == "ETF definition"
    assert "pooled investment" in hits[0].passage


@pytest.mark.asyncio
async def test_broker_query_returns_current_pricing_and_keeps_neutral_authorities(
    loaded_index: tuple[KnowledgeIndex, FakeEmbedder],
) -> None:
    index, _ = loaded_index

    hits = await index.search(
        "Angel One DP charge kya hai?",
        LearningMode.STOCKS,
        as_of_date=date(2026, 8, 6),
        broker="angel one",
    )

    assert hits[0].title == "Current DP charges"
    assert all(hit.title != "Old DP charges" for hit in hits)


@pytest.mark.asyncio
async def test_gold_purchase_query_does_not_conflate_gold_etf_or_sgb(
    loaded_index: tuple[KnowledgeIndex, FakeEmbedder],
) -> None:
    index, _ = loaded_index

    hits = await index.search("Gold kharidne par 3% tax?", LearningMode.GOLD)

    assert hits[0].title == "Gold purchase tax"
    assert hits[1].title == "Gold ETF and SGB"


@pytest.mark.asyncio
async def test_effective_date_excludes_schedule_outside_range(
    loaded_index: tuple[KnowledgeIndex, FakeEmbedder],
) -> None:
    index, _ = loaded_index

    hits = await index.search(
        "Angel One DP charge",
        LearningMode.STOCKS,
        as_of_date=date(2025, 10, 1),
        broker="Angel One",
    )

    assert hits[0].title == "Old DP charges"
    assert all(hit.title != "Current DP charges" for hit in hits)


@pytest.mark.asyncio
async def test_regulator_definition_outranks_conflicting_broker_education(
    loaded_index: tuple[KnowledgeIndex, FakeEmbedder],
) -> None:
    index, _ = loaded_index

    hits = await index.search("ETF market risk", LearningMode.ETFS)

    titles = [hit.title for hit in hits]
    assert titles.index("Official ETF definition") < titles.index("Broker ETF lesson")


@pytest.mark.asyncio
async def test_search_hits_preserve_backing_regulator_exchange_and_broker_provenance(
    loaded_index: tuple[KnowledgeIndex, FakeEmbedder],
) -> None:
    # Catches SearchHit construction that drops or guesses KnowledgeChunk provenance.
    index, _ = loaded_index

    regulator_hits = await index.search("ETF market risk", LearningMode.ETFS)
    regulator = next(
        hit for hit in regulator_hits if hit.title == "Official ETF definition"
    )
    exchange_hits = await index.search("ETF kya hota hai", LearningMode.ETFS)
    exchange = next(hit for hit in exchange_hits if hit.title == "ETF definition")
    broker_hits = await index.search(
        "Angel One DP charge",
        LearningMode.STOCKS,
        as_of_date=date(2026, 8, 6),
        broker="Angel One",
    )
    broker = next(hit for hit in broker_hits if hit.title == "Current DP charges")

    assert (
        regulator.source_id,
        regulator.authority,
        regulator.broker,
        regulator.effective_from,
        regulator.effective_to,
    ) == ("source_regulator_etf", "regulator", None, None, None)
    assert (
        exchange.source_id,
        exchange.authority,
        exchange.broker,
        exchange.effective_from,
        exchange.effective_to,
    ) == ("source_etf_definition", "exchange", None, None, None)
    assert (
        broker.source_id,
        broker.authority,
        broker.broker,
        broker.effective_from,
        broker.effective_to,
    ) == (
        "source_angel_dp_current",
        "broker_pricing",
        "Angel One",
        date(2026, 1, 1),
        None,
    )


@pytest.mark.asyncio
async def test_embedding_failure_returns_lexical_results_as_degraded(
    loaded_index: tuple[KnowledgeIndex, FakeEmbedder],
) -> None:
    index, embedder = loaded_index

    hits = await index.search("fail embedding", LearningMode.GENERAL)

    assert hits == []
    assert embedder.query_calls == 0

    hits = await index.search("fail embedding ETF", LearningMode.ETFS)

    assert hits
    assert all(hit.confidence == "degraded" for hit in hits)
    assert embedder.query_calls == 1


@pytest.mark.asyncio
async def test_empty_and_zero_evidence_queries_do_not_return_arbitrary_chunks(
    loaded_index: tuple[KnowledgeIndex, FakeEmbedder],
) -> None:
    index, embedder = loaded_index

    assert await index.search("   ", LearningMode.GENERAL) == []
    assert await index.search("penguin astronomy", LearningMode.GENERAL) == []
    assert embedder.query_calls == 0


@pytest.mark.asyncio
async def test_search_embeds_query_once_and_never_embeds_documents(
    loaded_index: tuple[KnowledgeIndex, FakeEmbedder],
) -> None:
    index, embedder = loaded_index

    await index.search("ETF definition", LearningMode.GENERAL)

    assert embedder.query_calls == 1


@pytest.mark.parametrize(
    ("build_changes", "embedding_changes", "message"),
    [
        ({"schema_version": 999}, None, "schema"),
        ({"embedding_model": "wrong-model"}, None, "model"),
        ({"embedding_dimension": 3}, None, "dimension"),
        ({"chunk_ids": ["wrong"]}, None, "chunk IDs"),
        (None, {"chunk_id": "wrong"}, "chunk IDs"),
        (None, {"vector": [float("nan"), 0.0]}, "finite"),
        (None, {"vector": [True, 0.0]}, "finite"),
        (None, {"vector": [1.0, 1.0]}, "normalized"),
    ],
)
def test_load_rejects_invalid_generated_artifacts(
    tmp_path: Path,
    build_changes: dict[str, object] | None,
    embedding_changes: dict[str, object] | None,
    message: str,
) -> None:
    embedder = FakeEmbedder()
    chunk = _chunk(
        "etf",
        "ETF definition",
        title="ETF",
        authority="exchange",
        topics=(LearningMode.ETFS,),
    )
    _write_index(
        tmp_path,
        [chunk],
        embedder,
        build_changes=build_changes,
        embedding_changes=embedding_changes,
    )

    with pytest.raises(ValueError, match=message):
        KnowledgeIndex.load(tmp_path, embedder)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"schema_version": True}, "schema"),
        ({"chunk_count": True}, "chunk cardinality"),
    ],
)
def test_load_rejects_boolean_integer_metadata(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    embedder = FakeEmbedder()
    chunk = _chunk(
        "etf",
        "ETF definition",
        title="ETF",
        authority="exchange",
        topics=(LearningMode.ETFS,),
    )
    _write_index(tmp_path, [chunk], embedder, build_changes=changes)

    with pytest.raises(ValueError, match=message):
        KnowledgeIndex.load(tmp_path, embedder)


@pytest.mark.parametrize(
    ("changes", "remove", "message"),
    [
        (None, ("chunks_sha256",), "chunks_sha256"),
        ({"embeddings_sha256": "g" * 64}, (), "embeddings_sha256"),
        ({"source_hashes": []}, (), "source_hashes"),
        ({"source_hashes": {"source_etf": "0" * 63}}, (), "source_hashes"),
        ({"source_hashes": {"wrong_source": "0" * 64}}, (), "source IDs"),
    ],
)
def test_load_requires_strict_schema_v1_hash_metadata(
    tmp_path: Path,
    changes: dict[str, object] | None,
    remove: tuple[str, ...],
    message: str,
) -> None:
    embedder = FakeEmbedder()
    chunk = _chunk(
        "etf",
        "ETF definition",
        title="ETF",
        authority="exchange",
        topics=(LearningMode.ETFS,),
    )
    build_dir = _write_index(tmp_path, [chunk], embedder)
    _change_build(build_dir, changes=changes, remove=remove)

    with pytest.raises(ValueError, match=message):
        KnowledgeIndex.load(tmp_path, embedder)


def test_load_rejects_oversized_build_metadata_before_decoding(
    tmp_path: Path,
) -> None:
    embedder = FakeEmbedder()
    chunk = _chunk(
        "etf",
        "ETF definition",
        title="ETF",
        authority="exchange",
        topics=(LearningMode.ETFS,),
    )
    build_dir = _write_index(tmp_path, [chunk], embedder)
    with (build_dir / "build.json").open("r+b") as build_file:
        build_file.truncate(BUILD_METADATA_LIMIT + 1)

    with pytest.raises(ValueError, match=r"build\.json.*size limit"):
        KnowledgeIndex.load(tmp_path, embedder)


def test_load_rejects_oversized_artifact_before_hashing(tmp_path: Path) -> None:
    embedder = FakeEmbedder()
    chunk = _chunk(
        "etf",
        "ETF definition",
        title="ETF",
        authority="exchange",
        topics=(LearningMode.ETFS,),
    )
    build_dir = _write_index(tmp_path, [chunk], embedder)
    with (build_dir / "chunks.jsonl").open("r+b") as chunks_file:
        chunks_file.truncate(ARTIFACT_BYTES_LIMIT + 1)

    with pytest.raises(ValueError, match=r"chunks\.jsonl.*size limit"):
        KnowledgeIndex.load(tmp_path, embedder)


def test_load_stops_at_oversized_jsonl_line(tmp_path: Path) -> None:
    embedder = FakeEmbedder()
    chunk = _chunk(
        "etf",
        "ETF definition",
        title="ETF",
        authority="exchange",
        topics=(LearningMode.ETFS,),
    )
    build_dir = _write_index(tmp_path, [chunk], embedder)
    oversized = _chunk_row(chunk)
    oversized["padding"] = "x" * JSONL_LINE_LIMIT
    _replace_artifact(
        build_dir,
        "chunks.jsonl",
        (json.dumps(oversized) + "\n").encode("utf-8"),
    )

    with pytest.raises(ValueError, match=r"chunks\.jsonl.*line.*limit"):
        KnowledgeIndex.load(tmp_path, embedder)


def test_load_stops_when_jsonl_row_limit_is_exceeded(tmp_path: Path) -> None:
    embedder = FakeEmbedder()
    chunk = _chunk(
        "etf",
        "ETF definition",
        title="ETF",
        authority="exchange",
        topics=(LearningMode.ETFS,),
    )
    build_dir = _write_index(tmp_path, [chunk], embedder)
    _replace_artifact(
        build_dir,
        "chunks.jsonl",
        b"{}\n" * (KNOWLEDGE_ROW_LIMIT + 1),
    )

    with pytest.raises(ValueError, match=r"chunks\.jsonl.*row limit"):
        KnowledgeIndex.load(tmp_path, embedder)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"chunk_count": KNOWLEDGE_ROW_LIMIT + 1}, "chunk count.*maximum"),
        ({"embedding_dimension": 3073}, "dimension.*maximum"),
    ],
)
def test_load_rejects_oversized_count_and_dimension_metadata(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    embedder = FakeEmbedder()
    chunk = _chunk(
        "etf",
        "ETF definition",
        title="ETF",
        authority="exchange",
        topics=(LearningMode.ETFS,),
    )
    _write_index(tmp_path, [chunk], embedder, build_changes=changes)

    with pytest.raises(ValueError, match=message):
        KnowledgeIndex.load(tmp_path, embedder)


class FakeModels:
    def __init__(self, responses: list[list[list[float] | None]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    async def embed_content(self, **kwargs: object) -> types.EmbedContentResponse:
        self.calls.append(kwargs)
        values = self.responses.pop(0)
        return types.EmbedContentResponse(
            embeddings=[
                types.ContentEmbedding(values=value) if value is not None else None
                for value in values
            ]
        )


@pytest.mark.asyncio
async def test_gemini_embedder_batches_documents_and_normalizes_vectors() -> None:
    raw = [3.0] + [0.0] * 767
    models = FakeModels([[[*raw], [*raw]], [[*raw]]])
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    embedder = GeminiEmbedder(client, batch_size=2)

    vectors = await embedder.embed_documents(
        [EmbeddingInput("one"), EmbeddingInput("two"), EmbeddingInput("three")]
    )

    assert vectors == [[1.0] + [0.0] * 767] * 3
    assert [call["contents"] for call in models.calls] == [
        ["one", "two"],
        ["three"],
    ]
    assert all(call["model"] == "gemini-embedding-001" for call in models.calls)
    assert all(
        call["config"].task_type == "RETRIEVAL_DOCUMENT" for call in models.calls
    )
    assert all(call["config"].output_dimensionality == 768 for call in models.calls)


@pytest.mark.asyncio
async def test_gemini_query_uses_query_task_and_rejects_malformed_response() -> None:
    raw = [0.0] * 767 + [2.0]
    models = FakeModels([[[*raw]], [[1.0] * 767]])
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    embedder = GeminiEmbedder(client)

    assert await embedder.embed_query("ETF") == [0.0] * 767 + [1.0]
    assert models.calls[0]["config"].task_type == "RETRIEVAL_QUERY"

    with pytest.raises(ValueError, match="dimension"):
        await embedder.embed_query("bad")


class ProviderFailureModels:
    async def embed_content(self, **kwargs: object) -> types.EmbedContentResponse:
        raise RuntimeError("provider echoed secret source body")


@pytest.mark.asyncio
async def test_gemini_provider_failure_does_not_expose_source_content() -> None:
    client = SimpleNamespace(aio=SimpleNamespace(models=ProviderFailureModels()))
    embedder = GeminiEmbedder(client)

    with pytest.raises(RuntimeError, match="provider request failed") as failure:
        await embedder.embed_documents([EmbeddingInput("secret source body")])

    assert "secret source body" not in str(failure.value)


class FakeFetcher:
    async def fetch(
        self, source: SourceSpec, allowed_hosts: frozenset[str]
    ) -> FetchedPage:
        return FetchedPage(
            requested_url=source.url,
            final_url=source.url,
            status_code=200,
            text=(
                "<article><h1>DP charge</h1>"
                "<p>DP charge current schedule is twenty rupees.</p></article>"
            ),
            content_type="text/html",
        )


def _manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "dp_charge",
                        "publisher": "Broker",
                        "authority": "broker_pricing",
                        "url": "https://example.test/dp",
                        "topics": ["stocks"],
                        "broker": "Broker",
                        "verified_on": "2026-08-06",
                        "status": "required",
                        "expected_terms": ["DP charge"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_embedding_artifacts_publish_inside_immutable_build(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "sources.json"
    _manifest(manifest)
    embedder = FakeEmbedder()

    report = await build_snapshots(
        manifest,
        tmp_path / "generated",
        FakeFetcher(),
        artifact_builder=EmbeddingArtifactBuilder(embedder),
    )

    assert report.current_build == resolve_current_build(tmp_path / "generated")
    assert {"chunks.jsonl", "embeddings.jsonl", "build.json"}.issubset(
        {path.name for path in report.current_build.iterdir()}
    )
    loaded = KnowledgeIndex.load(tmp_path / "generated", embedder)
    hits = await loaded.search("DP charge", LearningMode.STOCKS)
    assert hits[0].title == "DP charge"


@pytest.mark.asyncio
async def test_snapshot_only_build_loads_as_lexical_rag(tmp_path: Path) -> None:
    manifest = tmp_path / "sources.json"
    _manifest(manifest)
    generated = tmp_path / "generated"
    embedder = FakeEmbedder()

    await build_snapshots(manifest, generated, FakeFetcher())

    loaded = KnowledgeIndex.load(generated, embedder)
    hits = await loaded.search("DP charge", LearningMode.STOCKS)

    assert hits[0].source_id == "dp_charge"
    assert hits[0].confidence == "degraded"
    assert embedder.query_calls == 0


@pytest.mark.asyncio
async def test_embedder_protocol_does_not_require_metadata_attributes(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "sources.json"
    _manifest(manifest)
    embedder = MinimalFakeEmbedder()
    generated = tmp_path / "generated"

    report = await build_snapshots(
        manifest,
        generated,
        FakeFetcher(),
        artifact_builder=EmbeddingArtifactBuilder(embedder),
    )

    embedding_row = json.loads(
        (report.current_build / "embeddings.jsonl").read_text(encoding="utf-8")
    )
    assert embedding_row["vector"] == pytest.approx([math.sqrt(0.5), math.sqrt(0.5)])
    assert sum(value * value for value in embedding_row["vector"]) == pytest.approx(1.0)
    index = KnowledgeIndex.load(generated, embedder)
    hits = await index.search("DP charge", LearningMode.STOCKS)
    assert hits[0].title == "DP charge"


@pytest.mark.asyncio
async def test_method_only_embedder_rejects_mutated_model_identity(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "sources.json"
    _manifest(manifest)
    embedder = MinimalFakeEmbedder()
    generated = tmp_path / "generated"
    report = await build_snapshots(
        manifest,
        generated,
        FakeFetcher(),
        artifact_builder=EmbeddingArtifactBuilder(embedder),
    )
    _change_build(
        report.current_build,
        changes={"embedding_model": "tampered.MinimalFakeEmbedder"},
    )

    with pytest.raises(ValueError, match="model"):
        KnowledgeIndex.load(generated, embedder)


class FailingArtifactBuilder:
    identity: ClassVar[dict[str, object]] = {
        "kind": "embedding",
        "model": "fails",
    }

    async def build(
        self,
        chunks: list[KnowledgeChunk],
        source_hashes: dict[str, str],
    ) -> dict[str, bytes]:
        raise RuntimeError("provider unavailable")


class ConflictingArtifactBuilder:
    identity: ClassVar[dict[str, object]] = {"kind": "conflict"}

    async def build(
        self,
        chunks: list[KnowledgeChunk],
        source_hashes: dict[str, str],
    ) -> dict[str, bytes]:
        return {"dp_charge.json": b"overwritten"}


@pytest.mark.asyncio
async def test_artifact_failure_leaves_previous_current_active(tmp_path: Path) -> None:
    manifest = tmp_path / "sources.json"
    _manifest(manifest)
    generated = tmp_path / "generated"
    previous = await build_snapshots(manifest, generated, FakeFetcher())
    before_target = os.readlink(generated / "current")

    with pytest.raises(BuildError, match=r"artifact.*provider unavailable"):
        await build_snapshots(
            manifest,
            generated,
            FakeFetcher(),
            artifact_builder=FailingArtifactBuilder(),
        )

    assert os.readlink(generated / "current") == before_target
    assert resolve_current_build(generated) == previous.current_build


@pytest.mark.asyncio
async def test_artifact_cannot_overwrite_a_source_snapshot(tmp_path: Path) -> None:
    manifest = tmp_path / "sources.json"
    _manifest(manifest)

    with pytest.raises(BuildError, match="conflicts with a snapshot"):
        await build_snapshots(
            manifest,
            tmp_path / "generated",
            FakeFetcher(),
            artifact_builder=ConflictingArtifactBuilder(),
        )


@pytest.mark.asyncio
async def test_indexed_and_extraction_only_builds_have_distinct_identities(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "sources.json"
    _manifest(manifest)
    generated = tmp_path / "generated"

    extraction = await build_snapshots(manifest, generated, FakeFetcher())
    indexed = await build_snapshots(
        manifest,
        generated,
        FakeFetcher(),
        artifact_builder=EmbeddingArtifactBuilder(FakeEmbedder()),
    )

    assert extraction.build_id != indexed.build_id
    assert extraction.current_build.is_dir()
    assert indexed.current_build.is_dir()
