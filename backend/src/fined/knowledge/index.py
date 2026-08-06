from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from fined.knowledge.embeddings import (
    ARTIFACT_SCHEMA_VERSION,
    Embedder,
    embedding_model_identity,
)
from fined.knowledge.ingest import resolve_current_build
from fined.knowledge.lexical import BM25Index, tokenize
from fined.knowledge.models import KnowledgeChunk
from fined.modes import LearningMode

# Conservative startup limits keep immutable artifact validation memory-bounded.
MAX_BUILD_METADATA_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_JSONL_LINE_BYTES = 256 * 1024
MAX_KNOWLEDGE_ROWS = 10_000
MAX_EMBEDDING_DIMENSIONS = 3_072

_RRF_K = 60
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_AUTHORITY_WEIGHT = {
    "regulator": 1.020,
    "exchange": 1.015,
    "broker_pricing": 1.010,
    "broker_support": 1.005,
    "broker_education": 1.000,
}


@dataclass(frozen=True)
class SearchHit:
    source_id: str
    authority: str
    broker: str | None
    effective_from: date | None
    effective_to: date | None
    title: str
    url: str
    publisher: str
    verified_on: date
    applicability: str
    passage: str
    score: float
    confidence: Literal["high", "medium", "degraded"]


class UnavailableKnowledgeRetriever:
    """Evidence-safe retriever used only when no knowledge build was published."""

    async def search(
        self,
        query: str,
        learning_mode: LearningMode,
        as_of_date: date | None = None,
        broker: str | None = None,
        top_k: int = 4,
    ) -> list[SearchHit]:
        del query, learning_mode, as_of_date, broker, top_k
        return []


class KnowledgeIndex:
    def __init__(
        self,
        chunks: list[KnowledgeChunk],
        vectors: list[list[float]],
        embedder: Embedder,
        dimensions: int,
    ) -> None:
        self._chunks = tuple(chunks)
        self._vectors = tuple(tuple(vector) for vector in vectors)
        self._embedder = embedder
        self._dimensions = dimensions

    @classmethod
    def load(cls, directory: Path, embedder: Embedder) -> KnowledgeIndex:
        build_dir = resolve_current_build(directory)
        build = _read_json_object(build_dir / "build.json")
        schema_version = build.get("schema_version")
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != ARTIFACT_SCHEMA_VERSION
        ):
            raise ValueError("knowledge artifact schema version is unsupported")
        artifact_model = build.get("embedding_model")
        if not isinstance(artifact_model, str) or not artifact_model:
            raise ValueError("knowledge artifact embedding model is invalid")
        expected_model = embedding_model_identity(embedder)
        if artifact_model != expected_model:
            raise ValueError(
                "knowledge artifact embedding model does not match embedder"
            )
        artifact_dimensions = build.get("embedding_dimension")
        if (
            isinstance(artifact_dimensions, bool)
            or not isinstance(artifact_dimensions, int)
            or artifact_dimensions <= 0
        ):
            raise ValueError("knowledge artifact embedding dimension is invalid")
        if artifact_dimensions > MAX_EMBEDDING_DIMENSIONS:
            raise ValueError(
                "knowledge artifact embedding dimension exceeds maximum 3072"
            )
        expected_dimensions = getattr(embedder, "dimensions", None)
        if (
            expected_dimensions is not None
            and artifact_dimensions != expected_dimensions
        ):
            raise ValueError(
                "knowledge artifact embedding dimension does not match embedder"
            )
        chunk_count = build.get("chunk_count")
        if (
            isinstance(chunk_count, bool)
            or not isinstance(chunk_count, int)
            or chunk_count < 0
        ):
            raise ValueError("knowledge artifact chunk cardinality is invalid")
        if chunk_count > MAX_KNOWLEDGE_ROWS:
            raise ValueError("knowledge artifact chunk count exceeds maximum 10000")
        source_hashes = _validate_source_hashes(build.get("source_hashes"))

        chunks_path = build_dir / "chunks.jsonl"
        embeddings_path = build_dir / "embeddings.jsonl"
        chunks_hash = _required_hash(build, "chunks_sha256")
        embeddings_hash = _required_hash(build, "embeddings_sha256")
        chunk_rows = _read_hashed_json_lines(chunks_path, chunks_hash)
        embedding_rows = _read_hashed_json_lines(embeddings_path, embeddings_hash)
        chunks = [_parse_chunk(row, index) for index, row in enumerate(chunk_rows)]
        chunk_ids = [chunk.chunk_id for chunk in chunks]
        recorded_ids = build.get("chunk_ids")
        if not isinstance(recorded_ids, list) or recorded_ids != chunk_ids:
            raise ValueError("knowledge artifact chunk IDs do not match chunks")
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("knowledge artifact chunk IDs contain duplicates")
        if chunk_count != len(chunks):
            raise ValueError(
                "knowledge artifact chunk cardinality does not match build"
            )
        if set(source_hashes) != {chunk.source_id for chunk in chunks}:
            raise ValueError(
                "knowledge artifact source hash source IDs do not match chunks"
            )
        if len(embedding_rows) != len(chunks):
            raise ValueError(
                "knowledge artifact embedding cardinality does not match chunks"
            )

        embedding_ids: list[str] = []
        vectors: list[list[float]] = []
        for index, row in enumerate(embedding_rows):
            chunk_id = row.get("chunk_id")
            if not isinstance(chunk_id, str):
                raise ValueError(
                    f"knowledge embedding row {index} has invalid chunk ID"
                )
            embedding_ids.append(chunk_id)
            vector = row.get("vector")
            if not isinstance(vector, list):
                raise ValueError(f"knowledge embedding row {index} has invalid vector")
            vectors.append(_load_unit_vector(vector, artifact_dimensions, index))
        if embedding_ids != chunk_ids:
            raise ValueError(
                "knowledge artifact embedding chunk IDs do not match chunks"
            )
        return cls(chunks, vectors, embedder, artifact_dimensions)

    async def search(
        self,
        query: str,
        learning_mode: LearningMode,
        as_of_date: date | None = None,
        broker: str | None = None,
        top_k: int = 4,
    ) -> list[SearchHit]:
        if not tokenize(query) or top_k <= 0:
            return []
        selected = [
            index
            for index, chunk in enumerate(self._chunks)
            if _applies(chunk, learning_mode, as_of_date, broker)
        ]
        if not selected:
            return []

        lexical = BM25Index([self._chunks[index].text for index in selected])
        lexical_scores = lexical.score(query)
        candidates = [
            local_index
            for local_index, score in enumerate(lexical_scores)
            if score > 0.0
        ]
        if not candidates:
            return []
        lexical_rank = sorted(
            candidates,
            key=lambda index: (
                -lexical_scores[index],
                self._chunks[selected[index]].chunk_id,
            ),
        )

        degraded = False
        dense_scores: dict[int, float] = {}
        try:
            query_vector = _query_vector(
                await self._embedder.embed_query(query), self._dimensions
            )
            dense_scores = {
                index: sum(
                    left * right
                    for left, right in zip(
                        query_vector,
                        self._vectors[selected[index]],
                        strict=True,
                    )
                )
                for index in candidates
            }
            dense_rank = sorted(
                candidates,
                key=lambda index: (
                    -dense_scores[index],
                    self._chunks[selected[index]].chunk_id,
                ),
            )
        except Exception:
            degraded = True
            dense_rank = []

        scores = _rrf_scores(lexical_rank, dense_rank)
        ranked = sorted(
            candidates,
            key=lambda index: (
                -scores[index]
                * _AUTHORITY_WEIGHT.get(self._chunks[selected[index]].authority, 1.0),
                -lexical_scores[index],
                self._chunks[selected[index]].chunk_id,
            ),
        )
        limit = min(top_k, 4)
        hits: list[SearchHit] = []
        for local_index in ranked[:limit]:
            chunk = self._chunks[selected[local_index]]
            weighted_score = scores[local_index] * _AUTHORITY_WEIGHT.get(
                chunk.authority, 1.0
            )
            confidence: Literal["high", "medium", "degraded"]
            if degraded:
                confidence = "degraded"
            elif chunk.authority in {"regulator", "exchange", "broker_pricing"}:
                confidence = "high"
            else:
                confidence = "medium"
            hits.append(
                SearchHit(
                    source_id=chunk.source_id,
                    authority=chunk.authority,
                    broker=chunk.broker,
                    effective_from=chunk.effective_from,
                    effective_to=chunk.effective_to,
                    title=chunk.title,
                    url=chunk.url,
                    publisher=chunk.publisher,
                    verified_on=chunk.verified_on,
                    applicability=_applicability(chunk),
                    passage=chunk.text,
                    score=weighted_score,
                    confidence=confidence,
                )
            )
        return hits


def _rrf_scores(first: list[int], second: list[int]) -> dict[int, float]:
    scores = dict.fromkeys(first, 0.0)
    for rank, index in enumerate(first, start=1):
        scores[index] += 1.0 / (_RRF_K + rank)
    for rank, index in enumerate(second, start=1):
        scores[index] += 1.0 / (_RRF_K + rank)
    return scores


def _applies(
    chunk: KnowledgeChunk,
    learning_mode: LearningMode,
    as_of_date: date | None,
    broker: str | None,
) -> bool:
    if learning_mode != LearningMode.GENERAL and learning_mode not in chunk.topics:
        return False
    if as_of_date is not None:
        if chunk.effective_from is not None and as_of_date < chunk.effective_from:
            return False
        if chunk.effective_to is not None and as_of_date > chunk.effective_to:
            return False
    if broker is None:
        return True
    if chunk.broker is not None and chunk.broker.casefold() == broker.casefold():
        return True
    return chunk.broker is None and chunk.authority in {"regulator", "exchange"}


def _applicability(chunk: KnowledgeChunk) -> str:
    parts = [chunk.broker or "market-wide"]
    if chunk.effective_from is not None:
        parts.append(f"from {chunk.effective_from.isoformat()}")
    if chunk.effective_to is not None:
        parts.append(f"through {chunk.effective_to.isoformat()}")
    return "; ".join(parts)


def _read_json_object(path: Path) -> dict[str, object]:
    _validate_file_size(path, MAX_BUILD_METADATA_BYTES)
    try:
        with path.open("rb") as artifact_file:
            raw = artifact_file.read(MAX_BUILD_METADATA_BYTES + 1)
        if len(raw) > MAX_BUILD_METADATA_BYTES:
            raise ValueError(
                f"knowledge artifact {path.name} exceeds size limit "
                f"{MAX_BUILD_METADATA_BYTES}"
            )
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read knowledge artifact {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"knowledge artifact {path.name} must contain an object")
    return value


def _read_hashed_json_lines(path: Path, expected_hash: str) -> list[dict[str, object]]:
    _validate_file_size(path, MAX_ARTIFACT_BYTES)
    rows: list[dict[str, object]] = []
    digest = hashlib.sha256()
    total_bytes = 0
    try:
        with path.open("rb") as artifact_file:
            while True:
                raw_line = artifact_file.readline(MAX_JSONL_LINE_BYTES + 1)
                if not raw_line:
                    break
                total_bytes += len(raw_line)
                if total_bytes > MAX_ARTIFACT_BYTES:
                    raise ValueError(
                        f"knowledge artifact {path.name} exceeds size limit "
                        f"{MAX_ARTIFACT_BYTES}"
                    )
                if len(raw_line) > MAX_JSONL_LINE_BYTES:
                    raise ValueError(
                        f"knowledge artifact {path.name} line exceeds line byte limit "
                        f"{MAX_JSONL_LINE_BYTES}"
                    )
                if len(rows) >= MAX_KNOWLEDGE_ROWS:
                    raise ValueError(
                        f"knowledge artifact {path.name} exceeds row limit "
                        f"{MAX_KNOWLEDGE_ROWS}"
                    )
                digest.update(raw_line)
                line_number = len(rows) + 1
                value = json.loads(raw_line.decode("utf-8"))
                if not isinstance(value, dict):
                    raise ValueError(
                        f"knowledge artifact {path.name} line {line_number} "
                        "must be an object"
                    )
                rows.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read knowledge artifact {path.name}: {exc}") from exc
    if digest.hexdigest() != expected_hash:
        raise ValueError(f"knowledge artifact {path.name} hash does not match build")
    return rows


def _required_hash(build: dict[str, object], key: str) -> str:
    recorded = build.get(key)
    if not isinstance(recorded, str) or not _SHA256.fullmatch(recorded):
        raise ValueError(f"knowledge artifact {key} is invalid")
    return recorded


def _validate_file_size(path: Path, maximum_bytes: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"knowledge artifact file is unavailable: {path.name}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"cannot stat knowledge artifact {path.name}: {exc}") from exc
    if size > maximum_bytes:
        raise ValueError(
            f"knowledge artifact {path.name} exceeds size limit {maximum_bytes}"
        )


def _validate_source_hashes(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ValueError("knowledge artifact source_hashes must be a non-empty object")
    hashes: dict[str, str] = {}
    if len(value) > MAX_KNOWLEDGE_ROWS:
        raise ValueError("knowledge artifact source_hashes exceeds row limit")
    for source_id, source_hash in value.items():
        if not isinstance(source_id, str) or not source_id:
            raise ValueError(
                "knowledge artifact source_hashes has an invalid source ID"
            )
        if not isinstance(source_hash, str) or not _SHA256.fullmatch(source_hash):
            raise ValueError("knowledge artifact source_hashes has an invalid SHA-256")
        hashes[source_id] = source_hash
    return hashes


def _parse_chunk(value: dict[str, object], index: int) -> KnowledgeChunk:
    try:
        topics_raw = value["topics"]
        if not isinstance(topics_raw, list) or not topics_raw:
            raise ValueError("topics must be a non-empty list")
        return KnowledgeChunk(
            chunk_id=_text(value, "chunk_id"),
            source_id=_text(value, "source_id"),
            publisher=_text(value, "publisher"),
            authority=_text(value, "authority"),
            title=_text(value, "title"),
            heading_path=tuple(_text_list(value, "heading_path")),
            text=_text(value, "text"),
            url=_text(value, "url"),
            topics=tuple(LearningMode(item) for item in topics_raw),
            broker=_optional_text(value, "broker"),
            verified_on=_date_value(value, "verified_on", required=True),
            effective_from=_date_value(value, "effective_from"),
            effective_to=_date_value(value, "effective_to"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"knowledge chunk row {index} is invalid: {exc}") from exc


def _text(value: dict[str, object], key: str) -> str:
    item = value[key]
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be non-empty text")
    return item


def _optional_text(value: dict[str, object], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be text or null")
    return item


def _text_list(value: dict[str, object], key: str) -> list[str]:
    item = value[key]
    if not isinstance(item, list) or any(not isinstance(part, str) for part in item):
        raise ValueError(f"{key} must be a text list")
    return item


def _date_value(
    value: dict[str, object], key: str, *, required: bool = False
) -> date | None:
    item = value.get(key)
    if item is None and not required:
        return None
    if not isinstance(item, str):
        raise ValueError(f"{key} must be an ISO date")
    return date.fromisoformat(item)


def _load_unit_vector(value: list[object], dimensions: int, index: int) -> list[float]:
    if len(value) != dimensions:
        raise ValueError(
            f"knowledge embedding vector {index} dimension does not match build"
        )
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(item)
        for item in value
    ):
        raise ValueError(
            f"knowledge embedding vector {index} must contain finite numbers"
        )
    vector = [float(item) for item in value]
    norm = math.sqrt(sum(item * item for item in vector))
    if not math.isclose(norm, 1.0, rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError(f"knowledge embedding vector {index} must be normalized")
    return vector


def _query_vector(value: list[float], dimensions: int) -> list[float]:
    if len(value) != dimensions:
        raise ValueError("query embedding dimension does not match knowledge index")
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(item)
        for item in value
    ):
        raise ValueError("query embedding must contain finite numbers")
    norm = math.sqrt(sum(float(item) * float(item) for item in value))
    if norm <= 0.0 or not math.isfinite(norm):
        raise ValueError("query embedding must have a nonzero norm")
    return [float(item) / norm for item in value]
