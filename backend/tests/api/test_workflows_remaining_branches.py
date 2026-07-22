from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import workflows
from app.models.workflow import (
    RunStatus,
    TriggerType,
    WorkflowStatus,
    WorkflowVisibility,
)
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.workflow import WorkflowCreate, WorkflowRunRequest, WorkflowUpdate
from app.tasks.workflow import run_workflow_task


class Query:
    def __init__(self, *, first=None, items=None, total=0):
        self.first_value = first
        self.items = items or []
        self.total = total
        self.filters = []

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def exclude(self, **kwargs):
        self.excluded = kwargs
        return self

    def prefetch_related(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, _value):
        return self

    def limit(self, _value):
        return self

    async def first(self):
        return self.first_value

    async def count(self):
        return self.total

    def __await__(self):
        async def result():
            return self.items

        return result().__await__()


class Dump:
    def __init__(self, value):
        self.value = value

    def model_dump(self):
        return self.value


def patch_dump_schema(monkeypatch, schema, value):
    monkeypatch.setattr(schema, "model_validate", Mock(return_value=Dump(value)))


@pytest.mark.asyncio
async def test_create_workflow_rejects_duplicate_name(monkeypatch):
    workflow_create = AsyncMock()
    monkeypatch.setattr(workflows.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(workflows, "check_team_access", AsyncMock())
    monkeypatch.setattr(
        workflows.Workflow, "filter", Mock(return_value=Query(first=object()))
    )
    monkeypatch.setattr(workflows.Workflow, "create", workflow_create)

    with pytest.raises(BusinessError) as exc_info:
        await workflows.create_workflow(
            workflow_in=WorkflowCreate(team_id=uuid4(), name="Existing"),
            request=SimpleNamespace(),
            current_user=SimpleNamespace(),
        )

    assert exc_info.value.code == ResponseCode.DUPLICATE_NAME
    assert exc_info.value.msg_key == "workflow_name_exists"
    workflow_create.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_workflow_builds_default_definition_and_audits(monkeypatch):
    team_id, workflow_id = uuid4(), uuid4()
    user = SimpleNamespace(id=uuid4())
    team = SimpleNamespace(id=team_id)
    created = SimpleNamespace(id=workflow_id, name="New flow")
    reloaded = SimpleNamespace(id=workflow_id)
    create = AsyncMock(return_value=created)
    audit = AsyncMock()

    monkeypatch.setattr(workflows.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(workflows, "check_team_access", AsyncMock(return_value=team))
    monkeypatch.setattr(workflows.Workflow, "filter", Mock(return_value=Query()))
    monkeypatch.setattr(workflows.Workflow, "create", create)
    monkeypatch.setattr(
        workflows.Workflow, "get", Mock(return_value=Query(first=reloaded))
    )
    monkeypatch.setattr(workflows.AuditLogService, "log", audit)
    patch_dump_schema(monkeypatch, workflows.WorkflowOut, {"id": workflow_id})

    response = await workflows.create_workflow(
        workflow_in=WorkflowCreate(team_id=team_id, name="New flow"),
        request=SimpleNamespace(),
        current_user=user,
    )

    definition = create.await_args.kwargs["definition"]
    assert definition["nodes"][0]["type"] == "user_input"
    assert definition["edges"] == []
    assert create.await_args.kwargs["team"] is team
    assert audit.await_args.kwargs["action"] == "create_workflow"
    assert response["data"] == {"id": workflow_id}


@pytest.mark.asyncio
async def test_update_workflow_rejects_duplicate_renamed_workflow(monkeypatch):
    workflow_id = uuid4()
    workflow = SimpleNamespace(id=workflow_id, team_id=uuid4(), name="Old")
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(workflows.deps, "check_scoped_permission", AsyncMock())
    duplicate_query = Query(first=object())
    monkeypatch.setattr(
        workflows.Workflow, "filter", Mock(return_value=duplicate_query)
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.update_workflow(
            workflow_id=workflow_id,
            workflow_in=WorkflowUpdate(name="Taken"),
            request=SimpleNamespace(),
            current_user=SimpleNamespace(),
        )

    assert exc_info.value.code == ResponseCode.DUPLICATE_NAME
    assert duplicate_query.excluded == {"id": workflow_id}


@pytest.mark.asyncio
async def test_update_workflow_applies_fields_increments_version_and_audits(
    monkeypatch,
):
    workflow_id = uuid4()
    workflow = SimpleNamespace(
        id=workflow_id,
        team_id=uuid4(),
        name="Same",
        version=3,
        save=AsyncMock(),
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(workflows.deps, "check_scoped_permission", AsyncMock())
    monkeypatch.setattr(
        workflows.Workflow, "get", Mock(return_value=Query(first=workflow))
    )
    monkeypatch.setattr(workflows.AuditLogService, "log", audit)
    patch_dump_schema(monkeypatch, workflows.WorkflowOut, {"id": workflow_id})

    await workflows.update_workflow(
        workflow_id=workflow_id,
        workflow_in=WorkflowUpdate(
            name="Same",
            description="Description",
            icon="icon",
            definition={"nodes": []},
            variables=[{"name": "query"}],
            trigger_type=TriggerType.WEBHOOK,
            trigger_config={"enabled": True},
            visibility="team",
            embed_config={"enabled": True},
        ),
        request=SimpleNamespace(),
        current_user=SimpleNamespace(),
    )

    assert workflow.version == 4
    assert workflow.visibility == WorkflowVisibility.TEAM
    assert workflow.embed_config == {"enabled": True}
    workflow.save.assert_awaited_once()
    assert audit.await_args.kwargs["action"] == "update_workflow"


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_version", [object(), None])
async def test_publish_workflow_only_creates_missing_snapshot(
    monkeypatch, existing_version
):
    workflow_id = uuid4()
    workflow = SimpleNamespace(
        id=workflow_id,
        version=2,
        definition={"nodes": []},
        variables=[],
        trigger_type=TriggerType.MANUAL,
        trigger_config={},
        name="Flow",
        status=WorkflowStatus.DRAFT,
        save=AsyncMock(),
    )
    version_create = AsyncMock()
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        workflows.WorkflowVersion,
        "filter",
        Mock(return_value=Query(first=existing_version)),
    )
    monkeypatch.setattr(workflows.WorkflowVersion, "create", version_create)
    monkeypatch.setattr(workflows.AuditLogService, "log", AsyncMock())
    patch_dump_schema(monkeypatch, workflows.WorkflowOut, {"id": workflow_id})

    await workflows.publish_workflow(
        workflow_id, SimpleNamespace(), SimpleNamespace(id=uuid4())
    )

    assert workflow.status == WorkflowStatus.PUBLISHED
    workflow.save.assert_awaited_once()
    assert version_create.await_count == (0 if existing_version else 1)


@pytest.mark.asyncio
async def test_list_workflow_runs_applies_filters_and_invalid_search(monkeypatch):
    workflow_id = uuid4()
    query = Query(total=0)
    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    monkeypatch.setattr(workflows.WorkflowRun, "filter", Mock(return_value=query))
    timestamp = datetime.now(UTC)

    response = await workflows.list_workflow_runs(
        workflow_id,
        status=RunStatus.FAILED,
        is_debug=True,
        search="not-a-uuid",
        created_after=timestamp,
        created_before=timestamp,
        page=2,
        page_size=5,
        current_user=SimpleNamespace(),
    )

    assert {"status": RunStatus.FAILED} in query.filters
    assert {"is_debug": True} in query.filters
    assert {"id__isnull": True} in query.filters
    assert {"created_at__gte": timestamp} in query.filters
    assert {"created_at__lte": timestamp} in query.filters
    assert response["data"]["page"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("run", "msg_key"),
    [
        (None, "workflow_run_not_found"),
        (SimpleNamespace(workflow_id=None), "workflow_not_found"),
    ],
)
async def test_run_detail_rejects_missing_or_orphaned_runs(monkeypatch, run, msg_key):
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", Mock(return_value=Query(first=run))
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.get_workflow_run(uuid4(), SimpleNamespace())

    assert exc_info.value.msg_key == msg_key
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_run_detail_checks_access_and_sanitizes_error(monkeypatch):
    workflow_id = uuid4()
    run = SimpleNamespace(workflow_id=workflow_id)
    access = AsyncMock()
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", Mock(return_value=Query(first=run))
    )
    monkeypatch.setattr(workflows, "check_workflow_access", access)
    patch_dump_schema(
        monkeypatch, workflows.WorkflowRunOut, {"error_message": "private detail"}
    )
    monkeypatch.setattr(
        workflows, "sanitize_public_workflow_error", lambda _msg: "safe"
    )

    response = await workflows.get_workflow_run(uuid4(), SimpleNamespace())

    access.assert_awaited_once_with(workflow_id, ANY)
    assert response["data"]["error_message"] == "safe"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("run", "msg_key"),
    [
        (None, "workflow_run_not_found"),
        (SimpleNamespace(workflow_id=None), "workflow_not_found"),
    ],
)
async def test_run_logs_reject_missing_or_orphaned_runs(monkeypatch, run, msg_key):
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", Mock(return_value=Query(first=run))
    )

    with pytest.raises(BusinessError) as exc_info:
        await workflows.list_run_node_executions(uuid4(), SimpleNamespace())

    assert exc_info.value.msg_key == msg_key


@pytest.mark.asyncio
async def test_run_logs_order_and_sanitize_node_errors(monkeypatch):
    workflow_id = uuid4()
    run = SimpleNamespace(workflow_id=workflow_id)
    node = SimpleNamespace()
    node_query = Query(items=[node])
    monkeypatch.setattr(
        workflows.WorkflowRun, "filter", Mock(return_value=Query(first=run))
    )
    monkeypatch.setattr(
        workflows.NodeExecution, "filter", Mock(return_value=node_query)
    )
    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    patch_dump_schema(
        monkeypatch, workflows.NodeExecutionOut, {"error_message": "traceback"}
    )
    monkeypatch.setattr(
        workflows, "sanitize_public_workflow_error", lambda _msg: "safe"
    )

    response = await workflows.list_run_node_executions(uuid4(), SimpleNamespace())

    assert response["data"] == [{"error_message": "safe"}]


@pytest.mark.asyncio
async def test_debug_workflow_wraps_run_creation_errors(monkeypatch):
    workflow = SimpleNamespace(
        team_id=uuid4(), trigger_type=TriggerType.MANUAL, name="Flow"
    )
    monkeypatch.setattr(
        workflows, "check_workflow_access", AsyncMock(return_value=workflow)
    )
    monkeypatch.setattr(
        workflows.WorkflowRun,
        "create",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(run_workflow_task, "delay", Mock())
    monkeypatch.setattr(workflows.AuditLogService, "log", AsyncMock())

    with pytest.raises(BusinessError) as exc_info:
        await workflows.debug_workflow(
            uuid4(),
            WorkflowRunRequest(inputs={}),
            SimpleNamespace(),
            SimpleNamespace(id=uuid4()),
        )

    assert exc_info.value.code == ResponseCode.INTERNAL_ERROR
    assert exc_info.value.msg_key == "workflow_execution_error"
