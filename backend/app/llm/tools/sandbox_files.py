"""Sandbox file tools for skill-assisted chat."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

from app.core.config import settings
from app.llm.tools.builtin.media import ToolExecutionResult
from app.services.sandbox.gateway import sandbox_gateway
from app.services.sandbox.models import (
    SandboxArtifactLimits,
    SandboxArtifactSpec,
    SandboxJob,
    SandboxJobSource,
    SandboxLimits,
)

from .registry import ToolInfo, ToolParameter, tool_registry

_MAX_READ_CHARS = 200_000
_MAX_WRITE_CHARS = 1_000_000
_HASHLINE_SNAPSHOT_DIR = "tmp/.hashline-snapshots"
_HASHLINE_CLIPBOARD_PATH = "tmp/.hashline-clipboard.json"
_HASHLINE_RUNTIME = r"""
import difflib
import json
import os
import tempfile
from collections import Counter
from hashlib import blake2s
from pathlib import Path

_HASHLINE_TAG_PATTERN = r"[0-9A-F]{4}"
_MAX_SNAPSHOT_VERSIONS = 4


def _normalize_hashline_text(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _compute_file_tag(text):
    normalized = _normalize_hashline_text(text)
    return blake2s(normalized.encode("utf-8"), digest_size=2).hexdigest().upper()


def _snapshot_directory(params, path):
    configured = params.get("snapshot_dir")
    root = Path(configured) if configured else path.parent / ".hashline-snapshots"
    path_key = blake2s(
        str(path.resolve()).encode("utf-8"), digest_size=16
    ).hexdigest()
    return root / path_key


def _valid_snapshot(data, path, tag, expected_text=None):
    if not isinstance(data, dict):
        return False
    text = data.get("text")
    if not isinstance(text, str):
        return False
    if data.get("path") != str(path.resolve()) or data.get("tag") != tag:
        return False
    if _compute_file_tag(text) != tag:
        return False
    return expected_text is None or text == _normalize_hashline_text(expected_text)


def _load_snapshot(params, path, tag, expected_text=None):
    directory = _snapshot_directory(params, path)
    if not directory.is_dir():
        return None
    candidates = sorted(
        directory.glob(f"{tag}-*.json"),
        key=lambda candidate: candidate.stat().st_mtime_ns,
        reverse=True,
    )
    for candidate in candidates:
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        if _valid_snapshot(data, path, tag, expected_text):
            return data
    return None


def _record_snapshot(params, path, text, seen_lines=()):
    normalized = _normalize_hashline_text(text)
    tag = _compute_file_tag(normalized)
    directory = _snapshot_directory(params, path)
    directory.mkdir(parents=True, exist_ok=True)
    content_hash = blake2s(normalized.encode("utf-8"), digest_size=16).hexdigest()
    snapshot_path = directory / f"{tag}-{content_hash}.json"
    merged_seen = set(seen_lines)
    if snapshot_path.is_file():
        try:
            existing = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            existing = None
        if _valid_snapshot(existing, path, tag, normalized):
            merged_seen.update(existing.get("seen_lines", []))

    payload = {
        "path": str(path.resolve()),
        "tag": tag,
        "text": normalized,
        "seen_lines": sorted(merged_seen),
    }
    descriptor, temporary_name = tempfile.mkstemp(
        dir=directory, prefix=".snapshot-", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            json.dump(payload, temporary, ensure_ascii=False, separators=(",", ":"))
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, snapshot_path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)

    snapshots = sorted(
        directory.glob("*.json"),
        key=lambda candidate: candidate.stat().st_mtime_ns,
        reverse=True,
    )
    for expired in snapshots[_MAX_SNAPSHOT_VERSIONS:]:
        try:
            expired.unlink()
        except FileNotFoundError:
            pass
    return tag


def _format_hashlines(lines, tag, max_chars, start_line=1, end_line=None, search=None):
    start_index = start_line - 1
    stop_index = len(lines) if end_line is None else min(end_line, len(lines))
    chunks = []
    seen_lines = []
    length = 0
    for index in range(start_index, stop_index):
        if search is not None and search not in lines[index]:
            continue
        row = f"{index + 1}#{tag}| {lines[index]}"
        chunk = ("\n" if chunks else "") + row
        remaining = max_chars - length
        # A line that would exceed the budget is not fully returned; never emit
        # its anchor, since every shown LINE#ID must be an editable target.
        if len(chunk) > remaining:
            break
        chunks.append(chunk)
        seen_lines.append(index + 1)
        length += len(chunk)
    return "".join(chunks), seen_lines


def _matching_line_map(previous_lines, current_lines):
    matcher = difflib.SequenceMatcher(
        None, previous_lines, current_lines, autojunk=False
    )
    line_map = {}
    for previous_start, current_start, size in matcher.get_matching_blocks():
        for offset in range(size):
            line_map[previous_start + offset + 1] = current_start + offset + 1
    return line_map


def _anchor_neighbors(anchor_lines, line_count):
    sorted_lines = sorted(anchor_lines)
    neighbors = {}
    index = 0
    while index < len(sorted_lines):
        end_index = index
        while (
            end_index + 1 < len(sorted_lines)
            and sorted_lines[end_index + 1] == sorted_lines[end_index] + 1
        ):
            end_index += 1
        start = sorted_lines[index]
        end = sorted_lines[end_index]
        before = start - 1 if start > 1 else None
        after = end + 1 if end < line_count else None
        for position in range(index, end_index + 1):
            neighbors[sorted_lines[position]] = (before, after)
        index = end_index + 1
    return neighbors


def _remap_snapshot_lines(previous_text, current_text, anchor_lines):
    previous_lines = previous_text.splitlines()
    current_lines = _normalize_hashline_text(current_text).splitlines()
    line_map = _matching_line_map(previous_lines, current_lines)
    neighbors = _anchor_neighbors(anchor_lines, len(previous_lines))
    previous_counts = Counter(previous_lines)
    current_counts = Counter(current_lines)

    remapped = {}
    for line in anchor_lines:
        mapped = line_map.get(line)
        if mapped is None:
            return None
        before, after = neighbors[line]
        context_lines = [candidate for candidate in (before, after) if candidate]
        value = previous_lines[line - 1]
        # A line value that is unique in both snapshots is an exact identity;
        # unchanged context is required only when duplicate content could map
        # to more than one location.
        if previous_counts[value] != 1 or current_counts[value] != 1:
            if not context_lines or any(
                line_map.get(context) != mapped + (context - line)
                for context in context_lines
            ):
                return None
        remapped[line] = mapped
    return remapped
""".strip()

_HASHLINE_READ_CODE = (
    _HASHLINE_RUNTIME
    + r"""

import fcntl

path = Path(params["path"])
if not path.is_file():
    raise ValueError(f"not a file: {path}")
with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
    fcntl.flock(handle, fcntl.LOCK_SH)
    original = handle.read()
    lines = original.splitlines()
    start_line = params.get("start_line", 1)
    end_line = params.get("end_line")
    if start_line > len(lines) and not (start_line == 1 and not lines):
        raise ValueError(
            f"start_line {start_line} exceeds file length {len(lines)}; request an existing line range"
        )
    tag = _compute_file_tag(original)
    content, seen_lines = _format_hashlines(
        lines,
        tag,
        params["max_chars"],
        start_line,
        end_line,
        params.get("search"),
    )
    _record_snapshot(params, path, original, seen_lines)
return content
"""
).strip()

_HASHLINE_OPERATION_RUNTIME = r"""
import ast
import re

_COMPACT_EDIT_OPS = {
    "replace",
    "replace_block",
    "cut",
    "cut_block",
    "insert_before",
    "insert_after",
    "insert_block_after",
    "insert_head",
    "insert_tail",
    "paste_before",
    "paste_after",
    "paste_block_after",
    "paste_head",
    "paste_tail",
}
_BODY_OPS = {
    "replace",
    "replace_block",
    "insert_before",
    "insert_after",
    "insert_block_after",
    "insert_head",
    "insert_tail",
}
_CUT_OPS = {"cut", "cut_block"}
_PASTE_OPS = {
    "paste_before",
    "paste_after",
    "paste_block_after",
    "paste_head",
    "paste_tail",
}
_BLOCK_OPS = {
    "replace_block",
    "cut_block",
    "insert_block_after",
    "paste_block_after",
}
_UNANCHORED_OPS = {"insert_head", "insert_tail", "paste_head", "paste_tail"}


def _tag_from_reference(value):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(rf"[1-9]\d*#({_HASHLINE_TAG_PATTERN})", value.strip().upper())
    return match.group(1) if match else None


def _parse_line_reference(value, source_tag, field):
    if isinstance(value, int) and not isinstance(value, bool):
        if value < 1:
            raise ValueError(f"{field} must be at least 1")
        return value
    if isinstance(value, str):
        match = re.fullmatch(
            rf"([1-9]\d*)#({_HASHLINE_TAG_PATTERN})", value.strip().upper()
        )
        if match is not None:
            if match.group(2) != source_tag:
                raise ValueError(f"{field} uses a different read snapshot: {value}")
            return int(match.group(1))
    raise ValueError(
        f"{field} must be a positive line number with top-level tag, or a LINE#ID anchor from read"
    )


def _validate_register_name(value):
    name = "default" if value is None else value
    if not isinstance(name, str) or re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name) is None:
        raise ValueError("register must contain 1-64 letters, numbers, dots, underscores, or dashes")
    return name


def _clipboard_file(params, path):
    configured = params.get("clipboard_path")
    return Path(configured) if configured else path.parent / ".hashline-clipboard.json"


def _load_clipboard(params, path):
    clipboard_path = _clipboard_file(params, path)
    if not clipboard_path.is_file():
        return {}
    try:
        payload = json.loads(clipboard_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        raise ValueError("saved edit clipboard is unreadable")
    registers = payload.get("registers") if isinstance(payload, dict) else None
    if not isinstance(registers, dict) or any(
        not isinstance(name, str) or not isinstance(content, str)
        for name, content in registers.items()
    ):
        raise ValueError("saved edit clipboard is invalid")
    return registers


def _save_clipboard(params, path, registers):
    clipboard_path = _clipboard_file(params, path)
    clipboard_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=clipboard_path.parent, prefix=".clipboard-", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            json.dump(
                {"registers": registers},
                temporary,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, clipboard_path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _python_block_range(path, lines, anchor):
    if path.suffix.lower() not in {".py", ".pyi"}:
        return None
    try:
        tree = ast.parse("\n".join(lines))
    except SyntaxError:
        return None
    compound_types = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.With,
        ast.AsyncWith,
        ast.Match,
    )
    if hasattr(ast, "TryStar"):
        compound_types += (ast.TryStar,)
    candidates = []
    for node in ast.walk(tree):
        if not isinstance(node, compound_types):
            continue
        start = node.lineno
        decorators = getattr(node, "decorator_list", ())
        if decorators:
            start = min(start, *(decorator.lineno for decorator in decorators))
        end = getattr(node, "end_lineno", None)
        if start == anchor and isinstance(end, int) and end > start:
            candidates.append((start, end))
    return min(candidates, key=lambda span: span[1] - span[0]) if candidates else None


def _markdown_block_range(path, lines, anchor):
    if path.suffix.lower() not in {".md", ".mdx", ".markdown"}:
        return None
    match = re.match(r"^(#{1,6})\s", lines[anchor - 1].lstrip())
    if match is None:
        return None
    level = len(match.group(1))
    end = len(lines)
    for index in range(anchor, len(lines)):
        candidate = re.match(r"^(#{1,6})\s", lines[index].lstrip())
        if candidate is not None and len(candidate.group(1)) <= level:
            end = index
            break
    return (anchor, end) if end > anchor else None


def _brace_delta(line, state):
    delta = 0
    saw_open = False
    index = 0
    quote = state.get("quote")
    in_comment = state.get("comment", False)
    while index < len(line):
        char = line[index]
        following = line[index + 1] if index + 1 < len(line) else ""
        if in_comment:
            if char == "*" and following == "/":
                in_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char == "/" and following == "/":
            break
        if char == "/" and following == "*":
            in_comment = True
            index += 2
            continue
        if char in {'"', "'", "`"}:
            quote = char
        elif char == "{":
            delta += 1
            saw_open = True
        elif char == "}":
            delta -= 1
        index += 1
    if quote != "`":
        quote = None
    state["quote"] = quote
    state["comment"] = in_comment
    return delta, saw_open


def _brace_block_range(lines, anchor):
    balance = 0
    opened = False
    nonblank_before_open = 0
    state = {}
    for index in range(anchor - 1, len(lines)):
        if lines[index].strip() and not opened:
            nonblank_before_open += 1
            if nonblank_before_open > 2:
                return None
        delta, saw_open = _brace_delta(lines[index], state)
        opened = opened or saw_open
        balance += delta
        if opened and balance == 0:
            return (anchor, index + 1)
        if opened and balance < 0:
            return None
    return None


def _indent_block_range(lines, anchor):
    header = lines[anchor - 1]
    if not header.strip():
        return None
    base_indent = len(header) - len(header.lstrip(" \t"))
    end = anchor
    saw_body = False
    last_content = anchor
    for index in range(anchor, len(lines)):
        text = lines[index]
        if not text.strip():
            if saw_body:
                end = index + 1
            continue
        indent = len(text) - len(text.lstrip(" \t"))
        if indent <= base_indent:
            break
        saw_body = True
        end = index + 1
        last_content = end
    return (anchor, last_content) if saw_body and last_content > anchor else None


def _resolve_block_range(path, lines, anchor):
    if anchor < 1 or anchor > len(lines):
        return None
    for resolver in (
        lambda: _python_block_range(path, lines, anchor),
        lambda: _markdown_block_range(path, lines, anchor),
        lambda: _brace_block_range(lines, anchor),
        lambda: _indent_block_range(lines, anchor),
    ):
        resolved = resolver()
        if resolved is not None and resolved[1] > resolved[0]:
            return resolved
    return None


def _payload_lines(content):
    return _normalize_hashline_text(content).split("\n")


def _apply_compact_actions(lines, had_trailing_newline, actions):
    spans = {}
    inserts = {}
    for action in actions:
        if action["kind"] == "span":
            spans[action["start"]] = action
        else:
            inserts.setdefault(action["gap"], []).extend(action["lines"])

    output = []
    line = 1
    while line <= len(lines):
        output.extend(inserts.get(line - 1, ()))
        span = spans.get(line)
        if span is not None:
            output.extend(span["lines"])
            line = span["end"] + 1
        else:
            output.append(lines[line - 1])
            line += 1
    output.extend(inserts.get(len(lines), ()))

    updated = "\n".join(output)
    if had_trailing_newline and output:
        updated += "\n"
    return updated
""".strip()

_HASHLINE_EDIT_CODE = (
    _HASHLINE_RUNTIME
    + "\n\n"
    + _HASHLINE_OPERATION_RUNTIME
    + r"""

import fcntl

path = Path(params["path"])
if not path.is_file():
    raise ValueError(f"not a file: {path}")

with path.open("r+", encoding="utf-8", newline="") as handle:
    fcntl.flock(handle, fcntl.LOCK_EX)
    original = handle.read()
    normalized_original = _normalize_hashline_text(original)
    had_trailing_newline = normalized_original.endswith("\n")
    current_lines = normalized_original.split("\n")
    if had_trailing_newline:
        current_lines = current_lines[:-1]
    elif normalized_original == "":
        current_lines = []

    requested_tag = params.get("tag")
    source_tag = requested_tag.strip().upper() if isinstance(requested_tag, str) else None
    if source_tag is not None and re.fullmatch(_HASHLINE_TAG_PATTERN, source_tag) is None:
        raise ValueError("tag must be the four-hex ID returned by read")

    raw_operations = params["edits"]
    parsed_operations = []
    for index, item in enumerate(raw_operations, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"edit {index} must be an object")
        unknown = set(item) - {"op", "line", "end_line", "new", "register"}
        if unknown:
            raise ValueError(f"edit {index} has unsupported field(s): {', '.join(sorted(unknown))}")
        op = item.get("op", "replace")
        if op not in _COMPACT_EDIT_OPS:
            raise ValueError(f"edit {index} has unsupported op: {op}")
        for field in ("line", "end_line"):
            tag = _tag_from_reference(item.get(field))
            if tag is None:
                continue
            if source_tag is None:
                source_tag = tag
            elif source_tag != tag:
                raise ValueError("all edit operations must use the same read snapshot")
        parsed_operations.append((index, op, item))

    if source_tag is None:
        raise ValueError("edit requires top-level tag or at least one LINE#ID anchor from read")

    current_tag = _compute_file_tag(original)
    snapshot = _load_snapshot(
        params,
        path,
        source_tag,
        original if source_tag == current_tag else None,
    )
    if snapshot is None:
        raise ValueError(
            f"stale line reference(s): snapshot #{source_tag} is unavailable or does not match "
            f"current #{current_tag}; re-read the file before editing"
        )

    snapshot_lines = snapshot["text"].splitlines()
    seen_lines = set(snapshot.get("seen_lines", []))
    source_operations = []
    source_anchor_lines = set()
    warnings = []

    for index, op, item in parsed_operations:
        has_body = op in _BODY_OPS
        if has_body:
            if "new" not in item or not isinstance(item["new"], str):
                raise ValueError(f"edit {index} ({op}) requires string new content")
        elif "new" in item:
            raise ValueError(f"edit {index} ({op}) does not accept new content")

        uses_register = op in _CUT_OPS or op in _PASTE_OPS
        if not uses_register and "register" in item:
            raise ValueError(f"edit {index} ({op}) does not use a register")
        register = _validate_register_name(item.get("register")) if uses_register else None

        if op in _UNANCHORED_OPS:
            if "line" in item or "end_line" in item:
                raise ValueError(f"edit {index} ({op}) does not accept line anchors")
            source_operations.append(
                {"index": index, "op": op, "new": item.get("new"), "register": register}
            )
            continue

        if "line" not in item:
            raise ValueError(f"edit {index} ({op}) requires line")
        start = _parse_line_reference(item["line"], source_tag, "line")
        if start > len(snapshot_lines):
            raise ValueError(f"edit {index} line {start} exceeds snapshot length {len(snapshot_lines)}")
        if start not in seen_lines:
            raise ValueError(f"edit {index} line {start} was not returned by read")

        end = start
        if op in {"replace", "cut"}:
            if "end_line" in item:
                end = _parse_line_reference(item["end_line"], source_tag, "end_line")
            if end < start:
                raise ValueError(f"edit {index} range ends before it starts")
            if end > len(snapshot_lines):
                raise ValueError(f"edit {index} end_line {end} exceeds snapshot length {len(snapshot_lines)}")
            unseen = [line for line in range(start, end + 1) if line not in seen_lines]
            if unseen:
                raise ValueError(f"edit {index} range contains line(s) not returned by read: {unseen[0]}")
        elif "end_line" in item:
            raise ValueError(f"edit {index} ({op}) does not accept end_line")

        block_resolved = False
        if op in _BLOCK_OPS:
            block = _resolve_block_range(path, snapshot_lines, start)
            if block is None:
                if op in {"insert_block_after", "paste_block_after"}:
                    warnings.append(
                        f"edit {index} ({op}) could not resolve a multiline block; used line {start}"
                    )
                else:
                    raise ValueError(
                        f"edit {index} ({op}) could not resolve a multiline block beginning on line {start}"
                    )
            else:
                start, end = block
                block_resolved = True

        if op in {"replace", "cut", "replace_block", "cut_block"} or block_resolved:
            source_anchor_lines.update(range(start, end + 1))
        else:
            source_anchor_lines.add(start)
        source_operations.append(
            {
                "index": index,
                "op": op,
                "start": start,
                "end": end,
                "new": item.get("new"),
                "register": register,
            }
        )

    recovered = source_tag != current_tag
    if recovered:
        if not source_anchor_lines:
            raise ValueError(
                "head/tail-only edits require the current read tag; re-read the file before editing"
            )
        line_map = _remap_snapshot_lines(snapshot["text"], original, source_anchor_lines)
        if line_map is None:
            raise ValueError(
                f"stale line reference(s) for snapshot #{source_tag} (current #{current_tag}); "
                "target lines changed or became ambiguous; re-read the file before editing"
            )
    else:
        line_map = {line: line for line in source_anchor_lines}

    def map_span(operation):
        mapped = [line_map[line] for line in range(operation["start"], operation["end"] + 1)]
        if any(current != previous + 1 for previous, current in zip(mapped, mapped[1:])):
            raise ValueError(
                f"edit {operation['index']} target changed internally; re-read the file before editing"
            )
        return mapped[0], mapped[-1]

    registers = _load_clipboard(params, path)
    registers_changed = False
    actions = []
    operation_results = []

    for operation in source_operations:
        op = operation["op"]
        if op in _UNANCHORED_OPS:
            if op.endswith("head"):
                gap = 0
            else:
                gap = len(current_lines)
            if op.startswith("insert_"):
                payload = _payload_lines(operation["new"])
            else:
                register = operation["register"]
                if register not in registers:
                    raise ValueError(f"edit {operation['index']} found empty register: {register}")
                payload = _payload_lines(registers[register])
            actions.append({"kind": "insert", "gap": gap, "lines": payload, "index": operation["index"]})
            operation_results.append({"op": op, "gap": gap, "register": operation["register"]})
            continue

        start, end = map_span(operation)
        if op in {"replace", "replace_block"}:
            actions.append(
                {
                    "kind": "span",
                    "start": start,
                    "end": end,
                    "lines": _payload_lines(operation["new"]),
                    "index": operation["index"],
                }
            )
        elif op in _CUT_OPS:
            register = operation["register"]
            registers[register] = "\n".join(current_lines[start - 1 : end])
            registers_changed = True
            actions.append(
                {"kind": "span", "start": start, "end": end, "lines": [], "index": operation["index"]}
            )
        else:
            if op in {"insert_before", "paste_before"}:
                gap = start - 1
            elif op in {"insert_after", "paste_after"}:
                gap = start
            else:
                gap = end
            if op.startswith("insert_"):
                payload = _payload_lines(operation["new"])
            else:
                register = operation["register"]
                if register not in registers:
                    raise ValueError(f"edit {operation['index']} found empty register: {register}")
                payload = _payload_lines(registers[register])
            actions.append({"kind": "insert", "gap": gap, "lines": payload, "index": operation["index"]})

        result = {"op": op, "start": start, "end": end}
        if operation["register"] is not None:
            result["register"] = operation["register"]
        operation_results.append(result)

    spans = sorted(
        (action for action in actions if action["kind"] == "span"),
        key=lambda action: action["start"],
    )
    for previous, current in zip(spans, spans[1:]):
        if current["start"] <= previous["end"]:
            raise ValueError(
                f"edit {current['index']} overlaps edit {previous['index']}; use one operation per range"
            )
    for insertion in (action for action in actions if action["kind"] == "insert"):
        for span in spans:
            if span["start"] <= insertion["gap"] < span["end"]:
                raise ValueError(
                    f"edit {insertion['index']} inserts inside range targeted by edit {span['index']}"
                )

    updated_normalized = _apply_compact_actions(
        current_lines, had_trailing_newline, actions
    )
    ending_match = re.search(r"\r\n|\r|\n", original)
    default_ending = ending_match.group(0) if ending_match else "\n"
    updated = (
        updated_normalized.replace("\n", default_ending)
        if default_ending != "\n"
        else updated_normalized
    )

    if updated != original:
        handle.seek(0)
        handle.write(updated)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())
    if registers_changed:
        _save_clipboard(params, path, registers)
    updated_tag = _record_snapshot(params, path, updated)

return {
    "edits": len(actions),
    "changed": len(actions) if updated != original else 0,
    "bytes": len(updated.encode("utf-8")),
    "tag": updated_tag,
    "recovered": recovered,
    "results": operation_results,
    "warnings": warnings,
}
"""
).strip()


def _normalize_workspace_path(path: str) -> str:
    raw = str(path or "").strip()
    if not raw:
        raise ValueError("path is required")
    posix_path = PurePosixPath(raw)
    if posix_path.is_absolute() and not raw.startswith("/workspace"):
        raise ValueError("path must stay inside /workspace")
    relative = raw.removeprefix("/workspace/") if raw != "/workspace" else ""
    relative_path = PurePosixPath(relative)
    if ".." in relative_path.parts:
        raise ValueError("path must stay inside /workspace")
    if raw == "/workspace":
        return "/workspace"
    if raw.startswith("/workspace/"):
        return PurePosixPath("/workspace", relative_path).as_posix()
    return PurePosixPath("/workspace", posix_path).as_posix()


def _runtime_workspace_path(path: str) -> str:
    if path == "/workspace":
        return "."
    return path.removeprefix("/workspace/")


class SandboxReadTool:
    def __init__(
        self,
        session_id: str | None = None,
        allowed_commands: list[str] | None = None,
        agent_id: str | None = None,
        team_id: str | None = None,
    ):
        _ = allowed_commands
        self.session_id = session_id
        self.agent_id = agent_id
        self.team_id = team_id

    async def execute(
        self,
        path: str,
        max_chars: int = _MAX_READ_CHARS,
        start_line: int = 1,
        end_line: int | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        if not self.session_id:
            return {"success": False, "error": "Sandbox session is required"}
        try:
            safe_path = _normalize_workspace_path(path)
            limit = max(1, min(int(max_chars), _MAX_READ_CHARS))
            range_start = int(start_line)
            range_end = int(end_line) if end_line is not None else None
            if range_start < 1:
                raise ValueError("start_line must be at least 1")
            if range_end is not None and range_end < range_start:
                raise ValueError("end_line must be greater than or equal to start_line")
            if search is not None and not isinstance(search, str):
                raise ValueError("search must be a string")
            if search == "":
                raise ValueError("search must not be empty")
            job = SandboxJob(
                source=SandboxJobSource.TOOL,
                language="python",
                code=_HASHLINE_READ_CODE,
                cwd="/workspace",
                limits=SandboxLimits(timeout_seconds=10, disk_mb=1024),
                metadata={
                    "params": {
                        "path": _runtime_workspace_path(safe_path),
                        "max_chars": limit,
                        "start_line": range_start,
                        "end_line": range_end,
                        "search": search,
                        "snapshot_dir": _HASHLINE_SNAPSHOT_DIR,
                    }
                },
            )
            result = await sandbox_gateway.submit_and_wait(
                job,
                session_id=self.session_id,
                agent_id=self.agent_id,
                team_id=self.team_id,
                timeout_seconds=15,
            )
            return {
                "success": result.success,
                "path": safe_path,
                "content": result.result if result.success else None,
                "error": result.error,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class SandboxArtifactTool:
    def __init__(
        self,
        session_id: str | None = None,
        allowed_commands: list[str] | None = None,
        agent_id: str | None = None,
        team_id: str | None = None,
    ):
        _ = allowed_commands
        self.session_id = session_id
        self.agent_id = agent_id
        self.team_id = team_id

    async def execute(
        self,
        paths: list[Any],
        max_size_mb: float | None = None,
        max_total_size_mb: float | None = None,
    ) -> ToolExecutionResult:
        if not self.session_id:
            return self._result(success=False, error="Sandbox session is required")
        try:
            artifact_specs = self._build_artifact_specs(paths)
            if not artifact_specs:
                return self._result(
                    success=False, error="At least one artifact path is required"
                )
            artifact_limits = SandboxArtifactLimits(
                max_size_mb=float(
                    max_size_mb
                    if max_size_mb is not None
                    else settings.SANDBOX_ARTIFACT_MAX_FILE_SIZE_MB
                ),
                max_total_size_mb=float(
                    max_total_size_mb
                    if max_total_size_mb is not None
                    else settings.SANDBOX_ARTIFACT_MAX_TOTAL_SIZE_MB
                ),
            )
            job = SandboxJob(
                source=SandboxJobSource.TOOL,
                language="python",
                code="return {'collected': True}",
                cwd="/workspace",
                limits=SandboxLimits(timeout_seconds=10, disk_mb=1024),
                artifacts=artifact_specs,
                artifact_limits=artifact_limits,
            )
            result = await sandbox_gateway.submit_and_wait(
                job,
                session_id=self.session_id,
                agent_id=self.agent_id,
                team_id=self.team_id,
                timeout_seconds=15,
            )
            files = [
                {
                    "path": artifact.path,
                    "filename": artifact.filename,
                    "url": artifact.url,
                    "size": artifact.size,
                    "content_type": artifact.content_type,
                }
                for artifact in getattr(result, "artifacts", [])
            ]
            return self._result(success=result.success, files=files, error=result.error)
        except Exception as exc:
            return self._result(success=False, error=str(exc))

    def _build_artifact_specs(self, paths: list[Any]) -> list[SandboxArtifactSpec]:
        if not isinstance(paths, list):
            raise ValueError("paths must be a list")

        specs: list[SandboxArtifactSpec] = []
        for item in paths:
            optional = False
            description = None
            if isinstance(item, str):
                raw_path = item
            elif isinstance(item, dict):
                item_path = item.get("path")
                raw_path = item_path if isinstance(item_path, str) else ""
                optional = bool(item.get("optional", False))
                item_description = item.get("description")
                description = (
                    str(item_description) if item_description is not None else None
                )
            else:
                raise ValueError("artifact path item must be a string or object")
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ValueError("artifact path is required")
            specs.append(
                SandboxArtifactSpec(
                    path=_normalize_workspace_path(raw_path),
                    optional=optional,
                    description=description,
                )
            )
        return specs

    def _result(
        self,
        *,
        success: bool,
        files: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> ToolExecutionResult:
        files = files or []
        markdown_links = [f"[{file['filename']}]({file['url']})" for file in files]
        display_result = {
            "success": success,
            "result": f"Generated {len(markdown_links)} downloadable link(s) for the assistant response.",
            "count": len(markdown_links),
            "artifacts": files,
            "error": error,
        }
        llm_result = {
            "success": success,
            "result": "Use these Markdown links in your final answer."
            if success
            else None,
            "markdown_links": markdown_links,
            "files": files,
            "error": error,
        }
        return ToolExecutionResult(
            display_result=display_result,
            llm_result=json.dumps(llm_result, ensure_ascii=False),
        )


class SandboxEditTool:
    def __init__(
        self,
        session_id: str | None = None,
        allowed_commands: list[str] | None = None,
        agent_id: str | None = None,
        team_id: str | None = None,
    ):
        _ = allowed_commands
        self.session_id = session_id
        self.agent_id = agent_id
        self.team_id = team_id

    async def execute(
        self,
        path: str,
        edits: list[dict[str, Any]],
        tag: str | None = None,
    ) -> dict[str, Any]:
        if not self.session_id:
            return {"success": False, "error": "Sandbox session is required"}
        try:
            safe_path = _normalize_workspace_path(path)
            if not isinstance(edits, list) or not edits:
                raise ValueError("edits must be a non-empty list")

            snapshot_tag = None
            if tag is not None:
                if not isinstance(tag, str):
                    raise ValueError("tag must be a string")
                snapshot_tag = tag.strip().upper()
                if len(snapshot_tag) != 4 or any(
                    char not in "0123456789ABCDEF" for char in snapshot_tag
                ):
                    raise ValueError("tag must be the four-hex ID returned by read")

            normalized_edits: list[dict[str, Any]] = []
            total_chars = 0
            allowed_fields = {"op", "line", "end_line", "new", "register"}
            for edit in edits:
                if not isinstance(edit, dict):
                    raise ValueError("each edit must be an object")
                unknown = set(edit) - allowed_fields
                if unknown:
                    raise ValueError(
                        "unsupported edit field(s): " + ", ".join(sorted(unknown))
                    )
                if "op" in edit and not isinstance(edit["op"], str):
                    raise ValueError("edit op must be a string")
                for field in ("line", "end_line"):
                    value = edit.get(field)
                    if value is not None and (
                        isinstance(value, bool) or not isinstance(value, (int, str))
                    ):
                        raise ValueError(
                            f"edit {field} must be an integer or LINE#ID string"
                        )
                if "new" in edit:
                    if not isinstance(edit["new"], str):
                        raise ValueError("edit new content must be a string")
                    total_chars += len(edit["new"])
                if "register" in edit and not isinstance(edit["register"], str):
                    raise ValueError("edit register must be a string")
                normalized_edits.append(dict(edit))

            if total_chars > _MAX_WRITE_CHARS:
                return {"success": False, "error": "edit content is too large"}

            job = SandboxJob(
                source=SandboxJobSource.TOOL,
                language="python",
                code=_HASHLINE_EDIT_CODE,
                cwd="/workspace",
                limits=SandboxLimits(timeout_seconds=10, disk_mb=1024),
                metadata={
                    "params": {
                        "path": _runtime_workspace_path(safe_path),
                        "tag": snapshot_tag,
                        "edits": normalized_edits,
                        "snapshot_dir": _HASHLINE_SNAPSHOT_DIR,
                        "clipboard_path": _HASHLINE_CLIPBOARD_PATH,
                    }
                },
            )
            result = await sandbox_gateway.submit_and_wait(
                job,
                session_id=self.session_id,
                agent_id=self.agent_id,
                team_id=self.team_id,
                timeout_seconds=15,
            )
            details = result.result if isinstance(result.result, dict) else {}
            return {
                "success": result.success,
                "path": safe_path,
                "edits": details.get("edits", 0) if result.success else 0,
                "changed": details.get("changed", 0) if result.success else 0,
                "bytes": details.get("bytes", 0) if result.success else 0,
                "tag": details.get("tag") if result.success else None,
                "recovered": bool(details.get("recovered"))
                if result.success
                else False,
                "results": details.get("results", []) if result.success else [],
                "warnings": details.get("warnings", []) if result.success else [],
                "error": result.error,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class SandboxWriteTool:
    def __init__(
        self,
        session_id: str | None = None,
        allowed_commands: list[str] | None = None,
        agent_id: str | None = None,
        team_id: str | None = None,
    ):
        _ = allowed_commands
        self.session_id = session_id
        self.agent_id = agent_id
        self.team_id = team_id

    async def execute(self, path: str, content: str) -> dict[str, Any]:
        if not self.session_id:
            return {"success": False, "error": "Sandbox session is required"}
        try:
            safe_path = _normalize_workspace_path(path)
            text = str(content or "")
            if len(text) > _MAX_WRITE_CHARS:
                return {"success": False, "error": "content is too large"}
            job = SandboxJob(
                source=SandboxJobSource.TOOL,
                language="python",
                code=(
                    "import fcntl\n"
                    "import os\n"
                    "from pathlib import Path\n"
                    "content = params['content'].encode('utf-8')\n"
                    "path = Path(params['path'])\n"
                    "path.parent.mkdir(parents=True, exist_ok=True)\n"
                    "path.touch(exist_ok=True)\n"
                    "with path.open('r+b') as handle:\n"
                    "    fcntl.flock(handle, fcntl.LOCK_EX)\n"
                    "    handle.seek(0)\n"
                    "    handle.write(content)\n"
                    "    handle.truncate()\n"
                    "    handle.flush()\n"
                    "    os.fsync(handle.fileno())\n"
                    "return {'bytes': len(content)}\n"
                ),
                cwd="/workspace",
                limits=SandboxLimits(timeout_seconds=10, disk_mb=1024),
                metadata={
                    "params": {
                        "path": _runtime_workspace_path(safe_path),
                        "content": text,
                    }
                },
            )
            result = await sandbox_gateway.submit_and_wait(
                job,
                session_id=self.session_id,
                agent_id=self.agent_id,
                team_id=self.team_id,
                timeout_seconds=15,
            )
            bytes_written = (
                result.result.get("bytes", 0) if isinstance(result.result, dict) else 0
            )
            return {
                "success": result.success,
                "path": safe_path,
                "bytes": bytes_written if result.success else 0,
                "error": result.error,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


def register_sandbox_file_tools() -> None:
    read_info = ToolInfo(
        name="read",
        description=(
            "Read a UTF-8 text file from the sandbox workspace. Each returned line is prefixed "
            "with a hashline anchor in the form LINE#ID| content; the four-hex ID binds every "
            "returned line to the same full-file snapshot. Use start_line and end_line for an "
            "inclusive range, or search to return lines containing a case-sensitive literal "
            "string. Range and search can be combined. Paths must stay inside /workspace."
        ),
        parameters=[
            ToolParameter(
                name="path",
                type="string",
                description="File path to read. Use /workspace/file.txt or a relative path like file.txt; paths outside /workspace are rejected.",
                required=True,
            ),
            ToolParameter(
                name="start_line",
                type="integer",
                description="First line to inspect, using 1-based file line numbers. Defaults to 1.",
                required=False,
                default=1,
            ),
            ToolParameter(
                name="end_line",
                type="integer",
                description="Last line to inspect, inclusive. Omit to continue through the end of the file.",
                required=False,
            ),
            ToolParameter(
                name="search",
                type="string",
                description="Optional case-sensitive literal text. Only matching lines in the requested range are returned.",
                required=False,
            ),
            ToolParameter(
                name="max_chars",
                type="integer",
                description="Maximum characters of hashline-formatted text to return after range and search filtering.",
                required=False,
                default=_MAX_READ_CHARS,
            ),
        ],
    )
    edit_info = ToolInfo(
        name="edit",
        description=(
            "Apply compact, snapshot-verified operations to one UTF-8 file. Call read first. "
            "Use top-level tag with integer line numbers to avoid repeating LINE#ID, or pass "
            "LINE#ID directly. Supported ops: replace/range replace, replace_block, cut/cut_block, "
            "insert_before/after/block_after/head/tail, and matching paste operations. Cut stores "
            "content in a session register; paste reuses it across calls. Block resolution uses "
            "Python AST, Markdown sections, braces, then indentation. All operations are preflighted."
        ),
        parameters=[
            ToolParameter(
                name="path",
                type="string",
                description="Existing text file inside /workspace.",
                required=True,
            ),
            ToolParameter(
                name="tag",
                type="string",
                description="Four-hex snapshot ID from read. Required for integer lines and head/tail-only operations; omit when every anchor is LINE#ID.",
                required=False,
            ),
            ToolParameter(
                name="edits",
                type="array",
                description=(
                    "Ordered compact operations. Omit op for legacy single-line replace. "
                    "replace/cut accept optional inclusive end_line; *_block resolves from line; "
                    "insert_* uses new; cut/paste may name a persistent register (default: default)."
                ),
                required=True,
                items={
                    "type": "object",
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": [
                                "replace",
                                "replace_block",
                                "cut",
                                "cut_block",
                                "insert_before",
                                "insert_after",
                                "insert_block_after",
                                "insert_head",
                                "insert_tail",
                                "paste_before",
                                "paste_after",
                                "paste_block_after",
                                "paste_head",
                                "paste_tail",
                            ],
                            "description": "Operation kind. Defaults to replace when omitted.",
                        },
                        "line": {
                            "oneOf": [
                                {"type": "integer", "minimum": 1},
                                {
                                    "type": "string",
                                    "pattern": "^[1-9][0-9]*#[0-9A-Fa-f]{4}$",
                                },
                            ],
                            "description": "Start/anchor line as an integer with top-level tag, or exact LINE#ID from read.",
                        },
                        "end_line": {
                            "oneOf": [
                                {"type": "integer", "minimum": 1},
                                {
                                    "type": "string",
                                    "pattern": "^[1-9][0-9]*#[0-9A-Fa-f]{4}$",
                                },
                            ],
                            "description": "Inclusive range end for replace or cut.",
                        },
                        "new": {
                            "type": "string",
                            "description": "Final replacement or insertion text; newlines create multiple lines.",
                        },
                        "register": {
                            "type": "string",
                            "description": "Persistent cut/paste register name; defaults to default.",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            ),
        ],
    )
    write_info = ToolInfo(
        name="write",
        description=(
            "Create a new UTF-8 text file or replace a file's complete content inside the "
            "sandbox workspace. For localized changes to an existing file, use read followed "
            "by edit instead of rewriting the whole file. Use write before running non-trivial "
            "Python or Node code, then execute the script with bash. Parent directories are "
            "created automatically. Inside generated scripts, prefer output paths relative to "
            "the working directory rather than hardcoding /workspace."
        ),
        parameters=[
            ToolParameter(
                name="path",
                type="string",
                description="File path to write. Use /workspace/script.py, /workspace/output/result.txt, or a relative path; paths outside /workspace are rejected.",
                required=True,
            ),
            ToolParameter(
                name="content",
                type="string",
                description="Complete UTF-8 text content to write. Use edit instead when only a localized section needs to change.",
                required=True,
            ),
        ],
    )
    artifact_info = ToolInfo(
        name="artifact",
        description=(
            "Collect existing files or directories from /workspace and return fresh Markdown "
            "download links plus preview metadata. Call this only after verifying final user-facing "
            "files. If write, edit, or bash changes a collected file, call artifact again because "
            "earlier URLs are stale snapshots. Include the newest returned Markdown links in the "
            "final response body. Relative paths are interpreted from /workspace."
        ),
        parameters=[
            ToolParameter(
                name="paths",
                type="array",
                description=(
                    "Files or directories to collect for download. Prefer objects like "
                    '[{"path":"/workspace/output/report.docx","description":"Generated report"}]. '
                    'String paths like ["output/report.docx"] are also accepted.'
                ),
                required=True,
                items={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "optional": {"type": "boolean"},
                        "description": {"type": "string"},
                    },
                    "required": ["path"],
                },
            ),
            ToolParameter(
                name="max_size_mb",
                type="number",
                description="Maximum allowed size for each collected artifact in MB. Defaults to 10.",
                required=False,
                default=settings.SANDBOX_ARTIFACT_MAX_FILE_SIZE_MB,
            ),
            ToolParameter(
                name="max_total_size_mb",
                type="number",
                description="Maximum allowed total upload size across all collected artifacts in MB. Defaults to 10.",
                required=False,
                default=settings.SANDBOX_ARTIFACT_MAX_TOTAL_SIZE_MB,
            ),
        ],
    )
    tool_registry.register_sandbox_tool(
        "read",
        SandboxReadTool,
        tool_info=read_info,
        aliases=["Read"],
    )
    tool_registry.register_sandbox_tool(
        "edit",
        SandboxEditTool,
        tool_info=edit_info,
        aliases=["Edit"],
    )
    tool_registry.register_sandbox_tool(
        "write",
        SandboxWriteTool,
        tool_info=write_info,
        aliases=["Write"],
    )
    tool_registry.register_sandbox_tool(
        "artifact",
        SandboxArtifactTool,
        tool_info=artifact_info,
        aliases=["Artifact"],
    )


__all__ = [
    "SandboxArtifactTool",
    "SandboxEditTool",
    "SandboxReadTool",
    "SandboxWriteTool",
    "register_sandbox_file_tools",
]
