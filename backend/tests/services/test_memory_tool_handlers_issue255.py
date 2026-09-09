from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.models.memory import EntityType
from app.services import memory

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("00000000-0000-0000-0000-000000000002")
TARGET_ID = UUID("00000000-0000-0000-0000-000000000003")
ENTITY_ID = UUID("00000000-0000-0000-0000-000000000004")
RELATION_ID = UUID("00000000-0000-0000-0000-000000000005")


class Query:
    def __init__(self, *, first_result=None, all_results=None):
        self.first_result = first_result
        self.all_results = all_results or []

    async def first(self):
        return self.first_result

    async def all(self):
        return self.all_results


@pytest.fixture(autouse=True)
def fake_i18n(monkeypatch):
    def translate(key, **kwargs):
        suffix = f":{kwargs}" if kwargs else ""
        return f"{key}{suffix}"

    monkeypatch.setattr(memory, "t", translate)


@pytest.mark.asyncio
async def test_handle_create_entity_reports_similar_names_and_audits(monkeypatch):
    user = SimpleNamespace(id=USER_ID)
    similar = [
        SimpleNamespace(name="Python"),
        SimpleNamespace(name="Python data"),
        SimpleNamespace(name="Rust"),
    ]
    entity = SimpleNamespace(id=ENTITY_ID, name="python", entity_type=EntityType.SKILL)
    audit_log = AsyncMock()

    monkeypatch.setattr(memory.User, "get", AsyncMock(return_value=user))
    monkeypatch.setattr(
        memory.MemoryEntity,
        "filter",
        lambda **kwargs: (
            Query(all_results=similar)
            if kwargs == {"user_id": USER_ID, "entity_type": "skill"}
            else Query()
        ),
    )
    monkeypatch.setattr(
        memory.MemoryService, "create_entity", AsyncMock(return_value=entity)
    )
    monkeypatch.setattr(memory.AuditLogService, "log", audit_log)

    result = await memory.MemoryService.handle_create_entity(
        USER_ID,
        "python",
        "skill",
        description="uses daily",
        properties={"level": "high"},
    )

    assert result["success"] is True
    assert result["entity_id"] == str(ENTITY_ID)
    assert result["similar_entities"] == ["Python", "Python data"]
    assert "memory_similar_entities_notice" in result["message"]
    audit_log.assert_awaited_once()
    assert audit_log.await_args.kwargs["status"] == "success"


@pytest.mark.asyncio
async def test_handle_create_entity_logs_failure_when_create_raises(monkeypatch):
    audit_log = AsyncMock()

    monkeypatch.setattr(
        memory.User, "get", AsyncMock(return_value=SimpleNamespace(id=USER_ID))
    )
    monkeypatch.setattr(memory.MemoryEntity, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(
        memory.MemoryService,
        "create_entity",
        AsyncMock(side_effect=RuntimeError("embed failed")),
    )
    monkeypatch.setattr(memory.AuditLogService, "log", audit_log)

    result = await memory.MemoryService.handle_create_entity(USER_ID, "Python", "skill")

    assert result == {"success": False, "error": "memory_tool_execution_failed"}
    assert audit_log.await_count == 1
    assert audit_log.await_args.kwargs["status"] == "failed"
    assert audit_log.await_args.kwargs["error_message"] == "embed failed"


@pytest.mark.asyncio
async def test_handle_create_relation_returns_source_missing_error(monkeypatch):
    audit_log = AsyncMock()

    monkeypatch.setattr(
        memory.User, "get", AsyncMock(return_value=SimpleNamespace(id=USER_ID))
    )
    monkeypatch.setattr(memory.MemoryEntity, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(memory.AuditLogService, "log", audit_log)

    result = await memory.MemoryService.handle_create_relation(
        USER_ID, "Python", "Project", "related_to"
    )

    assert result["success"] is False
    assert "memory_source_entity_not_found" in result["error"]
    audit_log.assert_awaited_once()
    assert audit_log.await_args.kwargs["status"] == "failed"
    assert audit_log.await_args.kwargs["resource_name"] == "Python -> Project"


@pytest.mark.asyncio
async def test_handle_create_relation_success_uses_found_entities(monkeypatch):
    source = SimpleNamespace(id=SOURCE_ID, name="Python")
    target = SimpleNamespace(id=TARGET_ID, name="Project")
    relation = SimpleNamespace(id=RELATION_ID)
    audit_log = AsyncMock()

    def filter_entity(**kwargs):
        if kwargs == {"user_id": USER_ID, "name": "Python"}:
            return Query(first_result=source)
        if kwargs == {"user_id": USER_ID, "name": "Project"}:
            return Query(first_result=target)
        return Query()

    monkeypatch.setattr(
        memory.User, "get", AsyncMock(return_value=SimpleNamespace(id=USER_ID))
    )
    monkeypatch.setattr(memory.MemoryEntity, "filter", filter_entity)
    monkeypatch.setattr(
        memory.MemoryService, "create_relation", AsyncMock(return_value=relation)
    )
    monkeypatch.setattr(memory.AuditLogService, "log", audit_log)

    result = await memory.MemoryService.handle_create_relation(
        USER_ID, "Python", "Project", "related_to", description="used in"
    )

    assert result["success"] is True
    assert result["relation_id"] == str(RELATION_ID)
    memory.MemoryService.create_relation.assert_awaited_once_with(
        user_id=USER_ID,
        source_entity_id=SOURCE_ID,
        target_entity_id=TARGET_ID,
        relation_type="related_to",
        description="used in",
    )


@pytest.mark.asyncio
async def test_handle_create_relation_target_missing_and_exception(monkeypatch):
    source = SimpleNamespace(id=SOURCE_ID, name="Python")
    audit_log = AsyncMock()

    def filter_entity(**kwargs):
        if kwargs == {"user_id": USER_ID, "name": "Python"}:
            return Query(first_result=source)
        return Query(first_result=None)

    monkeypatch.setattr(
        memory.User, "get", AsyncMock(return_value=SimpleNamespace(id=USER_ID))
    )
    monkeypatch.setattr(memory.MemoryEntity, "filter", filter_entity)
    monkeypatch.setattr(memory.AuditLogService, "log", audit_log)

    # 1. Target missing
    res_target = await memory.MemoryService.handle_create_relation(
        USER_ID, "Python", "Missing", "related_to"
    )
    assert res_target["success"] is False
    assert "memory_target_entity_not_found" in res_target["error"]

    # 2. create_relation raises exception
    target = SimpleNamespace(id=TARGET_ID, name="Target")

    def filter_both(**kwargs):
        if kwargs == {"user_id": USER_ID, "name": "Python"}:
            return Query(first_result=source)
        if kwargs == {"user_id": USER_ID, "name": "Target"}:
            return Query(first_result=target)
        return Query()

    monkeypatch.setattr(memory.MemoryEntity, "filter", filter_both)
    monkeypatch.setattr(
        memory.MemoryService,
        "create_relation",
        AsyncMock(side_effect=RuntimeError("create relation failed")),
    )
    res_exc = await memory.MemoryService.handle_create_relation(
        USER_ID, "Python", "Target", "related_to"
    )
    assert res_exc == {"success": False, "error": "memory_tool_execution_failed"}


@pytest.mark.asyncio
async def test_handle_update_entity_branches(monkeypatch):
    audit_log = AsyncMock()
    entity = SimpleNamespace(
        id=ENTITY_ID,
        name="Python",
        description="initial",
        properties={},
        entity_type=EntityType.SKILL,
    )

    monkeypatch.setattr(
        memory.User, "get", AsyncMock(return_value=SimpleNamespace(id=USER_ID))
    )
    monkeypatch.setattr(memory.AuditLogService, "log", audit_log)

    # 1. Entity found -> update success
    monkeypatch.setattr(
        memory.MemoryEntity,
        "filter",
        lambda **kwargs: (
            Query(first_result=entity)
            if kwargs == {"user_id": USER_ID, "name": "Python"}
            else Query()
        ),
    )
    monkeypatch.setattr(
        memory.MemoryService, "update_entity", AsyncMock(return_value=entity)
    )

    res = await memory.MemoryService.handle_update_entity(
        USER_ID, "Python", description="updated", properties={"k": "v"}
    )
    assert res["success"] is True
    assert res["entity_id"] == str(ENTITY_ID)

    # 2. Entity not found
    monkeypatch.setattr(memory.MemoryEntity, "filter", lambda **_kwargs: Query())
    res_missing = await memory.MemoryService.handle_update_entity(
        USER_ID, "Nonexistent", description="desc"
    )
    assert "memory_entity_named_not_found" in res_missing["error"]

    # 3. update_entity raises exception
    monkeypatch.setattr(
        memory.MemoryEntity,
        "filter",
        lambda **_kwargs: Query(first_result=entity),
    )
    monkeypatch.setattr(
        memory.MemoryService,
        "update_entity",
        AsyncMock(side_effect=RuntimeError("db failed")),
    )
    res_err = await memory.MemoryService.handle_update_entity(
        USER_ID, "Python", description="updated"
    )
    assert res_err == {"success": False, "error": "memory_tool_execution_failed"}


@pytest.mark.asyncio
async def test_handle_search_memory_invalid_days_and_exceptions(monkeypatch):
    # 1. Invalid time_window_days string ('abc') -> parsed_days is None
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(memory.MemoryService, "search_entities", search)
    res = await memory.MemoryService.handle_search_memory(
        USER_ID, "query", time_window_days="abc"
    )
    assert res["success"] is True
    search.assert_awaited_once_with(
        user_id=USER_ID,
        query="query",
        top_k=5,
        entity_type=None,
        time_window_days=None,
    )

    # 2. search_entities raises exception -> returns error dict
    monkeypatch.setattr(
        memory.MemoryService,
        "search_entities",
        AsyncMock(side_effect=RuntimeError("search failed")),
    )
    res_err = await memory.MemoryService.handle_search_memory(USER_ID, "query")
    assert res_err == {"success": False, "error": "memory_tool_execution_failed"}


@pytest.mark.asyncio
async def test_handle_get_memory_subgraph_invalid_references(monkeypatch):
    # 1. non-string / non-UUID in entity_ids
    res_invalid_type = await memory.MemoryService.handle_get_memory_subgraph(
        USER_ID,
        [12345],  # type: ignore
    )
    assert res_invalid_type["success"] is False
    assert res_invalid_type["error"] == "memory_subgraph_invalid_request"

    # 2. empty whitespace string in entity_ids
    res_empty_str = await memory.MemoryService.handle_get_memory_subgraph(
        USER_ID, ["   "]
    )
    assert res_empty_str["success"] is False
    assert res_empty_str["error"] == "memory_subgraph_invalid_request"

    # 3. get_entity_subgraph raises general exception
    monkeypatch.setattr(memory.MemoryEntity, "filter", MagicMock(return_value=Query()))
    monkeypatch.setattr(
        memory.MemoryService,
        "get_entity_subgraph",
        AsyncMock(side_effect=RuntimeError("subgraph failed")),
    )
    res_err = await memory.MemoryService.handle_get_memory_subgraph(
        USER_ID, ["some_name"]
    )
    assert res_err == {"success": False, "error": "memory_tool_execution_failed"}
