from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import memories
from app.schemas.response import BusinessError


class _Query:
    def __init__(self, result=None, *, count=0, values=None):
        self.result = result
        self.total = count
        self.value_rows = values or []
        self.calls = []

    def filter(self, *args, **kwargs):
        self.calls.append(("filter", args, kwargs))
        return self

    def prefetch_related(self, *args):
        self.calls.append(("prefetch_related", args, {}))
        return self

    def order_by(self, *args):
        self.calls.append(("order_by", args, {}))
        return self

    def offset(self, value):
        self.calls.append(("offset", (value,), {}))
        return self

    def limit(self, value):
        self.calls.append(("limit", (value,), {}))
        return self

    def group_by(self, *args):
        self.calls.append(("group_by", args, {}))
        return self

    async def count(self):
        return self.total

    async def first(self):
        return self.result

    async def all(self):
        return self.result

    async def values(self, *args, **kwargs):
        self.calls.append(("values", args, kwargs))
        return self.value_rows

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


class _RelationManager:
    def __init__(self, count=0):
        self.query = _Query([], count=count)

    def all(self):
        return self.query


def _entity(**overrides):
    user_id = uuid4()
    values = {
        "id": uuid4(),
        "user_id": user_id,
        "user": SimpleNamespace(username="owner", avatar_url=None),
        "_fetched_relations": {"user"},
        "name": "Project Atlas",
        "entity_type": "project",
        "description": "Original",
        "properties": {"status": "active"},
        "access_count": 2,
        "last_accessed_at": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "outgoing_relations": _RelationManager(3),
        "incoming_relations": _RelationManager(1),
        "save": AsyncMock(),
        "delete": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def admin():
    return SimpleNamespace(id=uuid4(), username="admin")


@pytest.mark.anyio
async def test_list_entities_applies_filters_pagination_and_serializes(admin):
    entity = _entity()
    query = _Query([entity], count=1)
    owner_id = uuid4()

    with patch.object(memories.MemoryEntity, "all", return_value=query):
        response = await memories.list_entities(
            page=2,
            page_size=5,
            user_id=[owner_id],
            entity_type=["project"],
            search="atlas",
            current_user=admin,
        )

    data = response["data"]
    assert data.total == 1
    assert data.page == 2
    assert data.items[0]["user_name"] == "owner"
    assert data.items[0]["outgoing_relations_count"] == 3
    assert ("filter", (), {"user_id__in": [owner_id]}) in query.calls
    assert ("filter", (), {"entity_type__in": ["project"]}) in query.calls
    assert ("offset", (5,), {}) in query.calls


@pytest.mark.anyio
async def test_stats_sorts_limits_users_and_skips_deleted_owners(admin):
    included_id = uuid4()
    deleted_id = uuid4()
    entity_queries = [
        _Query(count=12),
        _Query(values=[{"entity_type": "person", "count": 7}]),
        _Query(
            values=[
                {"user_id": included_id, "count": 8},
                {"user_id": deleted_id, "count": 4},
            ]
        ),
    ]

    with (
        patch.object(memories.MemoryEntity, "all", side_effect=entity_queries),
        patch.object(memories.MemoryRelation, "all", return_value=_Query(count=5)),
        patch.object(
            memories.User,
            "filter",
            return_value=_Query([SimpleNamespace(id=included_id, username="alice")]),
        ),
    ):
        response = await memories.get_stats(current_user=admin)

    assert response["data"] == {
        "total_entities": 12,
        "total_relations": 5,
        "by_type": {"person": 7},
        "by_user": {"alice": 8},
    }


@pytest.mark.anyio
async def test_update_entity_changes_only_supplied_field_and_audits(admin):
    entity = _entity()
    audit = AsyncMock()
    request = MagicMock()

    with (
        patch.object(memories.MemoryEntity, "filter", return_value=_Query(entity)),
        patch.object(memories.AuditLogService, "log", audit),
        patch.object(memories, "t", return_value="updated"),
    ):
        response = await memories.update_entity(
            entity.id,
            memories.MemoryEntityUpdate(description="Revised"),
            request,
            current_user=admin,
        )

    assert entity.description == "Revised"
    assert entity.properties == {"status": "active"}
    entity.save.assert_awaited_once()
    assert response["data"]["description"] == "Revised"
    assert audit.await_args.kwargs["changes"] == {
        "before": {
            "description": "Original",
            "properties": {"status": "active"},
        },
        "after": {
            "description": "Revised",
            "properties": {"status": "active"},
        },
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("function", "model", "extra_args"),
    [
        (memories.get_entity, memories.MemoryEntity, ()),
        (
            memories.update_entity,
            memories.MemoryEntity,
            (memories.MemoryEntityUpdate(), MagicMock()),
        ),
        (memories.delete_entity, memories.MemoryEntity, (MagicMock(),)),
        (memories.delete_relation, memories.MemoryRelation, (MagicMock(),)),
    ],
)
async def test_detail_and_mutation_endpoints_reject_missing_records(
    admin, function, model, extra_args
):
    with (
        patch.object(model, "filter", return_value=_Query(None)),
        pytest.raises(BusinessError) as exc,
    ):
        await function(uuid4(), *extra_args, current_user=admin)

    assert exc.value.code == memories.ResponseCode.NOT_FOUND
