from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.workflow.debugger import (
    BreakpointType,
    DebugAction,
    WorkflowDebugger,
)


@pytest.mark.anyio
async def test_breakpoints_cover_node_condition_disabled_and_invalid_expression():
    debugger = WorkflowDebugger()
    with patch.object(debugger, "_save_session", new=AsyncMock()):
        session = await debugger.create_session("run", "workflow")

    disabled = await debugger.add_breakpoint(session.session_id, node_id="node")
    disabled.enabled = False
    conditional = await debugger.add_breakpoint(
        session.session_id,
        condition="value > 2",
        breakpoint_type=BreakpointType.CONDITION,
    )
    invalid = await debugger.add_breakpoint(
        session.session_id,
        condition="missing > 2",
        breakpoint_type=BreakpointType.CONDITION,
    )

    assert await debugger.should_break(session.session_id, "node", {"value": 3})
    assert conditional.hit_count == 1
    assert invalid.hit_count == 0
    assert not await debugger.should_break("missing", "node", {})
    assert await debugger.toggle_breakpoint(session.session_id, disabled.id)
    assert not await debugger.toggle_breakpoint(session.session_id, "missing")
    assert await debugger.remove_breakpoint(session.session_id, invalid.id)
    assert not await debugger.remove_breakpoint("missing", invalid.id)


@pytest.mark.anyio
async def test_frames_navigation_variables_watches_and_execution_path():
    debugger = WorkflowDebugger()
    with patch.object(debugger, "_save_session", new=AsyncMock()):
        session = await debugger.create_session("run", "workflow")

    entered = await debugger.record_frame(
        session.session_id, "node", "llm", "LLM", "enter", {"value": 2}, {}
    )
    await debugger.record_frame(
        session.session_id,
        "node",
        "llm",
        "LLM",
        "exit",
        {"value": 3},
        {},
        outputs={"answer": "ok"},
    )

    assert entered.stack_depth == 1
    assert session.call_stack == []
    assert (await debugger.step_back(session.session_id)) is entered
    assert (await debugger.step_forward(session.session_id)).outputs == {"answer": "ok"}
    assert await debugger.goto_frame(session.session_id, 9) is None
    assert await debugger.get_variables(session.session_id, 0) == {"value": 2}
    assert await debugger.add_watch(session.session_id, "value + 1")
    assert await debugger.add_watch(session.session_id, "value + 1")
    assert (await debugger.evaluate_watches(session.session_id))["value + 1"] == {
        "success": True,
        "result": 4,
    }
    assert not (await debugger.evaluate_expression(session.session_id, "missing"))[
        "success"
    ]
    assert await debugger.remove_watch(session.session_id, "value + 1")
    assert not await debugger.remove_watch(session.session_id, "value + 1")
    assert [
        item["node_id"]
        for item in await debugger.get_execution_path(session.session_id)
    ] == ["node"]


@pytest.mark.anyio
async def test_execution_controls_cover_signal_default_timeout_and_cleanup():
    debugger = WorkflowDebugger()
    with patch.object(debugger, "_save_session", new=AsyncMock()):
        session = await debugger.create_session("run", "workflow")

    await debugger.pause(session.session_id)
    assert session.status == "paused"
    await debugger.resume(session.session_id, DebugAction.STEP_OVER)
    assert (
        await debugger.wait_for_action(session.session_id, timeout=0.01)
        == DebugAction.STEP_OVER
    )
    assert await debugger.wait_for_action("missing") == DebugAction.CONTINUE
    assert (
        await debugger.wait_for_action(session.session_id, timeout=0)
        == DebugAction.STOP
    )

    await debugger.stop(session.session_id)
    assert (
        await debugger.wait_for_action(session.session_id, timeout=0.01)
        == DebugAction.STOP
    )
    await debugger.end_session(session.session_id)
    assert session.status == "stopped"
    assert await debugger.get_session(session.session_id) is None


@pytest.mark.anyio
async def test_save_session_ignores_redis_failure():
    debugger = WorkflowDebugger()
    debugger._redis = SimpleNamespace(setex=AsyncMock(side_effect=RuntimeError("down")))

    await debugger._save_session(SimpleNamespace(session_id="id", to_dict=lambda: {}))
