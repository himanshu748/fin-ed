from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from fined.speech import strip_markdown_links_for_speech


async def _stream(*chunks: str) -> AsyncIterator[str]:
    for chunk in chunks:
        yield chunk


async def _spoken(*chunks: str) -> str:
    return "".join(
        [piece async for piece in strip_markdown_links_for_speech(_stream(*chunks))]
    )


LINK = "[DP Charges](https://example.com/dp)"


@pytest.mark.asyncio
@pytest.mark.parametrize("split_at", range(len(LINK) + 1))
async def test_markdown_link_is_sanitized_at_every_chunk_boundary(
    split_at: int,
) -> None:
    # Catches a sanitizer that recognizes links only when one input chunk is complete.
    chunks = (LINK[:split_at], LINK[split_at:])

    assert await _spoken(*chunks) == "DP Charges"


@pytest.mark.asyncio
async def test_single_character_chunks_preserve_punctuation_and_multiple_labels() -> (
    None
):
    # Catches state loss between chunks and over-stripping around adjacent links.
    text = (
        "Fees: [DP Charges](https://example.com/dp), then read "
        "[SEBI guide](https://example.com/sebi)."
    )

    assert await _spoken(*text) == "Fees: DP Charges, then read SEBI guide."


@pytest.mark.asyncio
async def test_escaped_opening_bracket_is_not_treated_as_a_link_at_any_boundary() -> (
    None
):
    # Catches deletion from Markdown whose opening bracket is escaped.
    text = r"\[DP Charges](https://example.com/dp)"

    for split_at in range(len(text) + 1):
        assert await _spoken(text[:split_at], text[split_at:]) == text


@pytest.mark.asyncio
async def test_invalid_destination_is_not_stripped_at_any_boundary() -> None:
    # Catches parenthesized prose being mistaken for a complete Markdown link.
    text = "literal [x](not a URL) text"

    for split_at in range(len(text) + 1):
        assert await _spoken(text[:split_at], text[split_at:]) == text


@pytest.mark.asyncio
async def test_nested_link_label_is_sanitized_at_any_boundary() -> None:
    # Catches a first-closing-bracket parser that misses a complete nested label.
    text = "[outer [inner]](https://example.com)"

    for split_at in range(len(text) + 1):
        assert await _spoken(text[:split_at], text[split_at:]) == "outer [inner]"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "[DP Charges]",
        "[DP Charges](",
        "[DP Charges](https://example.com/dp",
        "Plain [bracketed text] stays unchanged.",
        "Asterisk *Markdown* stays unchanged.",
    ],
)
async def test_incomplete_or_non_link_markdown_flushes_unchanged(text: str) -> None:
    # Catches data loss when EOF arrives while a possible link is buffered.
    assert await _spoken(*text) == text


@pytest.mark.asyncio
async def test_ordinary_text_is_yielded_before_the_source_finishes() -> None:
    # Catches implementations that buffer the entire response before speaking.
    release = asyncio.Event()

    async def delayed_stream() -> AsyncIterator[str]:
        yield "Seedha answer: "
        await release.wait()
        yield LINK

    sanitized = strip_markdown_links_for_speech(delayed_stream())
    first = await asyncio.wait_for(sanitized.__anext__(), timeout=0.5)
    release.set()

    assert first == "Seedha answer: "
    assert "".join([first, *[piece async for piece in sanitized]]) == (
        "Seedha answer: DP Charges"
    )


@pytest.mark.asyncio
async def test_overlong_unmatched_link_candidate_flushes_before_stream_end() -> None:
    # Catches unbounded buffering after an unmatched opening bracket.
    release = asyncio.Event()
    malformed = "[" + "x" * 5000

    async def delayed_stream() -> AsyncIterator[str]:
        yield "prefix "
        yield malformed
        await release.wait()

    sanitized = strip_markdown_links_for_speech(delayed_stream())
    first = await sanitized.__anext__()
    pending_piece = asyncio.create_task(sanitized.__anext__())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    flushed_before_end = pending_piece.done()
    release.set()
    second = await pending_piece
    remainder = "".join([piece async for piece in sanitized])

    assert flushed_before_end is True
    assert first + second + remainder == "prefix " + malformed
