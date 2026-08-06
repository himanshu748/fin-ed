"""Speech-only text transforms for FinEd Saathi."""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator

# Curated citation labels and destinations remain well below this conservative cap.
MAX_MARKDOWN_LINK_CANDIDATE_CHARS = 4096


async def strip_markdown_links_for_speech(
    chunks: AsyncIterable[str],
) -> AsyncIterator[str]:
    """Yield Markdown link labels while omitting complete link URLs from speech."""
    pending = ""
    async for chunk in chunks:
        pending += chunk
        while pending:
            opening = pending.find("[")
            if opening < 0:
                retained = _trailing_escape_length(pending)
                emit_end = len(pending) - retained
                if emit_end:
                    yield pending[:emit_end]
                    pending = pending[emit_end:]
                break
            if _is_escaped(pending, opening):
                yield pending[: opening + 1]
                pending = pending[opening + 1 :]
                continue
            if opening:
                yield pending[:opening]
                pending = pending[opening:]

            label_end = _find_label_end(pending)
            if label_end < 0:
                if len(pending) > MAX_MARKDOWN_LINK_CANDIDATE_CHARS:
                    yield pending[0]
                    pending = pending[1:]
                    continue
                break
            if label_end + 1 > MAX_MARKDOWN_LINK_CANDIDATE_CHARS:
                yield pending[0]
                pending = pending[1:]
                continue
            if len(pending) == label_end + 1:
                break
            if pending[label_end + 1] != "(":
                yield pending[: label_end + 1]
                pending = pending[label_end + 1 :]
                continue

            status, link_end = _find_link_end(pending, start=label_end + 2)
            if status == "incomplete":
                if len(pending) > MAX_MARKDOWN_LINK_CANDIDATE_CHARS:
                    yield pending[0]
                    pending = pending[1:]
                    continue
                break
            if status == "invalid":
                yield pending[0]
                pending = pending[1:]
                continue
            if link_end + 1 > MAX_MARKDOWN_LINK_CANDIDATE_CHARS:
                yield pending[0]
                pending = pending[1:]
                continue
            label = pending[1:label_end]
            if label:
                yield label
            pending = pending[link_end + 1 :]

    if pending:
        yield pending


def _trailing_escape_length(value: str) -> int:
    count = 0
    for current in reversed(value):
        if current != "\\":
            break
        count += 1
    return count % 2


def _is_escaped(value: str, index: int) -> bool:
    backslashes = 0
    for current in reversed(value[:index]):
        if current != "\\":
            break
        backslashes += 1
    return backslashes % 2 == 1


def _find_label_end(value: str) -> int:
    depth = 1
    escaped = False
    for index in range(1, len(value)):
        current = value[index]
        if escaped:
            escaped = False
        elif current == "\\":
            escaped = True
        elif current == "[":
            depth += 1
        elif current == "]":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _find_link_end(value: str, *, start: int) -> tuple[str, int]:
    index = start
    while index < len(value) and value[index].isspace():
        index += 1
    if index == len(value):
        return "incomplete", -1
    if value[index] == ")":
        return "complete", index
    if value[index] == "<":
        return _find_angle_destination_end(value, index + 1)

    depth = 0
    escaped = False
    while index < len(value):
        current = value[index]
        if escaped:
            escaped = False
        elif current == "\\":
            escaped = True
        elif current.isspace():
            return _find_optional_title_end(value, index)
        elif current in "<>":
            return "invalid", -1
        elif current == "(":
            depth += 1
        elif current == ")":
            if depth == 0:
                return "complete", index
            depth -= 1
        index += 1
    return "incomplete", -1


def _find_angle_destination_end(value: str, start: int) -> tuple[str, int]:
    escaped = False
    for index in range(start, len(value)):
        current = value[index]
        if escaped:
            escaped = False
        elif current == "\\":
            escaped = True
        elif current == ">":
            return _find_optional_title_end(value, index + 1)
        elif current == "<" or current in "\r\n":
            return "invalid", -1
    return "incomplete", -1


def _find_optional_title_end(value: str, start: int) -> tuple[str, int]:
    index = start
    had_whitespace = False
    while index < len(value) and value[index].isspace():
        had_whitespace = True
        index += 1
    if index == len(value):
        return "incomplete", -1
    if value[index] == ")":
        return "complete", index
    if not had_whitespace or value[index] not in {'"', "'", "("}:
        return "invalid", -1

    opener = value[index]
    closer = ")" if opener == "(" else opener
    escaped = False
    index += 1
    while index < len(value):
        current = value[index]
        if escaped:
            escaped = False
        elif current == "\\":
            escaped = True
        elif current == closer:
            index += 1
            while index < len(value) and value[index].isspace():
                index += 1
            if index == len(value):
                return "incomplete", -1
            if value[index] == ")":
                return "complete", index
            return "invalid", -1
        elif current in "\r\n":
            return "invalid", -1
        index += 1
    return "incomplete", -1
