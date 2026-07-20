from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.admin.endpoints import memories
from app.schemas.response import BusinessError, ResponseCode, error


class _Permission:
    def __init__(self, code: str):
        self.code = code


class _Role:
    def __init__(self, *codes: str):
        self.permissions = [_Permission(code) for code in codes]


class _Query:
    def __init__(self, rows=(), *, total=None, first=None, values=()):
        self.rows = list(rows)
        self.total = len(self.rows) if total is None else total
        self.first_result = first
        self.value_rows = list(values)
        self.filters = []
        self.prefetches = []
        self.ordering = None
        self.offset_value = None
        self.limit_value = None

    def filter(self, *args, **kwargs):
        self.filters.append((args, kwargs))
        return self

    def prefetch_related(self, *relations):
        self.prefetches.append(relations)
        return self

    def order_by(self, ordering):
        self.ordering = ordering
        return self

    def offset(self, value):
        self.offset_value = value
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def group_by(self, *_fields):
        return self

    def all(self):
        return self

    async def count(self):
        return self.total

    async def first(self):
        return self.first_result

    async def values(self, *_fields, **_kwargs):
        return self.value_rows

    def __await__(self):
        async def resolve():
            return self.rows

        return resolve().__await__()


def _entity(*, user_id=None):
    now = datetime(2026, 1, 2, 3, 4, tzinfo=UTC)
    user_id = user_id or uuid4()
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        user=SimpleNamespace(username="owner", avatar_url="avatar.png"),
        _fetched_relations={"user"},
        name="Project Atlas",
        entity_type="project",
        description="Knowledge graph",
        properties={"status": "active"},
        access_count=4,
        last_accessed_at=now,
        created_at=now,
        updated_at=now,
        outgoing_relations=SimpleNamespace(all=lambda: _Query(total=2)),
        incoming_relations=SimpleNamespace(all=lambda: _Query(total=1)),
        save=AsyncMock(),
        delete=AsyncMock(),
    )


def _relation(entity, *, user_id=None):
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id or entity.user_id,
        source_entity_id=entity.id,
        target_entity_id=uuid4(),
        source_entity=SimpleNamespace(name=entity.name),
        target_entity=SimpleNamespace(name="Customer Beta"),
        _fetched_relations={"source_entity", "target_entity"},
        relation_type="supports",
        description="Used by",
        properties={"confidence": 0.9},
        created_at=entity.created_at,
        delete=AsyncMock(),
    )


def test_memory_routes_require_their_admin_permissions():
    app = FastAPI()
    app.include_router(memories.router, prefix="/memories")
    user = SimpleNamespace(
        id=uuid4(), is_active=True, is_superuser=False, roles=[_Role("admin:user:read")]
    )

    async def current_user():
        return user

    @app.exception_handler(BusinessError)
    async def handle_business_error(_, exc: BusinessError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error(code=exc.code, msg=exc.msg, msg_key=exc.msg_key),
        )

    app.dependency_overrides[deps.get_current_active_user] = current_user

    with TestClient(app) as client:
        assert client.get("/memories/entities").status_code == 403
        assert client.put(f"/memories/entities/{uuid4()}", json={}).status_code == 403
        assert client.delete(f"/memories/relations/{uuid4()}").status_code == 403


@pytest.mark.asyncio
async def test_list_entities_applies_scope_filters_and_pagination():
    owner_ids = [uuid4(), uuid4()]
    entity = _entity(user_id=owner_ids[0])
    query = _Query([entity], total=7)

    with patch.object(memories.MemoryEntity, "all", return_value=query):
        response = await memories.list_entities(
            page=3,
            page_size=5,
            user_id=owner_ids,
            entity_type=["person", "project"],
            search="atlas",
            current_user=SimpleNamespace(),
        )

    assert query.filters[0] == ((), {"user_id__in": owner_ids})
    assert query.filters[1] == ((), {"entity_type__in": ["person", "project"]})
    assert query.filters[2][0][0]
    assert query.prefetches == [("user",)]
    assert query.ordering == "-created_at"
    assert query.offset_value == 10
    assert query.limit_value == 5
    assert response["data"].total == 7
    assert response["data"].items[0]["user_name"] == "owner"
    assert response["data"].items[0]["outgoing_relations_count"] == 2


@pytest.mark.asyncio
async def test_stats_aggregates_types_and_top_users():
    user_ids = [uuid4() for _ in range(12)]
    entity_queries = [
        _Query(total=14),
        _Query(
            values=[
                {"entity_type": "person", "count": 8},
                {"entity_type": "project", "count": 6},
            ]
        ),
        _Query(
            values=[
                {"user_id": user_id, "count": 20 - index}
                for index, user_id in enumerate(user_ids)
            ]
        ),
    ]
    users = [
        SimpleNamespace(id=user_id, username=f"user-{index}")
        for index, user_id in enumerate(user_ids[:10])
    ]

    with (
        patch.object(memories.MemoryEntity, "all", side_effect=entity_queries),
        patch.object(memories.MemoryRelation, "all", return_value=_Query(total=9)),
        patch.object(
            memories.User, "filter", return_value=_Query(users)
        ) as user_filter,
    ):
        response = await memories.get_stats(current_user=SimpleNamespace())

    assert response["data"]["total_entities"] == 14
    assert response["data"]["total_relations"] == 9
    assert response["data"]["by_type"] == {"person": 8, "project": 6}
    assert response["data"]["by_user"] == {
        f"user-{index}": 20 - index for index in range(10)
    }
    assert user_filter.call_args.kwargs == {"id__in": user_ids[:10]}


@pytest.mark.asyncio
async def test_get_entity_returns_both_relation_directions():
    entity = _entity()
    outgoing = _relation(entity)
    incoming = _relation(entity)
    entity.outgoing_relations = SimpleNamespace(all=lambda: _Query([outgoing], total=1))
    entity.incoming_relations = SimpleNamespace(all=lambda: _Query([incoming], total=1))
    query = _Query(first=entity)

    with patch.object(
        memories.MemoryEntity, "filter", return_value=query
    ) as entity_filter:
        response = await memories.get_entity(entity.id, current_user=SimpleNamespace())

    assert entity_filter.call_args.kwargs == {"id": entity.id}
    assert (
        response["data"]["outgoing_relations"][0]["target_entity_name"]
        == "Customer Beta"
    )
    assert (
        response["data"]["incoming_relations"][0]["source_entity_name"]
        == "Project Atlas"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["get", "update", "delete"])
async def test_entity_operations_reject_missing_entities(operation):
    with patch.object(memories.MemoryEntity, "filter", return_value=_Query(first=None)):
        with pytest.raises(BusinessError) as exc_info:
            if operation == "get":
                await memories.get_entity(uuid4(), current_user=SimpleNamespace())
            elif operation == "update":
                await memories.update_entity(
                    uuid4(),
                    memories.MemoryEntityUpdate(description="new"),
                    SimpleNamespace(),
                    current_user=SimpleNamespace(),
                )
            else:
                await memories.delete_entity(
                    uuid4(), SimpleNamespace(), current_user=SimpleNamespace()
                )

    assert exc_info.value.code == ResponseCode.NOT_FOUND
    assert exc_info.value.msg_key == "memory_entity_not_found"


@pytest.mark.asyncio
async def test_update_entity_persists_changes_then_audits():
    entity = _entity()
    audit = AsyncMock()

    with (
        patch.object(
            memories.MemoryEntity, "filter", return_value=_Query(first=entity)
        ),
        patch.object(memories.AuditLogService, "log", audit),
    ):
        response = await memories.update_entity(
            entity.id,
            memories.MemoryEntityUpdate(description="Updated", properties={"tier": 2}),
            SimpleNamespace(),
            current_user=SimpleNamespace(id=uuid4()),
        )

    entity.save.assert_awaited_once()
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["changes"]["before"] == {
        "description": "Knowledge graph",
        "properties": {"status": "active"},
    }
    assert response["data"]["description"] == "Updated"
    assert response["data"]["properties"] == {"tier": 2}


@pytest.mark.asyncio
async def test_update_entity_persistence_failure_skips_audit():
    entity = _entity()
    entity.save.side_effect = RuntimeError("database unavailable")
    audit = AsyncMock()

    with (
        patch.object(
            memories.MemoryEntity, "filter", return_value=_Query(first=entity)
        ),
        patch.object(memories.AuditLogService, "log", audit),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        await memories.update_entity(
            entity.id,
            memories.MemoryEntityUpdate(description="Updated"),
            SimpleNamespace(),
            current_user=SimpleNamespace(),
        )

    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_entity_deletes_then_audits_owner_context():
    entity = _entity()
    audit = AsyncMock()

    with (
        patch.object(
            memories.MemoryEntity, "filter", return_value=_Query(first=entity)
        ),
        patch.object(memories.AuditLogService, "log", audit),
    ):
        await memories.delete_entity(
            entity.id, SimpleNamespace(), current_user=SimpleNamespace(id=uuid4())
        )

    entity.delete.assert_awaited_once()
    assert audit.await_args.kwargs["resource_name"] == "Project Atlas"
    assert audit.await_args.kwargs["metadata"]["owner_user_id"] == str(entity.user_id)


@pytest.mark.asyncio
async def test_list_relations_applies_owner_type_and_pagination():
    entity = _entity()
    relation = _relation(entity)
    query = _Query([relation], total=3)

    with patch.object(memories.MemoryRelation, "all", return_value=query):
        response = await memories.list_relations(
            page=2,
            page_size=2,
            user_id=entity.user_id,
            relation_type="supports",
            current_user=SimpleNamespace(),
        )

    assert query.filters == [
        ((), {"user_id": entity.user_id}),
        ((), {"relation_type": "supports"}),
    ]
    assert query.prefetches == [("source_entity", "target_entity")]
    assert query.offset_value == 2
    assert response["data"].items[0]["source_entity_name"] == "Project Atlas"


@pytest.mark.asyncio
async def test_delete_relation_handles_missing_and_persistence_failure():
    relation_id = uuid4()
    with patch.object(
        memories.MemoryRelation, "filter", return_value=_Query(first=None)
    ):
        with pytest.raises(BusinessError) as exc_info:
            await memories.delete_relation(
                relation_id, SimpleNamespace(), current_user=SimpleNamespace()
            )
    assert exc_info.value.msg_key == "memory_relation_not_found"

    entity = _entity()
    relation = _relation(entity)
    relation.delete.side_effect = RuntimeError("delete failed")
    audit = AsyncMock()
    with (
        patch.object(
            memories.MemoryRelation, "filter", return_value=_Query(first=relation)
        ),
        patch.object(memories.AuditLogService, "log", audit),
        pytest.raises(RuntimeError, match="delete failed"),
    ):
        await memories.delete_relation(
            relation.id, SimpleNamespace(), current_user=SimpleNamespace()
        )
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_relation_deletes_then_audits_endpoints():
    entity = _entity()
    relation = _relation(entity)
    audit = AsyncMock()

    with (
        patch.object(
            memories.MemoryRelation, "filter", return_value=_Query(first=relation)
        ),
        patch.object(memories.AuditLogService, "log", audit),
    ):
        await memories.delete_relation(
            relation.id, SimpleNamespace(), current_user=SimpleNamespace(id=uuid4())
        )

    relation.delete.assert_awaited_once()
    assert audit.await_args.kwargs["resource_name"] == "Project Atlas -> Customer Beta"
    assert audit.await_args.kwargs["metadata"] == {
        "relation_type": "supports",
        "source_entity": "Project Atlas",
        "target_entity": "Customer Beta",
        "owner_user_id": str(relation.user_id),
    }
