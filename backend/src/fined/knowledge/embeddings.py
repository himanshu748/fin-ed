from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Protocol

from google.genai import types

from fined.knowledge.models import KnowledgeChunk

ARTIFACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EmbeddingInput:
    text: str


class Embedder(Protocol):
    async def embed_documents(
        self, documents: list[EmbeddingInput]
    ) -> list[list[float]]: ...

    async def embed_query(self, query: str) -> list[float]: ...


class GeminiEmbedder:
    model = "gemini-embedding-001"
    dimensions = 768

    def __init__(self, client: Any, *, batch_size: int = 100) -> None:
        if batch_size <= 0:
            raise ValueError("embedding batch_size must be positive")
        self._models = client.aio.models
        self._batch_size = batch_size

    async def embed_documents(
        self, documents: list[EmbeddingInput]
    ) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(documents), self._batch_size):
            batch = documents[start : start + self._batch_size]
            try:
                response = await self._models.embed_content(
                    model=self.model,
                    contents=[document.text for document in batch],
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=self.dimensions,
                    ),
                )
            except Exception as exc:
                raise RuntimeError("embedding provider request failed") from exc
            vectors.extend(_response_vectors(response, len(batch), self.dimensions))
        return vectors

    async def embed_query(self, query: str) -> list[float]:
        try:
            response = await self._models.embed_content(
                model=self.model,
                contents=[query],
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=self.dimensions,
                ),
            )
        except Exception as exc:
            raise RuntimeError("embedding provider request failed") from exc
        return _response_vectors(response, 1, self.dimensions)[0]


class EmbeddingArtifactBuilder:
    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._model = embedding_model_identity(embedder)
        self._dimensions = getattr(embedder, "dimensions", None)
        if self._dimensions is not None and (
            isinstance(self._dimensions, bool)
            or not isinstance(self._dimensions, int)
            or self._dimensions <= 0
        ):
            raise ValueError("embedder dimension metadata must be a positive integer")
        self.identity = {
            "kind": "hybrid_embedding_index",
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "embedding_model": self._model,
            "embedding_dimension": self._dimensions,
        }

    async def build(
        self,
        chunks: list[KnowledgeChunk],
        source_hashes: dict[str, str],
    ) -> dict[str, bytes]:
        vectors = await self._embedder.embed_documents(
            [EmbeddingInput(chunk.text) for chunk in chunks]
        )
        if len(vectors) != len(chunks):
            raise ValueError(
                "embedding response cardinality does not match knowledge chunks"
            )
        if self._dimensions is None:
            if not vectors:
                raise ValueError(
                    "cannot infer embedding dimension from an empty knowledge build"
                )
            self._dimensions = len(vectors[0])
            if self._dimensions <= 0:
                raise ValueError("embedding dimension must be positive")
            self.identity["embedding_dimension"] = self._dimensions
        validated = [
            _normalize_vector(vector, self._dimensions, index=index)
            for index, vector in enumerate(vectors)
        ]
        chunk_rows = [_chunk_json(chunk) for chunk in chunks]
        embedding_rows = [
            {"chunk_id": chunk.chunk_id, "vector": vector}
            for chunk, vector in zip(chunks, validated, strict=True)
        ]
        chunks_bytes = _jsonl_bytes(chunk_rows)
        embeddings_bytes = _jsonl_bytes(embedding_rows)
        build = {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "embedding_model": self._model,
            "embedding_dimension": self._dimensions,
            "chunk_count": len(chunks),
            "chunk_ids": [chunk.chunk_id for chunk in chunks],
            "source_hashes": dict(sorted(source_hashes.items())),
            "chunks_sha256": hashlib.sha256(chunks_bytes).hexdigest(),
            "embeddings_sha256": hashlib.sha256(embeddings_bytes).hexdigest(),
        }
        return {
            "chunks.jsonl": chunks_bytes,
            "embeddings.jsonl": embeddings_bytes,
            "build.json": _json_bytes(build),
        }


def embedding_model_identity(embedder: Embedder) -> str:
    """Return explicit provider metadata or a stable custom-embedder type ID."""
    model = getattr(
        embedder,
        "model",
        f"{type(embedder).__module__}.{type(embedder).__qualname__}",
    )
    if not isinstance(model, str) or not model:
        raise ValueError("embedder model metadata must be non-empty text")
    return model


def _response_vectors(
    response: Any, expected_count: int, dimensions: int
) -> list[list[float]]:
    embeddings = response.embeddings
    if embeddings is None or len(embeddings) != expected_count:
        actual = 0 if embeddings is None else len(embeddings)
        raise ValueError(
            f"embedding response cardinality {actual} does not match {expected_count}"
        )
    vectors: list[list[float]] = []
    for index, embedding in enumerate(embeddings):
        if embedding is None or embedding.values is None:
            raise ValueError(f"embedding response vector {index} is missing")
        vectors.append(
            _normalize_vector(list(embedding.values), dimensions, index=index)
        )
    return vectors


def _normalize_vector(
    vector: list[float], dimensions: int, *, index: int
) -> list[float]:
    if len(vector) != dimensions:
        raise ValueError(
            f"embedding vector {index} dimension {len(vector)} does not match {dimensions}"
        )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in vector
    ):
        raise ValueError(f"embedding vector {index} must contain finite numbers")
    norm = math.sqrt(sum(float(value) * float(value) for value in vector))
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError(f"embedding vector {index} must have a nonzero norm")
    return [float(value) / norm for value in vector]


def _jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(_compact_json_bytes(row) + b"\n" for row in rows)


def _compact_json_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _chunk_json(chunk: KnowledgeChunk) -> dict[str, Any]:
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
