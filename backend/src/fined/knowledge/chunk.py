from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from fined.knowledge.models import ExtractedDocument, KnowledgeChunk

TARGET_MAX_CHARS = 1200
HARD_MAX_CHARS = 1800
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def chunk_document(document: ExtractedDocument) -> tuple[KnowledgeChunk, ...]:
    """Build deterministic heading-aware chunks with a strict size ceiling."""
    chunks: list[KnowledgeChunk] = []
    section_path: tuple[str, ...] | None = None
    section_blocks: list[str] = []
    section_ordinal = 0

    def flush_section() -> None:
        nonlocal section_ordinal
        if section_path is None or not section_blocks:
            return
        prefix = " > ".join(section_path)
        prefix_text = f"{prefix}\n\n" if prefix else ""
        body_limit = HARD_MAX_CHARS - len(prefix_text)
        target_limit = min(TARGET_MAX_CHARS - len(prefix_text), body_limit)
        if body_limit < 1:
            raise ValueError(
                f"source {document.source.source_id}: heading path exceeds chunk limit"
            )
        for chunk_ordinal, body in enumerate(
            _pack_units(section_blocks, max(target_limit, 1), body_limit)
        ):
            text = f"{prefix_text}{body}"
            digest = hashlib.sha256(
                f"{document.source.source_id}\0{section_ordinal}\0"
                f"{chunk_ordinal}\0{section_path}\0{text}".encode()
            ).hexdigest()[:20]
            source = document.source
            chunks.append(
                KnowledgeChunk(
                    chunk_id=f"{source.source_id}-{digest}",
                    source_id=source.source_id,
                    publisher=source.publisher,
                    authority=source.authority,
                    title=document.title,
                    heading_path=section_path,
                    text=text,
                    url=source.url,
                    topics=source.topics,
                    broker=source.broker,
                    verified_on=source.verified_on,
                    effective_from=source.effective_from,
                    effective_to=source.effective_to,
                )
            )
        section_ordinal += 1

    for block in document.blocks:
        if section_path is None:
            section_path = block.heading_path
        elif block.heading_path != section_path:
            flush_section()
            section_blocks = []
            section_path = block.heading_path
        section_blocks.append(block.text)
    flush_section()
    return tuple(chunks)


def _pack_units(blocks: Iterable[str], target: int, hard_limit: int) -> list[str]:
    units: list[str] = []
    for block in blocks:
        units.extend(_split_block(block, target, hard_limit))

    packed: list[str] = []
    current = ""
    for unit in units:
        candidate = unit if not current else f"{current}\n{unit}"
        if current and len(candidate) > target:
            packed.append(current)
            current = unit
        else:
            current = candidate
    if current:
        packed.append(current)
    return packed


def _split_block(text: str, target: int, hard_limit: int) -> list[str]:
    if len(text) <= target:
        return [text]
    sentences = _SENTENCE_END.split(text)
    if len(sentences) == 1:
        return _split_unavoidable(text, hard_limit)
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        sentence_parts = _split_unavoidable(sentence, hard_limit)
        for sentence_part in sentence_parts:
            candidate = sentence_part if not current else f"{current} {sentence_part}"
            if current and len(candidate) > target:
                parts.append(current)
                current = sentence_part
            else:
                current = candidate
    if current:
        parts.append(current)
    return parts


def _split_unavoidable(text: str, hard_limit: int) -> list[str]:
    if len(text) <= hard_limit:
        return [text]
    parts: list[str] = []
    current = text
    while len(current) > hard_limit:
        split_at = current.rfind(" ", 0, hard_limit + 1)
        if split_at <= 0:
            split_at = hard_limit
        parts.append(current[:split_at])
        current = current[split_at:].lstrip()
    if current:
        parts.append(current)
    return parts
