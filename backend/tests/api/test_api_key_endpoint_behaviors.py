from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import api_keys
from app.schemas.api_key import APIKeyCreate
from app.schemas.response import BusinessError, ResponseCode


class _Query:
    def __init__(self, result):
        self.result = result

    def prefetch_related(self, *relations):
        return self

    async def first(self):
        return self.result


class _Relations:
    def __init__(self, items=()):
        self.items = list(items)
        self.add = AsyncMock()
        self.clear = AsyncMock()

    async def all(self):
        return self.items


def _api_key(*, owner_id=None, active=True):
    key = SimpleNamespace(
        id=uuid4(),
        name="automation",
        key_prefix="clou_example",
        user_id=owner_id or uuid4(),
        scopes=["chat"],
        rate_limit=1000,
        is_active=active,
        expires_at=None,
        last_used_at=None,
        created_at=None,
        updated_at=None,
        agents=_Relations(),
        workflows=_Relations(),
        save=AsyncMock(),
    )
    return key


@pytest.mark.asyncio
async def test_create_api_key_returns_secret_and_assigns_allowed_resources(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    agent = SimpleNamespace(id=uuid4())
    workflow = SimpleNamespace(id=uuid4())
    created = _api_key(owner_id=user.id)
    reloaded = _api_key(owner_id=user.id)
    reloaded.id = created.id

    create = AsyncMock(return_value=created)
    audit = AsyncMock()
    monkeypatch.setattr(
        api_keys, "collect_allowed_agents", AsyncMock(return_value=[agent])
    )
    monkeypatch.setattr(
        api_keys, "collect_allowed_workflows", AsyncMock(return_value=[workflow])
    )
    monkeypatch.setattr(
        api_keys.APIKey,
        "generate_key",
        MagicMock(return_value=("clou_secret", "clou_secret", "hash")),
    )
    monkeypatch.setattr(api_keys.APIKey, "create", create)
    monkeypatch.setattr(
        api_keys.APIKey, "filter", MagicMock(return_value=_Query(reloaded))
    )
    monkeypatch.setattr(api_keys.AuditLogService, "log", audit)

    result = await api_keys.create_api_key(
        request=SimpleNamespace(),
        data=APIKeyCreate(
            name="automation", agent_ids=[agent.id], workflow_ids=[workflow.id]
        ),
        current_user=user,
    )

    assert result["data"]["key"] == "clou_secret"
    assert create.await_args.kwargs["user_id"] == user.id
    created.agents.add.assert_awaited_once_with(agent)
    created.workflows.add.assert_awaited_once_with(workflow)
    assert audit.await_args.kwargs["metadata"]["agent_count"] == 1
    assert audit.await_args.kwargs["metadata"]["workflow_count"] == 1


@pytest.mark.asyncio
async def test_create_api_key_fails_if_created_record_cannot_be_reloaded(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    created = _api_key(owner_id=user.id)
    monkeypatch.setattr(api_keys, "collect_allowed_agents", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        api_keys, "collect_allowed_workflows", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        api_keys.APIKey,
        "generate_key",
        MagicMock(return_value=("clou_secret", "clou_secret", "hash")),
    )
    monkeypatch.setattr(api_keys.APIKey, "create", AsyncMock(return_value=created))
    monkeypatch.setattr(api_keys.APIKey, "filter", MagicMock(return_value=_Query(None)))
    monkeypatch.setattr(api_keys.AuditLogService, "log", AsyncMock())

    with pytest.raises(BusinessError) as caught:
        await api_keys.create_api_key(
            request=SimpleNamespace(),
            data=APIKeyCreate(name="automation"),
            current_user=user,
        )

    assert caught.value.code == ResponseCode.NOT_FOUND
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_api_key_owner_guard_denies_other_user_but_allows_superuser():
    key = _api_key()

    with pytest.raises(BusinessError) as caught:
        await api_keys.ensure_api_key_owner(
            key, SimpleNamespace(id=uuid4(), is_superuser=False)
        )

    assert caught.value.code == ResponseCode.PERMISSION_DENIED
    assert caught.value.status_code == 403
    await api_keys.ensure_api_key_owner(
        key, SimpleNamespace(id=uuid4(), is_superuser=True)
    )


@pytest.mark.asyncio
async def test_get_api_key_reports_missing_record(monkeypatch):
    monkeypatch.setattr(api_keys.APIKey, "filter", MagicMock(return_value=_Query(None)))

    with pytest.raises(BusinessError) as caught:
        await api_keys.get_api_key_or_404(uuid4())

    assert caught.value.code == ResponseCode.NOT_FOUND
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_deactivate_api_key_changes_state_and_rejects_repeat(monkeypatch):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    key = _api_key(owner_id=user.id)
    monkeypatch.setattr(api_keys, "get_api_key_or_404", AsyncMock(return_value=key))
    audit = AsyncMock()
    monkeypatch.setattr(api_keys.AuditLogService, "log", audit)

    result = await api_keys.deactivate_api_key(SimpleNamespace(), key.id, user)

    assert result["data"]["is_active"] is False
    key.save.assert_awaited_once()
    audit.assert_awaited_once()

    with pytest.raises(BusinessError) as caught:
        await api_keys.deactivate_api_key(SimpleNamespace(), key.id, user)

    assert caught.value.code == ResponseCode.BAD_REQUEST
    assert caught.value.msg_key == "api_key_already_inactive"
