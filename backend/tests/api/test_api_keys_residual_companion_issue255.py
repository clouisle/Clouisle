from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import api_keys
from app.schemas.api_key import APIKeyUpdate


class APIKeyQuery:
    def __init__(self, result=None):
        self.result = result or []
        self.filters = []

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    def offset(self, _value):
        return self

    def limit(self, _value):
        return self

    def order_by(self, *_fields):
        return self

    def prefetch_related(self, *_relations):
        return self

    async def count(self):
        return len(self.result)

    async def first(self):
        return self.result[0] if self.result else None

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status", [["active"], ["inactive"], ["expired"], ["active", "inactive", "expired"]]
)
async def test_api_keys_issue255_list_builds_each_status_condition(monkeypatch, status):
    query = APIKeyQuery()
    monkeypatch.setattr(api_keys.APIKey, "all", lambda: query)

    result = await api_keys.list_api_keys(
        status=status,
        user_id=None,
        search="prefix",
        current_user=SimpleNamespace(is_superuser=True),
    )

    assert result["data"]["total"] == 0
    assert len(query.filters) == 2
    assert query.filters[0][0]
    assert query.filters[1][0]


@pytest.mark.anyio
async def test_api_keys_issue255_update_omits_relationship_changes(monkeypatch):
    api_key_id = uuid4()
    owner = SimpleNamespace(id=uuid4(), is_superuser=False)
    relation_agents = SimpleNamespace(clear=AsyncMock(), add=AsyncMock())
    relation_workflows = SimpleNamespace(clear=AsyncMock(), add=AsyncMock())
    item = SimpleNamespace(
        id=api_key_id,
        user_id=owner.id,
        name="key",
        agents=relation_agents,
        workflows=relation_workflows,
        update_from_dict=AsyncMock(),
        save=AsyncMock(),
    )
    monkeypatch.setattr(api_keys, "get_api_key_or_404", AsyncMock(return_value=item))
    monkeypatch.setattr(api_keys, "collect_allowed_agents", AsyncMock())
    monkeypatch.setattr(api_keys, "collect_allowed_workflows", AsyncMock())
    monkeypatch.setattr(
        api_keys.APIKey, "filter", lambda **_kwargs: APIKeyQuery([item])
    )
    monkeypatch.setattr(api_keys, "build_api_key_response", AsyncMock(return_value={}))
    monkeypatch.setattr(api_keys.AuditLogService, "log", AsyncMock())

    await api_keys.update_api_key(
        request=SimpleNamespace(),
        api_key_id=api_key_id,
        data=APIKeyUpdate(),
        current_user=owner,
    )

    api_keys.collect_allowed_agents.assert_not_awaited()
    api_keys.collect_allowed_workflows.assert_not_awaited()
    relation_agents.clear.assert_not_awaited()
    relation_workflows.clear.assert_not_awaited()
    item.save.assert_not_awaited()
    api_keys.AuditLogService.log.assert_awaited_once()
