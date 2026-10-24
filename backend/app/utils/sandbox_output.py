"""Concise model-facing rendering for sandbox tool payloads.

Display payloads stay structured for the UI and durable replay. This module only
decides how much prose the model sees; it never mutates the payload.
"""

from __future__ import annotations

import json
from typing import Any

SANDBOX_OUTPUT_TOOLS = frozenset({"bash", "read", "edit", "write", "artifact"})

#: Maximum lines kept in a bash preview before head/tail windowing.
PREVIEW_MAX_LINES = 80
PREVIEW_HEAD_LINES = 20
PREVIEW_TAIL_LINES = 60
#: Maximum characters of a single stream preview.
PREVIEW_MAX_CHARS = 12_000


def preview_stream(text: str | None) -> tuple[str, int, bool]:
    """Return a bounded preview plus omitted-line and character-clipping flags."""
    if not text:
        return "", 0, False
    lines = text.splitlines()
    omitted_lines = 0
    preview = text
    if len(lines) > PREVIEW_MAX_LINES:
        head = lines[:PREVIEW_HEAD_LINES]
        tail = lines[-PREVIEW_TAIL_LINES:]
        omitted_lines = len(lines) - len(head) - len(tail)
        preview = "\n".join([*head, f"… <{omitted_lines} lines omitted> …", *tail])
    chars_truncated = False
    if len(preview) > PREVIEW_MAX_CHARS:
        head_chars = PREVIEW_MAX_CHARS * 2 // 3
        tail_chars = PREVIEW_MAX_CHARS - head_chars
        preview = (
            preview[:head_chars]
            + "\n… <middle characters omitted> …\n"
            + preview[-tail_chars:]
        )
        chars_truncated = True
    return preview, omitted_lines, chars_truncated


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _error(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    return f"Error: {error}" if error else ""


def _bash(payload: dict[str, Any]) -> str:
    status = payload.get("status")
    if status not in {"completed", "failed", "timed_out"}:
        status = "completed" if payload.get("success") else "failed"
    label = {
        "completed": "Status: completed",
        "failed": "Status: failed",
        "timed_out": "Status: timed out",
    }[status]
    exit_code = payload.get("exit_code")
    if exit_code is not None and status != "timed_out":
        label += f" · exit {exit_code}"
    duration_ms = payload.get("duration_ms")
    if isinstance(duration_ms, int) and duration_ms >= 0:
        label += f" · {duration_ms}ms"

    parts = [label]
    error = _error(payload)
    stderr = payload.get("stderr") or ""
    if error and error.removeprefix("Error: ") not in stderr:
        parts.append(error)
    stdout = (payload.get("stdout") or "").rstrip("\n")
    if stdout:
        parts.append(f"<stdout>\n{stdout}\n</stdout>")
    stderr = stderr.rstrip("\n")
    if stderr:
        parts.append(f"<stderr>\n{stderr}\n</stderr>")

    for stream in ("stdout", "stderr"):
        omitted = payload.get(f"{stream}_omitted_lines") or 0
        chars_truncated = payload.get(f"{stream}_preview_chars_truncated")
        capture_truncated = payload.get(f"{stream}_capture_truncated")
        log_path = payload.get(f"{stream}_log")
        log_lines = payload.get(f"{stream}_lines")
        log_partial = payload.get(f"{stream}_log_partial")
        if not (omitted or chars_truncated or capture_truncated or log_partial):
            continue
        note = [f"{stream.capitalize()} preview"]
        if omitted:
            note.append(f"omits {omitted} line(s)")
        if chars_truncated:
            note.append("clips long line content")
        if capture_truncated:
            note.append("shows the beginning of output beyond the capture limit")
        if log_path:
            location = f"{log_path} ({log_lines} line(s))" if log_lines else log_path
            note.append(f"{'partial' if log_partial else 'full'} log: {location}")
            if log_partial:
                note.append("the process was stopped at the output limit")
            note.append(
                "use read with start_line/end_line to inspect further lines; "
                "for one very long line, slice bytes with bash (e.g. cut/dd)"
            )
        else:
            note.append("the omitted portion is not available")
        parts.append("; ".join(note) + ".")
    return "\n".join(filter(None, parts))


def _read(payload: dict[str, Any]) -> str:
    path = payload.get("path")
    tag = payload.get("tag")
    header = " · ".join(
        str(value) for value in (path, f"tag={tag}" if tag else None) if value
    )
    if payload.get("error"):
        error = _error(payload)
        return f"{header}\n{error}" if header else error
    content = payload.get("content")
    if payload.get("success") is False:
        message = "Read failed."
        return f"{header}\n{message}" if header else message
    if isinstance(content, str) and content:
        return f"{header}\n{content}" if header else content
    message = "No lines returned."
    return f"{header}\n{message}" if header else message


def _edit(payload: dict[str, Any]) -> str:
    if payload.get("error"):
        return _error(payload)
    path = payload.get("path") or "file"
    changed = payload.get("changed", 0)
    edits = payload.get("edits", 0)
    line = f"Edited {path}: {changed} of {edits} operation(s) changed"
    if payload.get("bytes") is not None:
        line += f", {payload['bytes']} bytes"
    if payload.get("tag"):
        line += f", tag {payload['tag']}"
    parts = [line + "."]
    warnings = payload.get("warnings")
    if isinstance(warnings, list):
        parts.extend(f"Warning: {warning}" for warning in warnings if warning)
    return "\n".join(parts)


def _write(payload: dict[str, Any]) -> str:
    if payload.get("error"):
        return _error(payload)
    path = payload.get("path") or "file"
    size = payload.get("bytes")
    suffix = f" ({size} bytes)" if isinstance(size, int) else ""
    return f"Wrote {path}{suffix}."


def _artifact(payload: dict[str, Any]) -> str:
    files = payload.get("files") or payload.get("artifacts") or []
    if not isinstance(files, list):
        return _json(payload)
    if not files:
        if payload.get("error"):
            return _error(payload)
        return str(
            payload.get("instruction") or payload.get("result") or "Collected no files."
        )
    lines = [f"Collected {len(files)} file(s)."]
    for item in files:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename") or item.get("path") or "file"
        details = []
        if item.get("url"):
            details.append(f"[{filename}]({item['url']})")
        else:
            details.append(filename)
        if item.get("asset_ref"):
            details.append(f"ref={item['asset_ref']}")
        if isinstance(item.get("size"), int):
            details.append(f"{item['size']} bytes")
        if item.get("content_type"):
            details.append(str(item["content_type"]))
        lines.append("- " + " · ".join(details))
    error = _error(payload)
    if error:
        lines.append(error)
    instruction = payload.get("instruction") or payload.get("result")
    if instruction:
        lines.append(str(instruction))
    return "\n".join(lines)


_RENDERERS = {
    "bash": _bash,
    "read": _read,
    "edit": _edit,
    "write": _write,
    "artifact": _artifact,
}


def render_sandbox_output(tool_name: str, payload: Any) -> str:
    """Render one sandbox tool payload for the model."""
    if not isinstance(payload, dict):
        return _json(payload)
    renderer = _RENDERERS.get(tool_name)
    if renderer is None:
        return _json(payload)
    return renderer(payload)
