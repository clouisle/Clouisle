"""Byte-bounded channel replies with paragraph, table and code boundaries."""

from __future__ import annotations

import re

DEFAULT_TEXT_LIMIT = 3500
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_SEPARATOR = re.compile(r":?-{3,}:?$")
_BREAK = re.compile(r"[。！？!?；;]|[.!?](?=\s)|\s+")


def _size(text: str) -> int:
    return len(text.encode("utf-8"))


def _plain(text: str, limit: int) -> list[str]:
    """Preserve every character; prefer paragraphs, lines, then sentences."""
    chunks = []
    start = 0
    while start < len(text):
        end = start
        used = 0
        while end < len(text):
            width = _size(text[end])
            if used + width > limit:
                break
            used += width
            end += 1
        if end == start:
            raise ValueError("limit cannot fit a Unicode character")
        if end < len(text):
            window = text[start:end]
            boundary = window.rfind("\n\n")
            if boundary >= 0:
                end = start + boundary + 2
            elif "\n" in window:
                end = start + window.rfind("\n") + 1
            else:
                matches = list(_BREAK.finditer(window))
                if matches:
                    end = start + matches[-1].end()
        chunks.append(text[start:end])
        start = end
    return chunks


def _cells(line: str) -> list[str]:
    # Escaped pipes and pipes inside inline code are cell content.
    result, current = [], []
    escaped, ticks = False, 0
    for token in re.findall(r"`+|.", line.strip().strip("|")):
        if token.startswith("`") and not escaped:
            ticks = 0 if len(token) == ticks else (len(token) if not ticks else ticks)
        if token == "|" and not escaped and not ticks:
            result.append("".join(current))
            current = []
        else:
            current.append(token)
        escaped = token == "\\" and not escaped
    result.append("".join(current))
    return result


def _table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines) or "|" not in lines[index]:
        return False
    cells = _cells(lines[index + 1])
    return (
        bool(cells)
        and len(cells) == len(_cells(lines[index]))
        and all(_SEPARATOR.fullmatch(cell.strip()) for cell in cells)
    )


def _row_parts(row: str, budget: int) -> list[str]:
    if _size(row) <= budget:
        return [row]
    cells = _cells(row)
    # Keep the column structure even if a single cell cannot fit in one message.
    overhead = len(cells) + 1
    if budget - overhead < 4:
        return _plain(row, budget)
    fragments = [
        list(_plain(cell, budget - overhead)) if cell else [""] for cell in cells
    ]
    rows = []
    for column, parts in enumerate(fragments):
        for part in parts:
            values = [""] * len(cells)
            values[column] = part
            rows.append("|" + "|".join(values) + "|")
    return rows


def _table(lines: list[str], limit: int) -> list[str]:
    text = "".join(lines)
    if _size(text) <= limit:
        return [text]
    newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
    header = lines[0].rstrip("\r\n") + newline + lines[1].rstrip("\r\n") + newline
    budget = limit - _size(header) - _size(newline)
    if budget < 4:
        # An oversized header cannot be repeated within the provider limit.
        return _plain(text, limit)
    chunks, current = [], header
    for row in lines[2:]:
        for part in _row_parts(row.rstrip("\r\n"), budget):
            addition = part + newline
            if _size(current + addition) > limit:
                chunks.append(current)
                current = header
            current += addition
    if current != header:
        chunks.append(current)
    return chunks or _plain(text, limit)


def _code(lines: list[str], marker: str, closed: bool, limit: int) -> list[str]:
    text = "".join(lines)
    if _size(text) <= limit:
        return [text]
    newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
    opening = lines[0].rstrip("\r\n") + newline
    closing = lines[-1].rstrip("\r\n") if closed else marker
    budget = limit - _size(opening + newline + closing)
    if budget < 4:
        return _plain(text, limit)
    body = "".join(lines[1:-1] if closed else lines[1:])
    pieces = _plain(body, budget)
    return [
        opening + piece + ("" if piece.endswith("\n") else newline) + closing
        for piece in pieces
    ]


def split_message_text(text: str, *, limit: int = DEFAULT_TEXT_LIMIT) -> list[str]:
    """Split replies without truncation; repeat table headers and code fences.

    Paragraphs and complete Markdown structures stay together when they fit.
    Oversized rows continue cell-by-cell with empty cells preserving columns.
    If a header/fence itself cannot fit, plain text splitting takes precedence
    over structure so the provider byte limit is never exceeded.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not text:
        return []
    if _size(text) <= limit:
        return [text]
    lines = text.splitlines(keepends=True)
    units: list[list[str]] = []
    index = 0
    while index < len(lines):
        fence = _FENCE.fullmatch(lines[index].rstrip("\r\n"))
        if fence:
            marker = fence[1]
            end = index + 1
            while end < len(lines):
                if re.fullmatch(
                    r" {0,3}"
                    + re.escape(marker[0])
                    + "{"
                    + str(len(marker))
                    + r",}\s*",
                    lines[end],
                ):
                    break
                end += 1
            closed = end < len(lines)
            stop = end + 1 if closed else end
            units.append(_code(lines[index:stop], marker, closed, limit))
            index = stop
        elif _table_start(lines, index):
            end = index + 2
            while end < len(lines) and "|" in lines[end] and lines[end].strip():
                end += 1
            units.append(_table(lines[index:end], limit))
            index = end
        else:
            end = index + 1
            while (
                end < len(lines)
                and not _FENCE.fullmatch(lines[end].rstrip("\r\n"))
                and not _table_start(lines, end)
            ):
                if not lines[end - 1].strip():
                    break
                end += 1
            units.append(_plain("".join(lines[index:end]), limit))
            index = end
    chunks, current = [], ""
    for pieces in units:
        for index, piece in enumerate(pieces):
            if current and (index > 0 or _size(current + piece) > limit):
                chunks.append(current)
                current = ""
            current += piece
    if current:
        chunks.append(current)
    return chunks
