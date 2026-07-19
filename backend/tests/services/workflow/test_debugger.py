"""Behavioral tests for the workflow debugger."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.services.workflow.debugger import (
    BreakpointType,
    DebugAction,
    WorkflowDebugger,
)


@pytest_asyncio.fixture
async def debugger_and_session():
    debugger = WorkflowDebugger()
    debugger._save_session = AsyncMock()
    session = await debugger.create_session("run-1", "workflow-1")
    return debugger, session


@pytest.mark.asyncio
async def test_session_lifecycle_and_execution_control(debugger_and_session):
    debugger, session = debugger_and_session

    assert await debugger.get_session(session.session_id) is session
    assert session.to_dict()["status"] == "running"
    debugger._save_session.assert_awaited_once_with(session)

    await debugger.pause(session.session_id)
    assert session.status == "paused"

    await debugger.resume(session.session_id, DebugAction.STEP_INTO)
    assert session.status == "running"
    assert (
        await debugger.wait_for_action(session.session_id, timeout=0.01)
        is DebugAction.STEP_INTO
    )

    await debugger.stop(session.session_id)
    assert session.status == "stopped"
    assert (
        await debugger.wait_for_action(session.session_id, timeout=0.01)
        is DebugAction.STOP
    )

    await debugger.end_session(session.session_id)
    assert await debugger.get_session(session.session_id) is None
    assert (
        await debugger.wait_for_action(session.session_id, timeout=0.01)
        is DebugAction.CONTINUE
    )


@pytest.mark.asyncio
async def test_breakpoints_match_toggle_and_remove(debugger_and_session):
    debugger, session = debugger_and_session
    node_breakpoint = await debugger.add_breakpoint(
        session.session_id, node_id="node-1"
    )
    condition_breakpoint = await debugger.add_breakpoint(
        session.session_id,
        condition="count > 2",
        breakpoint_type=BreakpointType.CONDITION,
    )

    assert (
        await debugger.should_break(session.session_id, "other", {"count": 3}) is True
    )
    assert condition_breakpoint.hit_count == 1
    assert (
        await debugger.should_break(session.session_id, "node-1", {"count": 0}) is True
    )
    assert node_breakpoint.hit_count == 1

    assert (
        await debugger.toggle_breakpoint(session.session_id, node_breakpoint.id) is True
    )
    assert (
        await debugger.should_break(session.session_id, "node-1", {"count": 0}) is False
    )
    assert await debugger.toggle_breakpoint(session.session_id, "missing") is False

    assert (
        await debugger.remove_breakpoint(session.session_id, condition_breakpoint.id)
        is True
    )
    assert await debugger.get_breakpoints(session.session_id) == [node_breakpoint]


@pytest.mark.asyncio
async def test_invalid_breakpoint_condition_is_ignored(debugger_and_session, caplog):
    debugger, session = debugger_and_session
    breakpoint = await debugger.add_breakpoint(
        session.session_id,
        condition="missing > 0",
        breakpoint_type=BreakpointType.CONDITION,
    )

    assert await debugger.should_break(session.session_id, "node-1", {}) is False
    assert breakpoint.hit_count == 0
    assert "Breakpoint condition error" in caplog.text


@pytest.mark.asyncio
async def test_frames_expose_state_history_and_call_stack(debugger_and_session):
    debugger, session = debugger_and_session
    variables = {"count": 1}
    enter = await debugger.record_frame(
        session.session_id,
        "node-1",
        "code",
        "First",
        "enter",
        variables,
        {"value": 1},
    )
    variables["count"] = 99
    exit_frame = await debugger.record_frame(
        session.session_id,
        "node-1",
        "code",
        "First",
        "exit",
        {"count": 2},
        {},
        outputs={"result": "done"},
        duration_ms=12,
    )

    assert enter.variables == {"count": 1}
    assert enter.stack_depth == 1
    assert exit_frame.stack_depth == 0
    assert await debugger.get_call_stack(session.session_id) == []
    assert await debugger.get_current_frame(session.session_id) is exit_frame
    assert await debugger.get_variables(session.session_id) == {"count": 2}
    assert await debugger.get_variables(session.session_id, 0) == {"count": 1}
    assert await debugger.get_frames(session.session_id, start=1, limit=1) == [
        exit_frame
    ]
    assert [
        item["node_id"]
        for item in await debugger.get_execution_path(session.session_id)
    ] == ["node-1"]


@pytest.mark.asyncio
async def test_frame_navigation_steps_within_recorded_history(debugger_and_session):
    debugger, session = debugger_and_session
    frames = []
    for node_id in ("one", "two", "three"):
        frames.append(
            await debugger.record_frame(
                session.session_id, node_id, "code", node_id.title(), "enter", {}, {}
            )
        )

    assert await debugger.goto_frame(session.session_id, 1) is frames[1]
    assert await debugger.step_back(session.session_id) is frames[0]
    assert await debugger.step_back(session.session_id) is None
    assert await debugger.step_forward(session.session_id) is frames[1]
    assert await debugger.step_forward(session.session_id) is frames[2]
    assert await debugger.step_forward(session.session_id) is None
    assert await debugger.goto_frame(session.session_id, 99) is None


@pytest.mark.asyncio
async def test_watches_and_error_paths(debugger_and_session):
    debugger, session = debugger_and_session
    await debugger.record_frame(
        session.session_id,
        "node-1",
        "code",
        "First",
        "error",
        {"items": [1, 2]},
        {},
        error="boom",
    )

    assert await debugger.add_watch(session.session_id, "len(items)") is True
    assert await debugger.add_watch(session.session_id, "len(items)") is True
    assert await debugger.add_watch(session.session_id, "missing") is True
    results = await debugger.evaluate_watches(session.session_id)
    assert results["len(items)"] == {"success": True, "result": 2}
    assert results["missing"]["success"] is False
    assert results["missing"]["error"]
    assert await debugger.remove_watch(session.session_id, "len(items)") is True
    assert await debugger.remove_watch(session.session_id, "len(items)") is False

    with pytest.raises(ValueError, match="Session not found: missing"):
        await debugger.add_breakpoint("missing")
    with pytest.raises(ValueError, match="Session not found: missing"):
        await debugger.record_frame("missing", "node", "code", "Node", "enter", {}, {})

    assert await debugger.get_frames("missing") == []
    assert await debugger.get_variables("missing") == {}
    assert await debugger.evaluate_watches("missing") == {}
    assert await debugger.remove_breakpoint("missing", "breakpoint") is False
