"""The tool test panel must not render a parked MCP call as a plain failure."""

from __future__ import annotations

from app.api.v1.endpoints.tools import _tool_test_response


def test_input_required_is_propagated_to_the_panel():
    raw = {
        "success": False,
        "result": None,
        "error": "MCP tool execution failed",
        "input_required": {
            "method": "tools/call",
            "requests": {"q1": {"method": "elicitation/create", "params": {}}},
            "request_state": "state-1",
        },
    }

    response = _tool_test_response(
        "demo_mcp", builtin=False, custom_type=None, raw=raw, started_at=0.0
    )

    assert response.input_required is not None
    assert response.input_required["request_state"] == "state-1"
    assert "q1" in response.input_required["requests"]


def test_absent_input_required_stays_none():
    response = _tool_test_response(
        "demo_mcp",
        builtin=False,
        custom_type=None,
        raw={"success": True, "result": "ok"},
        started_at=0.0,
    )

    assert response.input_required is None
