"""Tests for the bash output denoising module."""

from __future__ import annotations

import json

from unittest.mock import AsyncMock, patch

import pytest

from app.llm.tools.bash import BashSandboxTool
from app.llm.tools.bash_output import denoise_output
from app.services.sandbox.models import SandboxResult, SandboxTaskStatus


# ---------------------------------------------------------------------------
# 1. ANSI cleanup
# ---------------------------------------------------------------------------


def test_strip_ansi_sgr_colour_codes():
    text = "\x1b[32mok\x1b[0m\n\x1b[1;31merror\x1b[0m"
    assert denoise_output(text) == "ok\nerror"


def test_strip_ansi_colon_form_true_color():
    text = "\x1b[38:2::255:0:0mred\x1b[0m\x1b[38;5;208morange\x1b[0m"
    assert denoise_output(text) == "redorange"


def test_strip_ansi_osc_title_and_hyperlink():
    text = "\x1b]0;my title\x07visible\x1b]8;;https://x\x1b\\link\x1b]8;;\x1b\\"
    assert denoise_output(text) == "visiblelink"


def test_strip_ansi_cursor_and_single_char_escapes():
    text = "\x1b[2J\x1b[Hcleared\x1bM"
    assert denoise_output(text) == "cleared"


# ---------------------------------------------------------------------------
# 2. progress-overwrite folding
# ---------------------------------------------------------------------------


def test_fold_progress_overwrite_keeps_final_state():
    text = "downloading 10%\rdownloading 50%\rdownloading 100%\ndone\n"
    assert denoise_output(text) == "downloading 100%\ndone\n"


def test_fold_preserves_windows_line_endings():
    text = "line1\r\nline2\r\n"
    assert denoise_output(text) == "line1\nline2\n"


def test_fold_no_carriage_returns_unchanged():
    text = "plain output\nno cr here"
    assert denoise_output(text) == "plain output\nno cr here"


# ---------------------------------------------------------------------------
# 3. blank-line compression
# ---------------------------------------------------------------------------


def test_compress_blank_line_runs():
    text = "a\n\n\n\nb\n\n\nc"
    assert denoise_output(text) == "a\n\nb\n\nc"


def test_compress_leading_and_trailing_blanks():
    text = "\n\n\nhello\n\n"
    assert denoise_output(text) == "\nhello\n"


# ---------------------------------------------------------------------------
# 4. collapsing consecutive repeated lines
# ---------------------------------------------------------------------------


def test_collapse_long_run_of_identical_lines():
    text = "\n".join(["Downloading..."] * 10 + ["Done"])
    result = denoise_output(text)
    assert result == "Downloading...\n[repeated 10 times]\nDone"


def test_collapse_short_run_unchanged():
    text = "\n".join(["hi"] * 3 + ["bye"])
    assert denoise_output(text) == "hi\nhi\nhi\nbye"


def test_collapse_multiple_runs():
    text = "\n".join(["a"] * 6 + ["b"] * 5 + ["c"])
    result = denoise_output(text)
    assert result == "a\n[repeated 6 times]\nb\n[repeated 5 times]\nc"


def test_collapse_below_threshold_short_text_unchanged():
    text = "\n".join(["x"] * 3)
    assert denoise_output(text) == "x\nx\nx"


# ---------------------------------------------------------------------------
# 5. failure-diagnosis window
# ---------------------------------------------------------------------------


def test_failure_window_truncates_long_failed_output():
    text = "\n".join(f"line {i}" for i in range(250))
    result = denoise_output(text, failed=True)
    lines = result.split("\n")
    # 20 head + 1 marker + 40 tail = 61
    assert len(lines) == 61
    assert lines[20] == "... [190 lines omitted] ..."
    assert lines[0] == "line 0"
    assert lines[-1] == "line 249"


def test_failure_window_skipped_on_success():
    text = "\n".join(f"line {i}" for i in range(250))
    result = denoise_output(text, failed=False)
    assert result == text


def test_failure_window_skipped_for_short_output():
    text = "\n".join(f"line {i}" for i in range(100))
    result = denoise_output(text, failed=True)
    assert result == text


def test_failure_window_boundary_200_lines_with_trailing_newline():
    text = "\n".join(f"line {i}" for i in range(200)) + "\n"
    result = denoise_output(text, failed=True)
    assert result == text


# ---------------------------------------------------------------------------
# 6. structured-output guard
# ---------------------------------------------------------------------------


def test_structured_json_array_not_collapsed_on_failure():
    text = "[\n" + ",\n".join('  {"v": 1}' for _ in range(50)) + "\n]"
    result = denoise_output(text, failed=True)
    # JSON preserved - no windowing, no collapse
    assert result == text


def test_structured_json_object_keeps_repeated_values():
    text = '{"a": 1, "b": 1, "c": 1}'
    assert denoise_output(text) == text


def test_structured_json_with_ansi_still_cleaned():
    text = '\x1b[32m{"ok": true}\x1b[0m'
    assert denoise_output(text) == '{"ok": true}'


def test_structured_ansi_wrapped_json_not_windowed_on_failure():
    # ANSI-wrapped JSON exceeding 200 lines on failure must not be windowed
    inner = ",\n".join('  {"v": 1}' for _ in range(250))
    text = "\x1b[32m[\n" + inner + "\n]\x1b[0m"
    result = denoise_output(text, failed=True)
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) == 250


def test_non_json_starting_with_brace_not_protected():
    # Looks like JSON but isn't - destructive steps still apply
    text = "{not json}\n" * 10
    result = denoise_output(text, failed=False)
    assert "[repeated" in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_none_input_returns_none():
    assert denoise_output(None) is None


def test_empty_string_returns_empty():
    assert denoise_output("") == ""


def test_whitespace_only_compressed_to_single_blank():
    assert denoise_output("   \n   \n   ") == "   "


# ---------------------------------------------------------------------------
# Integration with BashSandboxTool
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_bash_tool_denoises_stdout_and_stderr():
    from pathlib import Path

    tool = BashSandboxTool(session_id="session-1", workspace_root="/workspace")
    workspace = type("Workspace", (), {"root": Path("/tmp/sessions/abc")})()
    fake_result = SandboxResult(
        job_id="job-1",
        success=False,
        status=SandboxTaskStatus.FAILED,
        stdout="\x1b[32mok\x1b[0m\n" + "\n".join(["step"] * 10),
        stderr="\x1b[31merr\x1b[0m\nprogress\n",
    )

    with (
        patch(
            "app.llm.tools.bash.sandbox_gateway.get_session_workspace",
            new=AsyncMock(return_value=workspace),
        ),
        patch(
            "app.llm.tools.bash.sandbox_gateway.submit_and_wait",
            new=AsyncMock(return_value=fake_result),
        ),
    ):
        result = await tool.execute(command="test", cwd="/workspace")

    assert result["stdout"] == "ok\nstep\n[repeated 10 times]"
    assert result["stderr"] == "err\nprogress\n"
