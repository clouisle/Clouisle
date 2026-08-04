"""Safe output denoising for the bash sandbox tool.

Only general-purpose noise removal - never content editing. Editing
responsibilities belong to a dedicated ``edit`` tool.

Capabilities (in application order):

1. ANSI cleanup          - strip colour/cursor escape sequences
2. progress-overwrite    - fold ``\\r`` progress bars to final state
3. blank-line compression - collapse runs of blank lines to one
4. repeated-line collapse - collapse long runs of identical lines
5. failure-diagnosis     - head+tail window on failed long output
6. structured-output guard - skip destructive steps for JSON
"""

from __future__ import annotations

import json
import re

from app.core.i18n import t

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

#: Lines of output beyond which a failure-diagnosis window is applied.
_MAX_LINES_BEFORE_WINDOW = 200
#: Lines retained from the head when windowing.
_WINDOW_HEAD = 20
#: Lines retained from the tail when windowing.
_WINDOW_TAIL = 40
#: Runs of identical consecutive lines longer than this are collapsed.
_COLLAPSE_THRESHOLD = 4

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

#: OSC sequences (title-set, hyperlinks, etc.) terminated by BEL or ST.
_ANSI_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
#: CSI sequences (SGR colours, cursor moves, erase, etc.).
_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
#: Other two-byte escape sequences (single-char after ESC).
_ANSI_OTHER_RE = re.compile(r"\x1b[@-_]")

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def denoise_output(text: str | None, *, failed: bool = False) -> str | None:
    """Apply safe output denoising to a command output stream.

    Non-destructive steps (ANSI cleanup, progress folding, blank-line
    compression) always run. Destructive steps (repeated-line collapse,
    failure-diagnosis windowing) are skipped when the output is structured
    JSON so that array shape and element counts are preserved.
    """
    if not text:
        return text

    cleaned = _strip_ansi(text)
    structured = _looks_structured(cleaned)
    cleaned = _fold_progress_overwrites(cleaned)
    cleaned = _compress_blank_lines(cleaned)

    if structured:
        return cleaned

    cleaned = _collapse_repeated_lines(cleaned)
    if failed:
        cleaned = _failure_window(cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Structured-output guard
# ---------------------------------------------------------------------------


def _looks_structured(text: str) -> bool:
    """Return True when *text* is parseable JSON (array or object)."""
    stripped = text.lstrip()
    if not stripped or stripped[0] not in "{[":
        return False
    try:
        json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return False
    return True


# ---------------------------------------------------------------------------
# 1. ANSI cleanup
# ---------------------------------------------------------------------------


def _strip_ansi(text: str) -> str:
    return _ANSI_OTHER_RE.sub("", _ANSI_CSI_RE.sub("", _ANSI_OSC_RE.sub("", text)))


# ---------------------------------------------------------------------------
# 2. progress-overwrite folding
# ---------------------------------------------------------------------------


def _fold_progress_overwrites(text: str) -> str:
    # Normalise Windows line endings first so trailing \r before \n is
    # not mistaken for a progress overwrite.
    text = text.replace("\r\n", "\n")
    if "\r" not in text:
        return text
    return "\n".join(line.split("\r")[-1] for line in text.split("\n"))


# ---------------------------------------------------------------------------
# 3. blank-line compression
# ---------------------------------------------------------------------------


def _compress_blank_lines(text: str) -> str:
    lines = text.split("\n")
    result: list[str] = []
    prev_blank = False
    for line in lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        result.append(line)
        prev_blank = is_blank
    return "\n".join(result)


# ---------------------------------------------------------------------------
# 4. collapsing consecutive repeated lines
# ---------------------------------------------------------------------------


def _collapse_repeated_lines(text: str) -> str:
    lines = text.split("\n")
    if len(lines) <= _COLLAPSE_THRESHOLD:
        return text
    result: list[str] = []
    i = 0
    while i < len(lines):
        run_end = i + 1
        while run_end < len(lines) and lines[run_end] == lines[i]:
            run_end += 1
        run_len = run_end - i
        if run_len > _COLLAPSE_THRESHOLD:
            result.append(lines[i])
            result.append(t("bash_output_repeated_lines", count=run_len))
        else:
            result.extend(lines[i:run_end])
        i = run_end
    return "\n".join(result)


# ---------------------------------------------------------------------------
# 5. failure-diagnosis window
# ---------------------------------------------------------------------------


def _failure_window(text: str) -> str:
    lines = text.splitlines()
    if len(lines) <= _MAX_LINES_BEFORE_WINDOW:
        return text
    head = lines[:_WINDOW_HEAD]
    tail = lines[-_WINDOW_TAIL:]
    omitted = len(lines) - _WINDOW_HEAD - _WINDOW_TAIL
    return "\n".join([*head, t("bash_output_lines_omitted", count=omitted), *tail])
