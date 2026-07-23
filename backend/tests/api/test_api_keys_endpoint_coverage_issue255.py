from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import api_keys
from app.schemas.api_key import APIKeyUpdate
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, result=(), counts=()):
        self.result = result
        self.count = AsyncMock(
            side_effect=counts or None,
            return_value=len(result) if isinstance(result, (list, tuple)) else 0,
        )
        self.filter = MagicMock(return_value=self)
        self.offset = MagicMock(return_value=self)
        self.limit = MagicMock(return_value=self)
        self.order_by = MagicMock(return_value=self)
        self.prefetch_related = MagicMock(return_value=self)

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()

    async def first(self):
        return self.result


class Relations:
    def __init__(self, items=()):
        self.items = list(items)
        self.add = AsyncMock()
        self.clear = AsyncMock()

    async def all(self):
        return self.items


def user(*, superuser=False):
    return SimpleNamespace(id=uuid4(), is_superuser=superuser)


def key(*, owner_id=None, agents=(), workflows=(), with_user=False):
    value = SimpleNamespace(
        id=uuid4(),
        name="fake key",
        key_prefix="clou_fakepre",
        user_id=owner_id or uuid4(),
        scopes=["chat"],
        rate_limit=100,
        is_active=True,
        expires_at=None,
        last_used_at=None,
        created_at=None,
        updated_at=None,
        agents=Relations(agents),
        workflows=Relations(workflows),
        update_from_dict=AsyncMock(),
        save=AsyncMock(),
        delete=AsyncMock(),
    )
    if with_user:
        value.user = SimpleNamespace(id=value.user_id, username="owner")
    return value


@pytest.mark.asyncio
async def test_build_response_controls_optional_relations_and_user():
    agent = SimpleNamespace(id=uuid4(), name="agent", icon=None)
    workflow = SimpleNamespace(id=uuid4(), name="workflow", icon="icon")
    api_key = key(agents=[agent], workflows=[workflow], with_user=True)

    full = await api_keys.build_api_key_response(api_key)
    minimal = await api_keys.build_api_key_response(
        api_key, include_agents=False, include_workflows=False
    )

    assert full["user"]["username"] == "owner"
    assert full["agents"][0].id == agent.id
    assert full["workflows"][0].id == workflow.id
    assert minimal["agents"] == []
    assert minimal["workflows"] == []


@pytest.mark.asyncio
async def test_access_collectors_use_each_authorization_boundary(monkeypatch):
    current_user = user()
    agent_ids = [uuid4(), uuid4()]
    workflow_ids = [uuid4()]
    agent_check = AsyncMock(side_effect=["agent-1", "agent-2"])
    workflow_check = AsyncMock(return_value="workflow-1")
    monkeypatch.setattr(api_keys, "check_agent_access", agent_check)
    monkeypatch.setattr(api_keys, "check_workflow_access", workflow_check)

    assert await api_keys.collect_allowed_agents(agent_ids, current_user) == [
        "agent-1",
        "agent-2",
    ]
    assert await api_keys.collect_allowed_workflows(workflow_ids, current_user) == [
        "workflow-1"
    ]
    assert await api_keys.collect_allowed_agents(None, current_user) == []
    assert await api_keys.collect_allowed_workflows(None, current_user) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("superuser", [True, False])
async def test_list_api_keys_applies_visibility_and_filters(monkeypatch, superuser):
    current_user = user(superuser=superuser)
    item = key(owner_id=current_user.id)
    query = Query([item])
    all_mock = MagicMock(return_value=query)
    filter_mock = MagicMock(return_value=query)
    rendered = AsyncMock(return_value={"id": item.id})
    monkeypatch.setattr(api_keys.APIKey, "all", all_mock)
    monkeypatch.setattr(api_keys.APIKey, "filter", filter_mock)
    monkeypatch.setattr(api_keys, "build_api_key_response", rendered)

    result = await api_keys.list_api_keys(
        page=2,
        page_size=5,
        status=["active", "inactive", "expired"],
        user_id=[uuid4()],
        search="fake",
        current_user=current_user,
    )

    assert result["data"] == {
        "items": [{"id": item.id}],
        "total": 1,
        "page": 2,
        "page_size": 5,
    }
    query.offset.assert_called_once_with(5)
    assert query.filter.call_count == (3 if superuser else 2)
    if superuser:
        all_mock.assert_called_once_with()
    else:
        filter_mock.assert_called_once_with(user_id=current_user.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("superuser", [True, False])
async def test_api_key_stats_use_role_scoped_query(monkeypatch, superuser):
    current_user = user(superuser=superuser)
    query = Query(counts=[7, 4, 2, 1])
    all_mock = MagicMock(return_value=query)
    filter_mock = MagicMock(return_value=query)
    monkeypatch.setattr(api_keys.APIKey, "all", all_mock)
    monkeypatch.setattr(api_keys.APIKey, "filter", filter_mock)

    result = await api_keys.get_api_key_stats(current_user)

    assert result["data"] == {"total": 7, "active": 4, "inactive": 2, "expired": 1}
    if superuser:
        all_mock.assert_called_once_with()
    else:
        filter_mock.assert_called_once_with(user_id=current_user.id)


@pytest.mark.asyncio
async def test_get_api_key_lookup_returns_found_record(monkeypatch):
    api_key = key()
    filter_mock = MagicMock(return_value=Query(api_key))
    monkeypatch.setattr(api_keys.APIKey, "filter", filter_mock)

    assert await api_keys.get_api_key_or_404(api_key.id) is api_key
    filter_mock.assert_called_once_with(id=api_key.id)


@pytest.mark.asyncio
async def test_get_api_key_returns_owned_key(monkeypatch):
    current_user = user()
    api_key = key(owner_id=current_user.id)
    monkeypatch.setattr(api_keys, "get_api_key_or_404", AsyncMock(return_value=api_key))
    monkeypatch.setattr(
        api_keys, "build_api_key_response", AsyncMock(return_value={"id": api_key.id})
    )

    result = await api_keys.get_api_key(api_key.id, current_user)

    assert result["data"] == {"id": api_key.id}


@pytest.mark.asyncio
async def test_update_api_key_replaces_relations_fields_and_audits(monkeypatch):
    current_user = user()
    api_key = key(owner_id=current_user.id)
    reloaded = key(owner_id=current_user.id)
    agent = SimpleNamespace(id=uuid4())
    workflow = SimpleNamespace(id=uuid4())
    data = APIKeyUpdate(
        name="renamed", agent_ids=[agent.id], workflow_ids=[workflow.id]
    )
    monkeypatch.setattr(api_keys, "get_api_key_or_404", AsyncMock(return_value=api_key))
    monkeypatch.setattr(
        api_keys, "collect_allowed_agents", AsyncMock(return_value=[agent])
    )
    monkeypatch.setattr(
        api_keys, "collect_allowed_workflows", AsyncMock(return_value=[workflow])
    )
    monkeypatch.setattr(
        api_keys.APIKey, "filter", MagicMock(return_value=Query(reloaded))
    )
    audit = AsyncMock()
    monkeypatch.setattr(api_keys.AuditLogService, "log", audit)

    result = await api_keys.update_api_key(
        request=SimpleNamespace(),
        api_key_id=api_key.id,
        data=data,
        current_user=current_user,
    )

    api_key.agents.clear.assert_awaited_once_with()
    api_key.agents.add.assert_awaited_once_with(agent)
    api_key.workflows.clear.assert_awaited_once_with()
    api_key.workflows.add.assert_awaited_once_with(workflow)
    api_key.update_from_dict.assert_awaited_once_with({"name": "renamed"})
    api_key.save.assert_awaited_once_with()
    assert audit.await_args.kwargs["metadata"]["fields_updated"] == [
        "name",
        "agent_ids",
        "workflow_ids",
    ]
    assert result["data"]["id"] == reloaded.id


@pytest.mark.asyncio
async def test_update_api_key_clears_relations_and_reports_failed_reload(monkeypatch):
    current_user = user()
    api_key = key(owner_id=current_user.id)
    monkeypatch.setattr(api_keys, "get_api_key_or_404", AsyncMock(return_value=api_key))
    monkeypatch.setattr(api_keys.APIKey, "filter", MagicMock(return_value=Query(None)))

    with pytest.raises(BusinessError) as exc_info:
        await api_keys.update_api_key(
            request=SimpleNamespace(),
            api_key_id=api_key.id,
            data=APIKeyUpdate(agent_ids=[], workflow_ids=[]),
            current_user=current_user,
        )

    api_key.agents.clear.assert_awaited_once_with()
    api_key.agents.add.assert_not_awaited()
    api_key.workflows.clear.assert_awaited_once_with()
    api_key.workflows.add.assert_not_awaited()
    api_key.update_from_dict.assert_not_awaited()
    assert exc_info.value.code == ResponseCode.NOT_FOUND


@pytest.mark.asyncio
async def test_delete_api_key_audits_before_deleting(monkeypatch):
    current_user = user()
    api_key = key(owner_id=current_user.id)
    audit = AsyncMock()
    monkeypatch.setattr(api_keys, "get_api_key_or_404", AsyncMock(return_value=api_key))
    monkeypatch.setattr(api_keys.AuditLogService, "log", audit)

    result = await api_keys.delete_api_key(SimpleNamespace(), api_key.id, current_user)

    audit.assert_awaited_once()
    api_key.delete.assert_awaited_once_with()
    assert result["data"]["key_prefix"] == "clou_fakepre"
