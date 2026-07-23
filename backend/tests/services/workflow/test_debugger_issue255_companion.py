from uuid import uuid4

import pytest

from app.services.workflow import debugger as debugger_module
from app.services.workflow.debugger import (
    BreakpointType,
    DebugAction,
    WorkflowDebugger,
    get_debugger,
)


@pytest.fixture
def workflow_debugger():
    return WorkflowDebugger()


@pytest.mark.asyncio
async def test_should_break_skips_disabled_node_and_handles_condition_branches(
    workflow_debugger,
):
    session = await workflow_debugger.create_session(str(uuid4()), str(uuid4()))
    disabled = await workflow_debugger.add_breakpoint(session.session_id, node_id="llm")
    disabled.enabled = False
    matching_condition = await workflow_debugger.add_breakpoint(
        session.session_id,
        condition="score > 2",
        breakpoint_type=BreakpointType.CONDITION,
    )
    failing_condition = await workflow_debugger.add_breakpoint(
        session.session_id,
        condition="missing + 1",
        breakpoint_type=BreakpointType.CONDITION,
    )

    assert await workflow_debugger.should_break(session.session_id, "llm", {"score": 3})
    assert matching_condition.hit_count == 1
    assert disabled.hit_count == 0

    assert not await workflow_debugger.should_break(
        session.session_id, "other", {"score": 0}
    )
    assert failing_condition.hit_count == 0
    assert not await workflow_debugger.should_break("missing-session", "llm", {})


@pytest.mark.asyncio
async def test_frame_navigation_variables_watches_and_invalid_expression(
    workflow_debugger,
):
    session = await workflow_debugger.create_session(str(uuid4()), str(uuid4()))

    enter_frame = await workflow_debugger.record_frame(
        session.session_id,
        node_id="start",
        node_type="input",
        node_label="Start",
        action="enter",
        variables={"items": [1, 2], "count": 2},
        inputs={"query": "hello"},
    )
    exit_frame = await workflow_debugger.record_frame(
        session.session_id,
        node_id="start",
        node_type="input",
        node_label="Start",
        action="exit",
        variables={"items": [1, 2, 3], "count": 3},
        inputs={},
        outputs={"query": "hello"},
        duration_ms=5,
    )

    assert await workflow_debugger.get_current_frame(session.session_id) == exit_frame
    assert await workflow_debugger.step_back(session.session_id) == enter_frame
    assert await workflow_debugger.step_back(session.session_id) is None
    assert await workflow_debugger.step_forward(session.session_id) == exit_frame
    assert await workflow_debugger.goto_frame(session.session_id, 99) is None
    assert await workflow_debugger.get_variables(session.session_id) == {
        "items": [1, 2, 3],
        "count": 3,
    }

    assert await workflow_debugger.evaluate_expression(
        session.session_id, "len(items)", frame_index=0
    ) == {"success": True, "result": 2}
    invalid = await workflow_debugger.evaluate_expression(
        session.session_id, "items[10]", frame_index=0
    )
    assert invalid["success"] is False
    assert invalid["error"]

    assert await workflow_debugger.add_watch(session.session_id, "count + 1")
    assert await workflow_debugger.add_watch(session.session_id, "count + 1")
    assert session.watches == ["count + 1"]
    assert await workflow_debugger.evaluate_watches(session.session_id) == {
        "count + 1": {"success": True, "result": 4}
    }
    assert await workflow_debugger.remove_watch(session.session_id, "count + 1")
    assert not await workflow_debugger.remove_watch(session.session_id, "count + 1")
    assert await workflow_debugger.evaluate_watches("missing-session") == {}

    assert await workflow_debugger.get_execution_path(session.session_id) == [
        {
            "node_id": "start",
            "node_type": "input",
            "node_label": "Start",
            "timestamp": enter_frame.timestamp.isoformat(),
        }
    ]
    assert await workflow_debugger.get_call_stack(session.session_id) == []


@pytest.mark.asyncio
async def test_control_branches_and_global_debugger_singleton(workflow_debugger):
    session = await workflow_debugger.create_session(str(uuid4()), str(uuid4()))

    assert (
        await workflow_debugger.wait_for_action("missing-session")
        == DebugAction.CONTINUE
    )

    await workflow_debugger.pause(session.session_id)
    assert session.status == "paused"

    await workflow_debugger.resume(session.session_id, DebugAction.STEP_OVER)
    assert session.status == "running"
    assert (
        await workflow_debugger.wait_for_action(session.session_id, timeout=0.1)
        == DebugAction.STEP_OVER
    )

    await workflow_debugger.stop(session.session_id)
    assert session.status == "stopped"
    assert (
        await workflow_debugger.wait_for_action(session.session_id, timeout=0.1)
        == DebugAction.STOP
    )

    await workflow_debugger.end_session(session.session_id)
    assert await workflow_debugger.get_session(session.session_id) is None

    debugger_module._debugger = None
    try:
        first = get_debugger()
        assert get_debugger() is first
    finally:
        debugger_module._debugger = None
