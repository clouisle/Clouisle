from types import SimpleNamespace
from unittest.mock import AsyncMock
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
    assert audit_log.await_args.kwargs["status"] == "success"
