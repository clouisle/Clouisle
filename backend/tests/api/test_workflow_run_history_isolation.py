"""Run-history isolation between app sessions, API keys and orchestration logs.

Three rules are pinned here:

1. ``/workflows/{id}/runs/mine*`` (JWT) lists only runs the caller started from
   the app: API-key and embed runs and ``api_key_origin_unknown`` rows stay out.
2. The same routes authenticated by an API key list exactly that key's runs, and
   the run stream (SSE) is bound to the same exact credential.
3. Orchestration logs keep showing every source for callers that already pass
   the workflow log permission, so ``/{workflow_id}/runs`` is not isolated.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api import deps
from app.api.v1.endpoints import embed, workflows
from app.api.workflow_run_access import (
    api_key_may_read_run,
    api_key_run_filter,
    get_run_history_principal,
    run_history_filter,
    session_run_filter,
    split_run_principal,
)
from app.schemas.response import BusinessError, ResponseCode
from app.services.workflow.execution_origin import (
    ORIGIN_SNAPSHOT_KEY,
    api_key_origin,
    embed_origin,
    origin_snapshot,
)


class RunQuery:
    """Minimal Tortoise query stub recording keyword filters."""

    def __init__(self, rows=None, exists=None):
        self.rows = list(rows or [])
        self.exists_result = exists
        self.filters = []
        self.offset_args = None

    def filter(self, **kwargs):
        self.filters.append(kwargs)
        return self

    def order_by(self, *_args):
        return self

    def prefetch_related(self, *_args):
        return self

    def offset(self, *args):
        self.offset_args = args
        return self

    def limit(self, *args):
        self.offset_args = (self.offset_args, args)
        return self

    async def count(self):
        return len(self.rows)

    async def all(self):
        return self.rows

    async def first(self):
        return self.rows[0] if self.rows else None

    async def exists(self):
        return bool(self.rows) if self.exists_result is None else self.exists_result

    def __await__(self):
        async def _self():
            return self.rows

        return _self().__await__()


def api_key(*, user_id=None, **overrides):
    values = {
        "id": uuid4(),
        "user_id": user_id or uuid4(),
        "is_active": True,
        "expires_at": None,
        # The webhook route checks the key's workflow scope, not the owner's.
        "workflows": SimpleNamespace(all=AsyncMock(return_value=[])),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def run(**overrides):
    values = {
        "id": uuid4(),
        "workflow_id": uuid4(),
        "triggered_by_id": uuid4(),
        "api_key_id": None,
        "api_key_origin_unknown": False,
        "context_snapshot": {},
        "is_debug": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# ---------------------------------------------------------------------------
# Filters: what each audience may list
# ---------------------------------------------------------------------------


def test_session_filter_excludes_api_key_and_unattributable_runs():
    user = SimpleNamespace(id=uuid4())

    assert session_run_filter(user) == {
        "triggered_by_id": user.id,
        "api_key_id__isnull": True,
        "api_key_origin_unknown": False,
    }


def test_api_key_filter_is_bound_to_the_exact_credential():
    key = api_key()

    assert api_key_run_filter(key) == {
        "triggered_by_id": key.user_id,
        "api_key_id": key.id,
        "api_key_origin_unknown": False,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"is_active": False},
        {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)},
        {"id": None},
    ],
)
def test_unusable_credential_matches_no_run(overrides):
    key = api_key(**overrides)
    user = SimpleNamespace(id=key.user_id)

    assert api_key_run_filter(key) is None
    assert run_history_filter(user, key) is None


@pytest.mark.parametrize(
    "expires_at", [None, datetime.now(timezone.utc) + timedelta(hours=1)]
)
def test_live_credential_filter_applies(expires_at):
    key = api_key(expires_at=expires_at)

    assert run_history_filter(SimpleNamespace(id=key.user_id), key) is not None


def test_run_history_filter_switches_on_the_credential():
    user = SimpleNamespace(id=uuid4())
    key = api_key(user_id=user.id)

    assert run_history_filter(user, None) == session_run_filter(user)
    assert run_history_filter(user, key) == api_key_run_filter(key)


def test_split_run_principal_accepts_direct_user_calls():
    user, key = api_key(), None

    assert split_run_principal((user, key)) == (user, key)
    assert split_run_principal(user) == (user, None)


# ---------------------------------------------------------------------------
# Predicate: which runs one exact credential may stream
# ---------------------------------------------------------------------------


def test_stored_key_id_wins():
    key = api_key()

    assert api_key_may_read_run(
        run(triggered_by_id=key.user_id, api_key_id=key.id), key
    )
    # A second key of the same owner is refused.
    assert not api_key_may_read_run(
        run(triggered_by_id=key.user_id, api_key_id=uuid4()), key
    )


def test_unknown_origin_is_never_claimed_by_a_key():
    key = api_key()
    unknown = run(
        triggered_by_id=key.user_id, api_key_id=None, api_key_origin_unknown=True
    )

    assert not api_key_may_read_run(unknown, key)


def test_unmigrated_origins_never_match_a_key():
    key = api_key()
    snapshot = {ORIGIN_SNAPSHOT_KEY: origin_snapshot(api_key_origin(key.id))}

    assert not api_key_may_read_run(
        run(
            triggered_by_id=key.user_id, workflow_id=uuid4(), context_snapshot=snapshot
        ),
        key,
    )
    # The same row is refused to a different credential of the same owner.
    assert not api_key_may_read_run(
        run(
            triggered_by_id=key.user_id, workflow_id=uuid4(), context_snapshot=snapshot
        ),
        api_key(user_id=key.user_id),
    )


def test_row_without_key_binding_is_not_key_history():
    key = api_key()
    snapshot = {
        ORIGIN_SNAPSHOT_KEY: origin_snapshot(embed_origin(uuid4())),
    }

    assert not api_key_may_read_run(run(triggered_by_id=key.user_id), key)
    assert not api_key_may_read_run(
        run(triggered_by_id=key.user_id, context_snapshot=snapshot), key
    )


def test_predicate_requires_the_key_owner_and_a_live_credential():
    key = api_key()

    assert not api_key_may_read_run(run(triggered_by_id=uuid4()), key)
    assert not api_key_may_read_run(run(triggered_by_id=None), key)
    assert not api_key_may_read_run(
        run(triggered_by_id=key.user_id), api_key(user_id=key.user_id, is_active=False)
    )
    assert not api_key_may_read_run(
        run(triggered_by_id=key.user_id),
        api_key(user_id=key.user_id, expires_at=datetime.now(timezone.utc)),
    )


# ---------------------------------------------------------------------------
# Dual-auth dependency
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_principal_keeps_the_app_session_permission_gate():
    user = SimpleNamespace(id=uuid4(), is_active=True, is_superuser=False, roles=[])

    with pytest.raises(BusinessError) as exc_info:
        await get_run_history_principal((user, None))

    assert exc_info.value.code == ResponseCode.PERMISSION_DENIED
    assert exc_info.value.msg_key == "operation_not_permitted"
    assert exc_info.value.kwargs["permission"] == "workflow:run"


@pytest.mark.anyio
async def test_principal_allows_a_permitted_session_and_any_api_key():
    permission = SimpleNamespace(code="workflow:run")
    user = SimpleNamespace(
        id=uuid4(),
        is_superuser=False,
        is_active=True,
        roles=[SimpleNamespace(permissions=[permission])],
    )
    key = api_key(user_id=user.id)

    assert await get_run_history_principal((user, None)) == (user, None)
    # A key acts with its own scope, exactly like the execution surfaces, so an
    # unprivileged owner's key is not blocked by the session permission gate.
    owner = SimpleNamespace(id=user.id, is_superuser=False, roles=[])
    assert await get_run_history_principal((owner, key)) == (owner, key)


# ---------------------------------------------------------------------------
# Endpoints: own history
# ---------------------------------------------------------------------------


def _patch_history_query(monkeypatch, query):
    recorded: list[dict] = []

    def filter_mock(**kwargs):
        recorded.append(kwargs)
        return query

    monkeypatch.setattr(workflows.WorkflowRun, "filter", filter_mock)
    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    monkeypatch.setattr(deps, "check_api_key_workflow_access", AsyncMock())
    return recorded


@pytest.mark.anyio
async def test_list_mine_with_api_key_lists_only_that_keys_runs(monkeypatch):
    workflow_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    key = api_key(user_id=user.id)
    recorded = _patch_history_query(monkeypatch, RunQuery())

    response = await workflows.list_my_workflow_runs(
        workflow_id=workflow_id,
        status=None,
        search=None,
        created_after=None,
        created_before=None,
        page=1,
        page_size=20,
        auth_result=(user, key),
    )

    assert response["data"]["total"] == 0
    assert recorded == [
        {
            "workflow_id": workflow_id,
            "is_debug": False,
            "triggered_by_id": key.user_id,
            "api_key_id": key.id,
            "api_key_origin_unknown": False,
        }
    ]
    deps.check_api_key_workflow_access.assert_awaited_once_with(key, workflow_id)  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_list_mine_with_revoked_key_returns_an_empty_page(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    key = api_key(user_id=user.id, is_active=False)
    recorded = _patch_history_query(monkeypatch, RunQuery())

    response = await workflows.list_my_workflow_runs(
        workflow_id=uuid4(),
        status=None,
        search=None,
        created_after=None,
        created_before=None,
        page=1,
        page_size=20,
        auth_result=(user, key),
    )

    assert response["data"] == {"items": [], "total": 0, "page": 1, "page_size": 20}
    assert recorded == []


@pytest.mark.anyio
async def test_get_mine_binds_detail_and_nodes_to_the_credential(monkeypatch):
    workflow_id = uuid4()
    run_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    key = api_key(user_id=user.id)
    recorded = _patch_history_query(monkeypatch, RunQuery([run(id=run_id)]))
    monkeypatch.setattr(
        workflows.WorkflowRunOut,
        "model_validate",
        lambda value: SimpleNamespace(model_dump=lambda: {"id": str(run_id)}),
    )
    monkeypatch.setattr(
        workflows.NodeExecution,
        "filter",
        lambda **_kwargs: RunQuery([SimpleNamespace(id="n1")]),
    )
    monkeypatch.setattr(
        workflows.NodeExecutionOut,
        "model_validate",
        lambda value: SimpleNamespace(model_dump=lambda: {"id": "n1"}),
    )

    detail = await workflows.get_my_workflow_run(
        workflow_id=workflow_id, run_id=run_id, auth_result=(user, key)
    )
    nodes = await workflows.list_my_run_node_executions(
        workflow_id=workflow_id, run_id=run_id, auth_result=(user, key)
    )

    assert detail["data"]["id"] == str(run_id)
    assert nodes["data"] == [{"id": "n1", "error_message": None}]
    for matrix in recorded:
        assert matrix["api_key_id"] == key.id
        assert matrix["triggered_by_id"] == key.user_id


@pytest.mark.anyio
async def test_get_mine_with_revoked_key_is_not_found(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    key = api_key(user_id=user.id, is_active=False)
    _patch_history_query(monkeypatch, RunQuery([run()]))

    with pytest.raises(BusinessError) as exc_info:
        await workflows.get_my_workflow_run(
            workflow_id=uuid4(), run_id=uuid4(), auth_result=(user, key)
        )

    assert exc_info.value.msg_key == "workflow_run_not_found"
    assert exc_info.value.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize("own_only", [False, True])
async def test_orchestration_log_list_is_not_isolated(monkeypatch, own_only):
    """The per-workflow log view keeps every source for authorised viewers."""

    workflow_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    query = RunQuery()
    recorded = _patch_history_query(monkeypatch, query)

    await workflows.list_workflow_runs(
        workflow_id=workflow_id,
        status=None,
        is_debug=None,
        search=None,
        created_after=None,
        created_before=None,
        page=1,
        page_size=20,
        current_user=user,
        own_only=own_only,
    )

    assert recorded == [{"workflow_id": workflow_id}]
    assert query.filters == ([{"triggered_by_id": user.id}] if own_only else [])


@pytest.mark.anyio
async def test_orchestration_log_key_filter_keeps_owner_constraint(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    key_id = uuid4()
    query = RunQuery()
    _patch_history_query(monkeypatch, query)
    await workflows.list_workflow_runs(
        workflow_id=uuid4(),
        status=None,
        is_debug=None,
        own_only=True,
        api_key_id=key_id,
        search=None,
        created_after=None,
        created_before=None,
        page=1,
        page_size=20,
        current_user=user,
    )
    assert query.filters == [{"triggered_by_id": user.id}, {"api_key_id": key_id}]


# ---------------------------------------------------------------------------
# Endpoints: streams
# ---------------------------------------------------------------------------


def _patch_stream(monkeypatch, row, query=None):
    query = query or RunQuery([row])
    monkeypatch.setattr(workflows.WorkflowRun, "filter", Mock(return_value=query))
    monkeypatch.setattr(workflows, "check_workflow_access", AsyncMock())
    monkeypatch.setattr(deps, "check_api_key_workflow_access", AsyncMock())

    from app.services.workflow import stream as stream_module

    async def fake_stream_to_sse(_run_id, _from_sequence):
        yield "data: complete\n\n"

    monkeypatch.setattr(stream_module, "stream_to_sse", fake_stream_to_sse)
    return query


@pytest.mark.anyio
async def test_stream_allows_the_creating_key(monkeypatch):
    key = api_key()
    row = run(triggered_by_id=key.user_id, api_key_id=key.id)
    _patch_stream(monkeypatch, row)

    response = await workflows.stream_workflow_run(
        row.id, auth_result=(SimpleNamespace(id=key.user_id), key)
    )

    assert [chunk async for chunk in response.body_iterator] == ["data: complete\n\n"]
    deps.check_api_key_workflow_access.assert_awaited_once_with(key, row.workflow_id)  # type: ignore[attr-defined]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "row_overrides",
    [
        {"api_key_id": uuid4()},  # another key of the same owner
        {"api_key_id": None},  # web run
        {"api_key_id": None, "api_key_origin_unknown": True},
        {"triggered_by_id": uuid4()},  # another user's run
    ],
)
async def test_stream_refuses_other_credentials(monkeypatch, row_overrides):
    key = api_key()
    overrides = {"triggered_by_id": key.user_id, **row_overrides}
    row = run(**overrides)
    _patch_stream(monkeypatch, row)

    with pytest.raises(BusinessError) as exc_info:
        await workflows.stream_workflow_run(
            row.id, auth_result=(SimpleNamespace(id=key.user_id), key)
        )

    assert exc_info.value.msg_key == "workflow_run_not_found"
    assert exc_info.value.status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize("authenticated", [True, False])
async def test_stream_does_not_replay_key_runs_without_the_key(
    monkeypatch, authenticated
):
    owner = SimpleNamespace(id=uuid4())
    row = run(triggered_by_id=owner.id, api_key_id=uuid4())
    _patch_stream(monkeypatch, row)
    with pytest.raises(BusinessError) as denied:
        await workflows.stream_workflow_run(
            row.id, auth_result=(owner, None) if authenticated else None
        )
    assert denied.value.status_code == 404


@pytest.mark.anyio
async def test_stream_disallows_callerless_runs_without_authentication(monkeypatch):
    row = run(triggered_by_id=None)
    _patch_stream(monkeypatch, row)

    with pytest.raises(BusinessError) as denied:
        await workflows.stream_workflow_run(row.id, auth_result=None)
    assert denied.value.status_code == 401


@pytest.mark.anyio
async def test_embed_stream_requires_the_creating_key(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    key = api_key(user_id=user.id)
    row = run(triggered_by_id=user.id, api_key_id=key.id)
    from app.models.workflow import WorkflowRun as _WorkflowRun

    # The route imports the model lazily, so patch the model itself.
    monkeypatch.setattr(_WorkflowRun, "filter", Mock(return_value=RunQuery([row])))
    monkeypatch.setattr(deps, "check_api_key_workflow_access", AsyncMock())

    from app.services.workflow import stream as stream_module

    async def fake_stream_to_sse(_run_id, _from_sequence):
        yield "data: done\n\n"

    monkeypatch.setattr(stream_module, "stream_to_sse", fake_stream_to_sse)

    response = await embed.embed_stream_workflow_run(
        row.id, from_sequence=0, auth_result=(user, key)
    )
    assert [chunk async for chunk in response.body_iterator] == ["data: done\n\n"]

    with pytest.raises(BusinessError) as exc_info:
        await embed.embed_stream_workflow_run(
            row.id, from_sequence=0, auth_result=(user, api_key(user_id=user.id))
        )
    assert exc_info.value.msg_key == "workflow_run_not_found"


# ---------------------------------------------------------------------------
# Creation: the exact key is persisted with the run
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_embed_workflow_run_persists_the_key(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    key = api_key(user_id=user.id)
    workflow = SimpleNamespace(
        id=uuid4(), name="Flow", team_id=uuid4(), trigger_type="webhook"
    )
    create = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(embed, "_get_embed_workflow", AsyncMock(return_value=workflow))

    from app.models.workflow import WorkflowRun
    from app.tasks import workflow as workflow_tasks

    monkeypatch.setattr(WorkflowRun, "create", create)
    monkeypatch.setattr(workflow_tasks.run_workflow_task, "delay", Mock())
    monkeypatch.setattr(
        "app.services.observability_v2.record_workflow_submission", AsyncMock()
    )
    monkeypatch.setattr(embed.AuditLogService, "log", AsyncMock())

    body = SimpleNamespace(json=AsyncMock(return_value={"inputs": {}}))
    response = await embed.embed_run_workflow(
        workflow.id,
        body,
        auth_result=(user, key),
    )

    assert response["data"]["run_id"]
    assert create.await_args.kwargs["api_key_id"] == key.id


@pytest.mark.anyio
async def test_webhook_run_persists_the_key(monkeypatch):
    user = SimpleNamespace(id=uuid4())
    key = api_key(user_id=user.id)
    workflow = SimpleNamespace(
        id=uuid4(),
        name="Flow",
        team_id=uuid4(),
        status=workflows.WorkflowStatus.PUBLISHED,
        trigger_type=workflows.TriggerType.WEBHOOK,
        webhook_token="token",
    )
    monkeypatch.setattr(
        deps, "_authenticate_api_key", AsyncMock(return_value=(user, key))
    )

    class WorkflowQuery:
        def prefetch_related(self, *_args):
            return self

        async def all(self):
            return [workflow]

    monkeypatch.setattr(
        workflows.Workflow, "filter", Mock(return_value=WorkflowQuery())
    )

    from app.models.workflow import WorkflowRun
    from app.tasks import workflow as workflow_tasks

    create = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(WorkflowRun, "create", create)
    monkeypatch.setattr(workflow_tasks.run_workflow_task, "delay", Mock())
    monkeypatch.setattr(
        "app.services.observability_v2.record_workflow_submission", AsyncMock()
    )

    response = await workflows.trigger_workflow_webhook("token", {}, "Bearer clou_abc")

    assert response["data"]["run_id"]
    assert create.await_args.kwargs["api_key_id"] == key.id


# ---------------------------------------------------------------------------
# Nested runs inherit the credential at creation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_nested_run_is_created_with_the_parents_credential(monkeypatch):
    """A child is never briefly readable as an app-session run of the owner."""

    from app.models.workflow import Workflow, WorkflowRun
    from app.services.workflow.executors import subworkflow
    from app.services.workflow.executors.subworkflow import SubWorkflowNodeExecutor
    from app.services.workflow.orchestrator import WorkflowOrchestrator

    key = api_key()
    parent = SimpleNamespace(
        id=uuid4(),
        root_run_id=None,
        depth=0,
        triggered_by_id=key.user_id,
        workflow_id=uuid4(),
        context_snapshot={},
        api_key_id=key.id,
        api_key_origin_unknown=False,
    )
    workflow_id = uuid4()
    child = SimpleNamespace(
        status="completed",
        outputs={},
        parent_run_id=None,
        root_run_id=None,
        depth=0,
        save=AsyncMock(),
    )
    run_child = AsyncMock(return_value=uuid4())

    monkeypatch.setattr(
        Workflow,
        "filter",
        Mock(return_value=RunQuery([SimpleNamespace(id=workflow_id)])),
    )
    monkeypatch.setattr(WorkflowRun, "filter", Mock(return_value=RunQuery([child])))
    monkeypatch.setattr(WorkflowOrchestrator, "run", run_child)
    monkeypatch.setattr(subworkflow, "inherited_origin", lambda _run: None)

    await SubWorkflowNodeExecutor().execute(
        {"data": {"subWorkflowConfig": {"workflowId": str(workflow_id)}}},
        Mock(),
        parent,
    )

    kwargs = run_child.await_args.kwargs
    assert kwargs["api_key_id"] == key.id
    assert kwargs["api_key_origin_unknown"] is False


# ---------------------------------------------------------------------------
# Credential checks the filters cannot express
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_principal_rejects_an_inactive_app_session():
    """An inactive login never reaches the run-history permission gate."""
    inactive = SimpleNamespace(
        id=uuid4(), is_active=False, is_superuser=False, roles=[]
    )

    with pytest.raises(BusinessError) as denied:
        await get_run_history_principal((inactive, None))

    assert denied.value.code == ResponseCode.INACTIVE_USER


@pytest.mark.anyio
async def test_stream_refuses_another_users_app_session_run(monkeypatch):
    """The stream is the owner's own history, not any web run."""
    caller = SimpleNamespace(id=uuid4(), is_superuser=False)
    row = run(triggered_by_id=uuid4(), api_key_id=None)
    _patch_stream(monkeypatch, row)

    with pytest.raises(BusinessError) as denied:
        await workflows.stream_workflow_run(row.id, auth_result=(caller, None))

    assert denied.value.msg_key == "workflow_run_not_found"
    assert denied.value.status_code == 404


@pytest.mark.anyio
async def test_node_executions_of_a_revoked_key_are_not_found(monkeypatch):
    """Node detail is part of the history, so it fails closed like the run."""
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    key = api_key(user_id=user.id, is_active=False)
    recorded = _patch_history_query(monkeypatch, RunQuery([run()]))

    with pytest.raises(BusinessError) as denied:
        await workflows.list_my_run_node_executions(
            workflow_id=uuid4(), run_id=uuid4(), auth_result=(user, key)
        )

    assert denied.value.msg_key == "workflow_run_not_found"
    assert denied.value.status_code == 404
    assert recorded == []
