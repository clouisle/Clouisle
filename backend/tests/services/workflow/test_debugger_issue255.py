from unittest.mock import AsyncMock, patch

import pytest

from app.services.workflow import debugger as debugger_module
from app.services.workflow.debugger import (
    BreakpointType,
    DebugAction,
    WorkflowDebugger,
)


@pytest.fixture
def redis():
    return AsyncMock()


@pytest.fixture
def workflow_debugger(redis):
    instance = WorkflowDebugger()
    instance._redis = redis
    return instance


@pytest.mark.asyncio
async def test_session_lifecycle_persists_and_cleans_state(workflow_debugger, redis):
    session = await workflow_debugger.create_session("run-1", "workflow-1")

    redis.setex.assert_awaited_once()
    assert await workflow_debugger.get_session(session.session_id) is session
    assert session.to_dict()["frame_count"] == 0

    await workflow_debugger.resume(session.session_id, DebugAction.STEP_INTO)
    await workflow_debugger.end_session(session.session_id)

    assert session.status == "stopped"
    assert await workflow_debugger.get_session(session.session_id) is None
    assert session.session_id not in workflow_debugger._action_events
    assert session.session_id not in workflow_debugger._pending_actions


@pytest.mark.asyncio
async def test_session_persistence_failure_is_non_fatal(workflow_debugger, redis):
    redis.setex.side_effect = ConnectionError("redis unavailable")

    session = await workflow_debugger.create_session("run-1", "workflow-1")

    assert await workflow_debugger.get_session(session.session_id) is session


@pytest.mark.asyncio
async def test_breakpoints_cover_node_condition_and_invalid_condition(
    workflow_debugger,
):
    session = await workflow_debugger.create_session("run-1", "workflow-1")
    node = await workflow_debugger.add_breakpoint(session.session_id, node_id="node-1")
    condition = await workflow_debugger.add_breakpoint(
        session.session_id,
        condition="count > 2",
        breakpoint_type=BreakpointType.CONDITION,
    )
    invalid = await workflow_debugger.add_breakpoint(
        session.session_id,
        condition="missing > 0",
        breakpoint_type=BreakpointType.CONDITION,
    )

    assert (
        await workflow_debugger.should_break(session.session_id, "other", {"count": 1})
        is False
    )
    assert (
        await workflow_debugger.should_break(session.session_id, "node-1", {}) is True
    )
    assert node.hit_count == 1
    assert (
        await workflow_debugger.toggle_breakpoint(session.session_id, node.id) is True
    )
    assert (
        await workflow_debugger.should_break(session.session_id, "other", {"count": 3})
        is True
    )
    assert condition.hit_count == 1
    condition.enabled = False
    assert (
        await workflow_debugger.should_break(session.session_id, "other", {}) is False
    )
    assert invalid.hit_count == 0

    assert (
        await workflow_debugger.remove_breakpoint(session.session_id, node.id) is True
    )
    assert node not in await workflow_debugger.get_breakpoints(session.session_id)
    assert (
        await workflow_debugger.toggle_breakpoint(session.session_id, "missing")
        is False
    )
    assert await workflow_debugger.get_breakpoints("missing") == []
    assert await workflow_debugger.should_break("missing", "node-1", {}) is False


@pytest.mark.asyncio
async def test_missing_session_breakpoint_boundaries(workflow_debugger):
    with pytest.raises(ValueError, match="Session not found"):
        await workflow_debugger.add_breakpoint("missing", node_id="node")

    assert await workflow_debugger.remove_breakpoint("missing", "breakpoint") is False
    assert await workflow_debugger.toggle_breakpoint("missing", "breakpoint") is False


@pytest.mark.asyncio
async def test_execution_controls_signal_actions_and_timeout(workflow_debugger):
    session = await workflow_debugger.create_session("run-1", "workflow-1")

    await workflow_debugger.pause(session.session_id)
    assert session.status == "paused"

    await workflow_debugger.resume(session.session_id, DebugAction.STEP_OVER)
    assert (
        await workflow_debugger.wait_for_action(session.session_id)
        == DebugAction.STEP_OVER
    )
    assert session.status == "running"

    assert (
        await workflow_debugger.wait_for_action(session.session_id, timeout=0)
        == DebugAction.STOP
    )

    await workflow_debugger.stop(session.session_id)
    assert session.status == "stopped"
    assert (
        await workflow_debugger.wait_for_action(session.session_id) == DebugAction.STOP
    )
    assert await workflow_debugger.wait_for_action("missing") == DebugAction.CONTINUE

    await workflow_debugger.pause("missing")
    await workflow_debugger.resume("missing")
    await workflow_debugger.stop("missing")


@pytest.mark.asyncio
async def test_frames_navigation_variables_and_execution_path(workflow_debugger):
    session = await workflow_debugger.create_session("run-1", "workflow-1")
    variables = {"count": 2}
    inputs = {"value": 1}
    outputs = {"value": 2}

    entered = await workflow_debugger.record_frame(
        session.session_id,
        "node-1",
        "code",
        "First",
        "enter",
        variables,
        inputs,
    )
    exited = await workflow_debugger.record_frame(
        session.session_id,
        "node-1",
        "code",
        "First",
        "exit",
        variables,
        inputs,
        outputs,
        duration_ms=12,
    )
    variables["count"] = 99
    outputs["value"] = 99

    assert entered.stack_depth == 1
    assert exited.stack_depth == 0
    assert exited.variables == {"count": 2}
    assert exited.outputs == {"value": 2}
    assert exited.to_dict()["timestamp"] == exited.timestamp.isoformat()
    assert await workflow_debugger.get_frames(session.session_id, 1, 1) == [exited]
    assert await workflow_debugger.get_current_frame(session.session_id) is exited
    assert await workflow_debugger.step_back(session.session_id) is entered
    assert await workflow_debugger.step_forward(session.session_id) is exited
    assert await workflow_debugger.goto_frame(session.session_id, 5) is None
    assert await workflow_debugger.get_variables(session.session_id, 0) == {"count": 2}
    assert await workflow_debugger.get_execution_path(session.session_id) == [
        {
            "node_id": "node-1",
            "node_type": "code",
            "node_label": "First",
            "timestamp": entered.timestamp.isoformat(),
        }
    ]
    assert await workflow_debugger.get_call_stack(session.session_id) == []


@pytest.mark.asyncio
async def test_frame_and_navigation_missing_boundaries(workflow_debugger):
    with pytest.raises(ValueError, match="Session not found"):
        await workflow_debugger.record_frame(
            "missing", "node", "code", "Node", "enter", {}, {}
        )

    assert await workflow_debugger.get_frames("missing") == []
    assert await workflow_debugger.get_current_frame("missing") is None
    assert await workflow_debugger.goto_frame("missing", 0) is None
    assert await workflow_debugger.step_back("missing") is None
    assert await workflow_debugger.step_forward("missing") is None
    assert await workflow_debugger.get_variables("missing") == {}
    assert await workflow_debugger.get_execution_path("missing") == []
    assert await workflow_debugger.get_call_stack("missing") == []


@pytest.mark.asyncio
async def test_expressions_and_watches_report_success_and_safe_errors(
    workflow_debugger,
):
    session = await workflow_debugger.create_session("run-1", "workflow-1")
    await workflow_debugger.record_frame(
        session.session_id,
        "node-1",
        "code",
        "First",
        "enter",
        {"items": [1, 2]},
        {},
    )

    assert await workflow_debugger.evaluate_expression(
        session.session_id, "len(items)"
    ) == {"success": True, "result": 2}
    with patch.object(
        debugger_module,
        "resolve_user_visible_error",
        return_value="safe error",
    ) as resolve_error:
        assert await workflow_debugger.evaluate_expression(
            session.session_id, "unknown"
        ) == {"success": False, "error": "safe error"}
    resolve_error.assert_called_once()

    assert await workflow_debugger.add_watch(session.session_id, "len(items)") is True
    assert await workflow_debugger.add_watch(session.session_id, "len(items)") is True
    assert await workflow_debugger.evaluate_watches(session.session_id) == {
        "len(items)": {"success": True, "result": 2}
    }
    assert (
        await workflow_debugger.remove_watch(session.session_id, "len(items)") is True
    )
    assert await workflow_debugger.remove_watch(session.session_id, "missing") is False
    assert await workflow_debugger.add_watch("missing", "value") is False
    assert await workflow_debugger.remove_watch("missing", "value") is False
    assert await workflow_debugger.evaluate_watches("missing") == {}


def test_debugger_singleton():
    with patch.object(debugger_module, "_debugger", None):
        assert debugger_module.get_debugger() is debugger_module.get_debugger()
