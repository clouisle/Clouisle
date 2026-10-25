from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import feishu_knowledge as endpoint
from app.schemas.response import BusinessError, ResponseCode


def test_source_update_validator_preserves_none_and_trims_nonblank_name():
    assert endpoint.SourceUpdate.not_blank(None) is None
    assert endpoint.SourceUpdate.not_blank("  Handbook  ") == "Handbook"


@pytest.mark.asyncio
async def test_update_source_without_schedule_fields_leaves_schedule_unchanged(
    monkeypatch,
):
    source = SimpleNamespace(
        id=uuid4(),
        name="Existing",
        dispatch_token="active-token",
        lease_expires_at="lease-expiry",
        status="running",
        next_sync_at="existing-schedule",
        save=AsyncMock(),
    )

    @asynccontextmanager
    async def source_lock(_source_id):
        yield

    monkeypatch.setattr(endpoint.service, "source_lock", source_lock)
    monkeypatch.setattr(endpoint.service, "get_source", AsyncMock(return_value=source))
    monkeypatch.setattr(
        endpoint.service, "source_output", lambda value: {"name": value.name}
    )
    monkeypatch.setattr(endpoint.AuditLogService, "log", AsyncMock())

    response = await endpoint.update_source(
        source.id,
        endpoint.SourceUpdate(),
        request=MagicMock(),
        current_user=SimpleNamespace(id=uuid4(), is_superuser=True),
    )

    assert response["data"] == {"name": "Existing"}
    assert source.next_sync_at == "existing-schedule"
    assert source.status == "running"
    source.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_require_superuser_rejects_regular_user_and_accepts_superuser():
    with pytest.raises(BusinessError) as raised:
        await endpoint.require_superuser(SimpleNamespace(is_superuser=False))

    assert raised.value.code == ResponseCode.INSUFFICIENT_PRIVILEGES
    assert raised.value.status_code == 403
    allowed = SimpleNamespace(is_superuser=True)
    assert await endpoint.require_superuser(allowed) is allowed


@pytest.mark.asyncio
async def test_list_spaces_maps_provider_failure_to_public_gateway_error(monkeypatch):
    monkeypatch.setattr(
        endpoint.service,
        "configured_client",
        AsyncMock(
            return_value=SimpleNamespace(
                list_wiki_spaces=AsyncMock(
                    side_effect=RuntimeError("private provider details")
                )
            )
        ),
    )
    monkeypatch.setattr(
        endpoint.service, "public_error", lambda exc: "Feishu unavailable"
    )

    with pytest.raises(BusinessError) as raised:
        await endpoint.list_spaces(current_user=SimpleNamespace(is_superuser=True))

    assert raised.value.status_code == 502
    assert raised.value.msg == "Feishu unavailable"
    assert "private provider details" not in str(raised.value)


@pytest.mark.asyncio
async def test_list_spaces_returns_wiki_spaces_when_provider_succeeds(monkeypatch):
    spaces = [{"space_id": "s1", "name": "Handbook"}]
    client = SimpleNamespace(list_wiki_spaces=AsyncMock(return_value=spaces))
    monkeypatch.setattr(
        endpoint.service, "configured_client", AsyncMock(return_value=client)
    )

    response = await endpoint.list_spaces(
        current_user=SimpleNamespace(is_superuser=True)
    )

    assert response["data"] == spaces


@pytest.mark.asyncio
async def test_list_targets_excludes_deleted_teams(monkeypatch):
    live = SimpleNamespace(
        id=uuid4(),
        name="Active KB",
        team=SimpleNamespace(name="Core", is_deleted=False),
    )
    deleted_team = SimpleNamespace(
        id=uuid4(), name="Hidden KB", team=SimpleNamespace(name="Gone", is_deleted=True)
    )

    class Query:
        def prefetch_related(self, *args):
            return self

        def order_by(self, *args):
            return self

        def __await__(self):
            async def rows():
                return [live, deleted_team]

            return rows().__await__()

    monkeypatch.setattr(endpoint.KnowledgeBase, "filter", lambda **_kwargs: Query())

    response = await endpoint.list_targets(
        current_user=SimpleNamespace(is_superuser=True)
    )

    assert response["data"] == [
        {"id": str(live.id), "name": "Active KB", "team_name": "Core"}
    ]


@pytest.mark.asyncio
async def test_create_source_rejects_inactive_or_missing_target(monkeypatch):
    class Query:
        def using_db(self, _connection):
            return self

        def select_for_update(self):
            return self

        async def first(self):
            return None

    @asynccontextmanager
    async def transaction():
        yield object()

    client = SimpleNamespace(
        list_wiki_spaces=AsyncMock(
            return_value=[{"space_id": "space-a", "name": "Docs"}]
        )
    )
    monkeypatch.setattr(
        endpoint.service, "configured_client", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(endpoint, "in_transaction", transaction)
    monkeypatch.setattr(endpoint.KnowledgeBase, "filter", lambda **_kwargs: Query())
    create = AsyncMock(side_effect=AssertionError("source persisted without target"))
    monkeypatch.setattr(endpoint.FeishuKnowledgeSource, "create", create)

    with pytest.raises(BusinessError) as raised:
        await endpoint.create_source(
            endpoint.SourceCreate(
                knowledge_base_id=uuid4(), space_id="space-a", name="Docs"
            ),
            request=MagicMock(),
            current_user=SimpleNamespace(id=uuid4(), is_superuser=True),
        )

    assert raised.value.msg_key == "feishu_knowledge_target_unavailable"
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_source_applies_disable_cleanup_and_enable_schedule(monkeypatch):
    disabled = SimpleNamespace(
        id=uuid4(),
        name="Docs",
        dispatch_token="lease",
        lease_expires_at=object(),
        status="running",
        next_sync_at=None,
        save=AsyncMock(),
    )
    enabled = SimpleNamespace(
        id=uuid4(),
        name="Docs",
        dispatch_token=None,
        lease_expires_at=None,
        status="idle",
        next_sync_at=None,
        save=AsyncMock(),
    )
    sources = {"disable": disabled, "enable": enabled}

    @asynccontextmanager
    async def source_lock(_source_id):
        yield

    get_source = AsyncMock(side_effect=lambda source_id: sources[str(source_id)])
    monkeypatch.setattr(endpoint.service, "source_lock", source_lock)
    monkeypatch.setattr(endpoint.service, "get_source", get_source)
    monkeypatch.setattr(endpoint.service, "utcnow", lambda: "scheduled-now")
    monkeypatch.setattr(
        endpoint.service, "source_output", lambda source: {"name": source.name}
    )
    monkeypatch.setattr(endpoint.AuditLogService, "log", AsyncMock())

    await endpoint.update_source(
        "disable",
        endpoint.SourceUpdate(is_enabled=False),
        request=MagicMock(),
        current_user=SimpleNamespace(id=uuid4(), is_superuser=True),
    )
    assert disabled.dispatch_token is None
    assert disabled.lease_expires_at is None
    assert disabled.status == "idle"
    assert disabled.next_sync_at is None
    disabled.save.assert_awaited_once()

    await endpoint.update_source(
        "enable",
        endpoint.SourceUpdate(is_enabled=True),
        request=MagicMock(),
        current_user=SimpleNamespace(id=uuid4(), is_superuser=True),
    )
    assert enabled.is_enabled is True
    assert enabled.next_sync_at == "scheduled-now"
    enabled.save.assert_awaited_once()
