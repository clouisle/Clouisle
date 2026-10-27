"""Workflow approval state edges.

These pin decisions a workflow consumer can observe but the main approval
suite does not reach: how a terminal execution is reported after resume, what
a missing/naive approval deadline means, what happens when resume dispatching
loses its broker, and how a park-race check behaves without a usable approval
record. They also pin the two access decisions that gate whether a tool or
knowledge node may produce output at all: a team share never widens a PRIVATE
tool, and a PRIVATE knowledge base stays unreadable to a non-creator run.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from app.models.knowledge_base import KnowledgeBase
from app.models.tool import ToolVisibility
from app.models.workflow import RunStatus
from app.schemas.tool_approval import (
    ExecutionRunKind,
    ToolExecutionStatus,
)
from app.services.workflow import tool_approval_resume as resume
from app.services.workflow.executors.knowledge import KnowledgeRetrievalNodeExecutor
from app.services.workflow.executors.tool import ToolNodeExecutor


def _execution(**overrides):
    values = {
        "id": uuid4(),
        "run_kind": ExecutionRunKind.WORKFLOW,
        "run_id": uuid4(),
        "status": ToolExecutionStatus.SUCCEEDED,
        "cancel_reason": None,
        "expires_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_terminal_execution_status_maps_to_the_node_failure_key():
    assert (
        resume.terminal_execution_error(
            _execution(status=ToolExecutionStatus.OUTCOME_UNKNOWN)
        )
        == "tool_execution_outcome_unknown"
    )
    assert (
        resume.terminal_execution_error(_execution(status=ToolExecutionStatus.FAILED))
        == "tool_execution_failed"
    )
    succeeded = _execution(status=ToolExecutionStatus.SUCCEEDED)
    assert resume.terminal_execution_error(succeeded) is None


def test_pending_execution_without_an_expiry_never_expires():
    assert resume.approval_deadline_passed(_execution(expires_at=None)) is False


def test_naive_deadline_is_read_as_utc_and_the_boundary_counts_as_passed():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    assert (
        resume.approval_deadline_passed(
            _execution(expires_at=datetime(2026, 1, 1, 11, 59, 59)), now=now
        )
        is True
    )
    assert (
        resume.approval_deadline_passed(
            _execution(expires_at=datetime(2026, 1, 1, 12, 0)), now=now
        )
        is True
    )
    assert (
        resume.approval_deadline_passed(
            _execution(expires_at=datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)),
            now=now,
        )
        is False
    )


@pytest.mark.asyncio
async def test_execution_without_a_run_is_never_queued_for_resume():
    with patch.object(resume.WorkflowRun, "filter") as run_filter:
        assert (
            await resume.queue_workflow_run_approval_resume(_execution(run_id=None))
            is None
        )

    run_filter.assert_not_called()


@pytest.mark.asyncio
async def test_broker_outage_does_not_turn_an_approved_run_into_a_failure(caplog):
    run = SimpleNamespace(id=uuid4())
    execution = _execution()

    with (
        patch.object(
            resume,
            "queue_workflow_run_approval_resume",
            new=AsyncMock(return_value=run),
        ),
        patch(
            "app.tasks.workflow.resume_workflow_task.delay",
            side_effect=ConnectionError("broker down"),
        ),
        caplog.at_level(logging.WARNING),
    ):
        resumed = await resume.schedule_workflow_run_approval_resume(execution)

    # The decision is already committed; a failed dispatch is only logged.
    assert resumed is run
    assert "Failed to schedule workflow resume" in caplog.text


@pytest.mark.asyncio
async def test_resume_by_execution_id_reports_whether_a_waiting_run_was_dispatched():
    execution = _execution()
    waiting_run = SimpleNamespace(id=uuid4(), status=RunStatus.WAITING)

    with (
        patch.object(resume.ToolExecution, "filter") as execution_filter,
        patch.object(resume.WorkflowRun, "filter") as run_filter,
        patch("app.tasks.workflow.resume_workflow_task.delay") as dispatch,
    ):
        run_filter.return_value.first = AsyncMock(return_value=waiting_run)

        execution_filter.return_value.first = AsyncMock(return_value=execution)
        assert await resume.schedule_workflow_resume_for_execution(execution.id) is True
        dispatch.assert_called_once_with(str(waiting_run.id))

        # A decision for an execution that no longer exists commits nothing.
        execution_filter.return_value.first = AsyncMock(return_value=None)
        assert await resume.schedule_workflow_resume_for_execution(uuid4()) is False
        dispatch.assert_called_once_with(str(waiting_run.id))


@pytest.mark.asyncio
async def test_park_race_check_skips_runs_without_a_tool_attempt():
    run = SimpleNamespace(id=uuid4())

    with (
        patch.object(resume.NodeExecution, "filter") as node_filter,
        patch.object(resume, "find_execution_for_token", new=AsyncMock()) as find,
    ):
        node_filter.return_value.order_by.return_value.first = AsyncMock(
            return_value=None
        )
        assert await resume.ensure_resume_after_park(run, "tool_1") is False

        node_filter.return_value.order_by.return_value.first = AsyncMock(
            return_value=SimpleNamespace(id=uuid4(), node_type="pause")
        )
        assert await resume.ensure_resume_after_park(run, "pause_1") is False

    find.assert_not_awaited()


@pytest.mark.asyncio
async def test_park_race_check_skips_a_tool_attempt_without_a_deferred_execution():
    run = SimpleNamespace(id=uuid4())
    node = SimpleNamespace(id=uuid4(), node_type="tool")

    with (
        patch.object(resume.NodeExecution, "filter") as node_filter,
        patch.object(
            resume, "find_execution_for_token", new=AsyncMock(return_value=None)
        ),
        patch.object(
            resume, "schedule_workflow_run_approval_resume", new=AsyncMock()
        ) as schedule,
    ):
        node_filter.return_value.order_by.return_value.first = AsyncMock(
            return_value=node
        )
        assert await resume.ensure_resume_after_park(run, "tool_1") is False

    schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_park_race_check_failure_leaves_the_run_parked(caplog):
    run = SimpleNamespace(id=uuid4())

    with (
        patch.object(
            resume.NodeExecution,
            "filter",
            Mock(side_effect=RuntimeError("db down")),
        ),
        caplog.at_level(logging.WARNING),
    ):
        assert await resume.ensure_resume_after_park(run, "tool_1") is False

    assert "Failed to check approval resume state" in caplog.text


def _tool_context():
    context = MagicMock()
    context.resolve_variable_ref = AsyncMock()
    return context


def _team_workflow_filter():
    return patch("app.models.workflow.Workflow.filter")


@pytest.mark.asyncio
async def test_a_team_share_does_not_expose_a_private_tool():
    tool = SimpleNamespace(
        id="tool-123",
        team_id="other-team",
        visibility=ToolVisibility.PRIVATE,
        created_by_id="owner-2",
        type="custom",
        name="private-query",
    )
    run = SimpleNamespace(
        id="run-1",
        workflow_id="workflow-1",
        triggered_by_id="user-1",
        context_snapshot={},
    )
    share_query = MagicMock()
    share_query.exists = AsyncMock(return_value=True)

    with (
        _team_workflow_filter() as workflow_filter,
        patch("app.models.tool.Tool.filter") as tool_filter,
        patch("app.models.tool.ToolShare.filter", return_value=share_query),
        patch("app.services.tool.ToolExecutor.execute", new=AsyncMock()) as execute,
    ):
        workflow_filter.return_value.only.return_value.first = AsyncMock(
            return_value=SimpleNamespace(team_id="team-1")
        )
        tool_filter.return_value.first = AsyncMock(return_value=tool)

        result = await ToolNodeExecutor().execute(
            {"id": "tool_1", "data": {"toolConfig": {"toolId": "tool-123"}}},
            _tool_context(),
            run,
        )

    # A share row exists, but PRIVATE still means creator-only.
    assert result.error == "tool_not_found"
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_team_share_lets_a_shared_tool_run_for_the_workflow_team():
    tool = SimpleNamespace(
        id="tool-123",
        team_id="other-team",
        visibility=ToolVisibility.TEAM,
        created_by_id="owner-2",
        type="custom",
        name="shared-query",
    )
    run = SimpleNamespace(
        id="run-1",
        workflow_id="workflow-1",
        triggered_by_id="user-1",
        context_snapshot={},
    )
    share_query = MagicMock()
    share_query.exists = AsyncMock(return_value=True)
    boundary = AsyncMock(return_value={"ok": True})

    with (
        _team_workflow_filter() as workflow_filter,
        patch("app.models.tool.Tool.filter") as tool_filter,
        patch("app.models.tool.ToolShare.filter", return_value=share_query),
        patch(
            "app.models.user.User.get_or_none",
            new=AsyncMock(return_value=SimpleNamespace(id="user-1")),
        ),
        patch(
            "app.services.workflow.tool_approval_resume.token_for_attempt",
            new=AsyncMock(return_value="call-1"),
        ),
        patch(
            "app.services.workflow.tool_approval_resume.find_execution_for_token",
            new=AsyncMock(return_value=None),
        ),
        patch("app.services.tool.ToolExecutor.execute", new=boundary),
    ):
        workflow_filter.return_value.only.return_value.first = AsyncMock(
            return_value=SimpleNamespace(team_id="team-1")
        )
        tool_filter.return_value.first = AsyncMock(return_value=tool)

        result = await ToolNodeExecutor().execute(
            {"id": "tool_1", "data": {"toolConfig": {"toolId": "tool-123"}}},
            _tool_context(),
            run,
        )

    assert result.success is True
    assert result.outputs["result"] == {"ok": True}
    kwargs = boundary.await_args.kwargs
    assert kwargs["team_id"] == "team-1"
    assert kwargs["context"].run_kind is ExecutionRunKind.WORKFLOW


@pytest.mark.asyncio
async def test_failed_tool_node_blanks_a_custom_output_variable():
    run = SimpleNamespace(
        id="run-1",
        workflow_id="workflow-1",
        triggered_by_id=None,
        context_snapshot={},
    )

    with _team_workflow_filter() as workflow_filter:
        workflow_filter.return_value.only.return_value.first = AsyncMock(
            return_value=SimpleNamespace(team_id="team-1")
        )
        result = await ToolNodeExecutor().execute(
            {
                "id": "tool_1",
                "data": {
                    "toolConfig": {
                        "toolType": "builtin",
                        "toolName": "get_current_time",
                        "outputVariable": "searchResult",
                    }
                },
            },
            _tool_context(),
            run,
        )

    assert result.error == "user_context_required"
    # Downstream references must see an explicit empty value, never stale data.
    assert result.outputs["searchResult"] is None
    assert result.outputs["result"] is None


@pytest.mark.asyncio
async def test_tool_executor_crash_is_reported_and_blanks_the_custom_output():
    tool = SimpleNamespace(
        id="tool-123",
        team_id="team-1",
        visibility=ToolVisibility.TEAM,
        created_by_id="user-1",
        type="custom",
        name="broken-query",
    )
    run = SimpleNamespace(
        id="run-1",
        workflow_id="workflow-1",
        triggered_by_id="user-1",
        context_snapshot={},
    )

    with (
        _team_workflow_filter() as workflow_filter,
        patch("app.models.tool.Tool.filter") as tool_filter,
        patch(
            "app.models.user.User.get_or_none",
            new=AsyncMock(return_value=SimpleNamespace(id="user-1")),
        ),
        patch(
            "app.services.workflow.tool_approval_resume.token_for_attempt",
            new=AsyncMock(return_value="call-1"),
        ),
        patch(
            "app.services.workflow.tool_approval_resume.find_execution_for_token",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.services.tool.ToolExecutor.execute",
            new=AsyncMock(side_effect=RuntimeError("adapter exploded")),
        ),
    ):
        workflow_filter.return_value.only.return_value.first = AsyncMock(
            return_value=SimpleNamespace(team_id="team-1")
        )
        tool_filter.return_value.first = AsyncMock(return_value=tool)

        result = await ToolNodeExecutor().execute(
            {
                "id": "tool_1",
                "data": {
                    "toolConfig": {
                        "toolId": "tool-123",
                        "outputVariable": "searchResult",
                    }
                },
            },
            _tool_context(),
            run,
        )

    assert result.error is not None
    assert result.outputs["status"] == "error"
    assert result.outputs["searchResult"] is None


class _KnowledgeBaseQuery:
    def __init__(self, kb):
        self._kb = kb

    def prefetch_related(self, *_args, **_kwargs):
        return self

    async def first(self):
        return self._kb


def _knowledge_node(kb_id):
    return {
        "data": {
            "knowledgeRetrievalConfig": {
                "knowledgeBaseId": str(kb_id),
                "querySource": "constant",
                "queryConstantValue": "policy text",
            }
        }
    }


def _knowledge_run(workflow_id, user_id):
    return SimpleNamespace(workflow_id=workflow_id, triggered_by_id=user_id)


def _private_kb(**overrides):
    values = {
        "id": uuid4(),
        "name": "secret",
        "team_id": uuid4(),
        "status": "active",
        "embedding_model_id": None,
        "rerank_model_id": None,
        "settings": {},
        "visibility": "private",
        "created_by_id": uuid4(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_private_knowledge_base_is_hidden_from_a_non_creator_run():
    workflow_id = uuid4()
    kb = _private_kb()
    run = _knowledge_run(workflow_id, uuid4())

    with (
        _team_workflow_filter() as workflow_filter,
        patch.object(KnowledgeBase, "filter", return_value=_KnowledgeBaseQuery(kb)),
        patch("app.services.retrieval.retrieve", new=AsyncMock()) as retrieve,
    ):
        workflow_filter.return_value.only.return_value.first = AsyncMock(
            return_value=SimpleNamespace(team_id=kb.team_id)
        )
        result = await KnowledgeRetrievalNodeExecutor().execute(
            _knowledge_node(kb.id), MagicMock(), run
        )

    assert result.error == "not_found"
    retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_knowledge_base_falls_back_to_the_creator_relation():
    workflow_id = uuid4()
    creator_id = uuid4()
    kb = _private_kb(created_by_id=None, created_by=SimpleNamespace(id=creator_id))
    run = _knowledge_run(workflow_id, uuid4())

    with (
        _team_workflow_filter() as workflow_filter,
        patch.object(KnowledgeBase, "filter", return_value=_KnowledgeBaseQuery(kb)),
        patch("app.services.retrieval.retrieve", new=AsyncMock()) as retrieve,
    ):
        workflow_filter.return_value.only.return_value.first = AsyncMock(
            return_value=SimpleNamespace(team_id=kb.team_id)
        )
        result = await KnowledgeRetrievalNodeExecutor().execute(
            _knowledge_node(kb.id), MagicMock(), run
        )

    assert result.error == "not_found"
    retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_private_knowledge_base_remains_available_to_its_creator():
    workflow_id = uuid4()
    creator_id = uuid4()
    document_id, chunk_id = uuid4(), uuid4()
    kb = _private_kb(created_by_id=creator_id)
    run = _knowledge_run(workflow_id, creator_id)
    response = SimpleNamespace(
        results=[
            {
                "document_id": document_id,
                "chunk_id": chunk_id,
                "content": "section 1",
                "score": 0.87,
                "metadata": {"page": 2},
            }
        ]
    )
    retrieve = AsyncMock(return_value=response)

    with (
        _team_workflow_filter() as workflow_filter,
        patch.object(KnowledgeBase, "filter", return_value=_KnowledgeBaseQuery(kb)),
        patch("app.services.retrieval.retrieve", new=retrieve),
    ):
        workflow_filter.return_value.only.return_value.first = AsyncMock(
            return_value=SimpleNamespace(team_id=kb.team_id)
        )
        result = await KnowledgeRetrievalNodeExecutor().execute(
            _knowledge_node(kb.id), MagicMock(), run
        )

    assert result.error is None
    assert result.outputs["results"][0]["documentId"] == str(document_id)
    assert result.outputs["results"][0]["chunkId"] == str(chunk_id)
    assert result.outputs["context"] == "section 1"
    assert result.outputs["totalFound"] == 1


@pytest.mark.asyncio
async def test_knowledge_node_without_a_workflow_run_fails_closed():
    with _team_workflow_filter() as workflow_filter:
        result = await KnowledgeRetrievalNodeExecutor().execute(
            _knowledge_node(uuid4()),
            MagicMock(),
            _knowledge_run(None, uuid4()),
        )

    assert result.error == "not_found"
    workflow_filter.assert_not_called()
