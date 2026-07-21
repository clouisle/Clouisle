from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import workflows
from app.models.workflow import TriggerType, WorkflowStatus, WorkflowVisibility
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowRunRequest,
    WorkflowUpdate,
    WorkflowVersionRestore,
)


class _Query:
    def __init__(self, result=None, *, count=0):
        self.result = result
        self.total = count
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def exclude(self, *args, **kwargs):
        self.calls.append(("exclude", args, kwargs))
        return self

    def prefetch_related(self, *args):
        self.calls.append(("prefetch_related", args, {}))
        return self

    def offset(self, value):
        self.calls.append(("offset", (value,), {}))
        return self

    def limit(self, value):
        self.calls.append(("limit", (value,), {}))
        return self

    def order_by(self, *args):
        self.calls.append(("order_by", args, {}))
        return self

    async def first(self):
        return self.result

    async def count(self):
        return self.total

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


def _workflow(**overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "Approval flow",
        "description": "Routes approvals",
        "icon": None,
        "definition": {"nodes": [], "edges": []},
        "variables": [],
        "status": WorkflowStatus.DRAFT,
        "visibility": WorkflowVisibility.TEAM,
        "version": 3,
        "trigger_type": TriggerType.MANUAL,
        "trigger_config": {},
        "webhook_token": None,
        "embed_config": {},
        "run_count": 0,
        "success_count": 0,
        "fail_count": 0,
        "created_by_id": uuid4(),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _version(workflow_id, version=3, **overrides):
    values = {
        "id": uuid4(),
        "workflow_id": workflow_id,
        "version": version,
        "definition": {"nodes": [{"id": "saved"}]},
        "variables": [{"name": "query"}],
        "trigger_type": TriggerType.WEBHOOK,
        "trigger_config": {"enabled": True},
        "description": "Snapshot",
        "created_by_id": uuid4(),
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_create_workflow_checks_scope_rejects_duplicate_name():
    team_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    scoped = AsyncMock()
    team_access = AsyncMock(return_value=SimpleNamespace(id=team_id))

    with (
        patch.object(workflows.deps, "check_scoped_permission", scoped),
        patch.object(workflows, "check_team_access", team_access),
        patch.object(workflows.Workflow, "filter", return_value=_Query(object())),
        patch.object(workflows.Workflow, "create", new=AsyncMock()) as create,
    ):
        with pytest.raises(BusinessError) as error:
            await workflows.create_workflow(
                workflow_in=WorkflowCreate(team_id=team_id, name="Existing"),
                request=MagicMock(),
                current_user=user,
            )

    assert error.value.code == ResponseCode.DUPLICATE_NAME
    scoped.assert_awaited_once_with(user, "workflow:create", "team", team_id)
    team_access.assert_awaited_once_with(team_id, user)
    create.assert_not_awaited()


@pytest.mark.anyio
async def test_create_workflow_persists_default_definition_and_audits():
    team_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    request = MagicMock()
    team = SimpleNamespace(id=team_id)
    created = _workflow(team_id=team_id, created_by_id=user.id)
    reloaded = _workflow(id=created.id, team_id=team_id, created_by_id=user.id)

    with (
        patch.object(workflows.deps, "check_scoped_permission", new=AsyncMock()),
        patch.object(workflows, "check_team_access", new=AsyncMock(return_value=team)),
        patch.object(workflows.Workflow, "filter", return_value=_Query(None)),
        patch.object(
            workflows.Workflow, "create", new=AsyncMock(return_value=created)
        ) as create,
        patch.object(workflows.Workflow, "get", return_value=_Query(reloaded)),
        patch.object(workflows.AuditLogService, "log", new=AsyncMock()) as audit,
    ):
        response = await workflows.create_workflow(
            workflow_in=WorkflowCreate(
                team_id=team_id,
                name="Approval flow",
                description="Routes approvals",
                visibility="team",
            ),
            request=request,
            current_user=user,
        )

    persisted = create.await_args.kwargs
    assert persisted["team"] is team
    assert persisted["created_by"] is user
    assert persisted["definition"]["nodes"][0]["type"] == "user_input"
    assert (
        persisted["definition"]["nodes"][0]["data"]["parameters"][0]["name"] == "query"
    )
    assert response["data"]["id"] == created.id
    audit.assert_awaited_once()


@pytest.mark.anyio
async def test_update_workflow_rejects_duplicate_name_before_persisting():
    user = SimpleNamespace(id=uuid4())
    workflow = _workflow()

    with (
        patch.object(
            workflows, "check_workflow_access", new=AsyncMock(return_value=workflow)
        ),
        patch.object(
            workflows.deps, "check_scoped_permission", new=AsyncMock()
        ) as scoped,
        patch.object(workflows.Workflow, "filter", return_value=_Query(object())),
    ):
        with pytest.raises(BusinessError) as error:
            await workflows.update_workflow(
                workflow_id=workflow.id,
                workflow_in=WorkflowUpdate(name="Existing"),
                request=MagicMock(),
                current_user=user,
            )

    assert error.value.msg_key == "workflow_name_exists"
    scoped.assert_awaited_once_with(user, "workflow:update", "team", workflow.team_id)
    workflow.save.assert_not_awaited()


@pytest.mark.anyio
async def test_update_workflow_applies_fields_and_increments_version():
    user = SimpleNamespace(id=uuid4())
    workflow = _workflow()
    reloaded = _workflow(id=workflow.id, team_id=workflow.team_id, version=4)
    access = AsyncMock(return_value=workflow)

    with (
        patch.object(workflows, "check_workflow_access", access),
        patch.object(
            workflows.deps, "check_scoped_permission", new=AsyncMock()
        ) as scoped,
        patch.object(workflows.Workflow, "filter", return_value=_Query(None)),
        patch.object(workflows.Workflow, "get", return_value=_Query(reloaded)),
        patch.object(workflows.AuditLogService, "log", new=AsyncMock()),
    ):
        response = await workflows.update_workflow(
            workflow_id=workflow.id,
            workflow_in=WorkflowUpdate(
                name="Updated",
                description="New description",
                icon="bolt",
                definition={"nodes": [{"id": "start"}]},
                variables=[{"name": "query"}],
                trigger_type=TriggerType.WEBHOOK,
                trigger_config={"enabled": True},
                visibility="public",
                embed_config={"theme": "dark"},
            ),
            request=MagicMock(),
            current_user=user,
        )

    access.assert_awaited_once_with(workflow.id, user, require_write=True)
    scoped.assert_awaited_once_with(user, "workflow:update", "team", workflow.team_id)
    assert workflow.name == "Updated"
    assert workflow.version == 4
    assert workflow.visibility == WorkflowVisibility.PUBLIC
    workflow.save.assert_awaited_once()
    assert response["data"]["version"] == 4


@pytest.mark.anyio
async def test_publish_snapshots_once_and_transitions_status():
    user = SimpleNamespace(id=uuid4())
    workflow = _workflow()
    access = AsyncMock(return_value=workflow)
    create_version = AsyncMock()

    with (
        patch.object(workflows, "check_workflow_access", access),
        patch.object(workflows.WorkflowVersion, "filter", return_value=_Query(None)),
        patch.object(workflows.WorkflowVersion, "create", new=create_version),
        patch.object(workflows.AuditLogService, "log", new=AsyncMock()),
    ):
        response = await workflows.publish_workflow(workflow.id, MagicMock(), user)

    access.assert_awaited_once_with(workflow.id, user, require_write=True)
    create_version.assert_awaited_once()
    assert create_version.await_args.kwargs["definition"] == workflow.definition
    assert workflow.status == WorkflowStatus.PUBLISHED
    workflow.save.assert_awaited_once()
    assert response["data"]["status"] == WorkflowStatus.PUBLISHED


@pytest.mark.anyio
async def test_publish_reuses_existing_snapshot():
    workflow = _workflow()
    create_version = AsyncMock()

    with (
        patch.object(
            workflows, "check_workflow_access", new=AsyncMock(return_value=workflow)
        ),
        patch.object(
            workflows.WorkflowVersion, "filter", return_value=_Query(object())
        ),
        patch.object(workflows.WorkflowVersion, "create", new=create_version),
        patch.object(workflows.AuditLogService, "log", new=AsyncMock()),
    ):
        await workflows.publish_workflow(
            workflow.id, MagicMock(), SimpleNamespace(id=uuid4())
        )

    create_version.assert_not_awaited()
    assert workflow.status == WorkflowStatus.PUBLISHED
    workflow.save.assert_awaited_once()


@pytest.mark.anyio
async def test_regenerate_webhook_token_checks_permission_before_persisting():
    workflow = _workflow()
    permission_error = BusinessError(msg_key="operation_not_permitted")

    with (
        patch.object(
            workflows, "check_workflow_access", new=AsyncMock(return_value=workflow)
        ),
        patch.object(
            workflows.deps,
            "check_scoped_permission",
            new=AsyncMock(side_effect=permission_error),
        ),
    ):
        with pytest.raises(BusinessError) as error:
            await workflows.regenerate_webhook_token(
                workflow.id, MagicMock(), SimpleNamespace(id=uuid4())
            )

    assert error.value.msg_key == "operation_not_permitted"
    assert workflow.webhook_token is None
    workflow.save.assert_not_awaited()


@pytest.mark.anyio
async def test_run_workflow_dispatches_mocked_runtime_and_records_audit():
    user = SimpleNamespace(id=uuid4())
    workflow = _workflow(status=WorkflowStatus.PUBLISHED)
    run = SimpleNamespace(id=uuid4())
    task = MagicMock()

    with (
        patch.object(
            workflows, "check_workflow_access", new=AsyncMock(return_value=workflow)
        ),
        patch.object(workflows.WorkflowRun, "create", new=AsyncMock(return_value=run)),
        patch("app.tasks.workflow.run_workflow_task", task),
        patch.object(workflows.AuditLogService, "log", new=AsyncMock()) as audit,
    ):
        response = await workflows.run_workflow(
            workflow.id,
            WorkflowRunRequest(inputs={"query": "hello"}),
            MagicMock(),
            user,
        )

    task.delay.assert_called_once_with(
        run_id=str(run.id),
        workflow_id=str(workflow.id),
        inputs={"query": "hello"},
        user_id=str(user.id),
        team_id=str(workflow.team_id),
    )
    audit.assert_awaited_once()
    assert response["data"]["run_id"] == str(run.id)


@pytest.mark.anyio
async def test_run_workflow_rejects_draft_and_maps_persistence_failure():
    user = SimpleNamespace(id=uuid4())
    draft = _workflow()

    with patch.object(
        workflows, "check_workflow_access", new=AsyncMock(return_value=draft)
    ):
        with pytest.raises(BusinessError) as unpublished:
            await workflows.run_workflow(
                draft.id, WorkflowRunRequest(), MagicMock(), user
            )

    assert unpublished.value.status_code == 403
    assert unpublished.value.msg_key == "workflow_not_published"

    published = _workflow(status=WorkflowStatus.PUBLISHED)
    with (
        patch.object(
            workflows, "check_workflow_access", new=AsyncMock(return_value=published)
        ),
        patch.object(
            workflows.WorkflowRun,
            "create",
            new=AsyncMock(side_effect=RuntimeError("database unavailable")),
        ),
    ):
        with pytest.raises(BusinessError) as failed:
            await workflows.run_workflow(
                published.id, WorkflowRunRequest(), MagicMock(), user
            )

    assert failed.value.code == ResponseCode.INTERNAL_ERROR
    assert failed.value.msg_key == "workflow_execution_error"


@pytest.mark.anyio
async def test_version_detail_not_found_and_restore_persists_snapshots():
    user = SimpleNamespace(id=uuid4())
    workflow = _workflow()
    saved = _version(workflow.id, version=2, trigger_config=None)
    reloaded = _workflow(id=workflow.id, team_id=workflow.team_id, version=4)
    access = AsyncMock(return_value=workflow)
    create_version = AsyncMock()

    with (
        patch.object(workflows, "check_workflow_access", access),
        patch.object(workflows.WorkflowVersion, "filter", return_value=_Query(None)),
    ):
        with pytest.raises(BusinessError) as missing:
            await workflows.get_workflow_version(workflow.id, 99, user)

    assert missing.value.status_code == 404
    assert missing.value.msg_key == "workflow_version_not_found"

    with (
        patch.object(workflows, "check_workflow_access", access),
        patch.object(
            workflows.deps, "check_scoped_permission", new=AsyncMock()
        ) as scoped,
        patch.object(workflows.WorkflowVersion, "filter", return_value=_Query(saved)),
        patch.object(workflows.WorkflowVersion, "create", new=create_version),
        patch.object(workflows.Workflow, "get", return_value=_Query(reloaded)),
        patch.object(workflows.AuditLogService, "log", new=AsyncMock()),
    ):
        response = await workflows.restore_workflow_version(
            workflow.id,
            2,
            WorkflowVersionRestore(description="Rollback"),
            MagicMock(),
            user,
        )

    scoped.assert_awaited_once_with(user, "workflow:update", "team", workflow.team_id)
    assert create_version.await_count == 2
    assert workflow.definition == saved.definition
    assert workflow.trigger_config == {}
    assert workflow.version == 4
    workflow.save.assert_awaited_once()
    assert create_version.await_args.kwargs["description"] == "Rollback"
    assert response["data"]["version"] == 4
