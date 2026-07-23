import sys
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.agent import AgentStatus, AgentVisibility
from app.schemas.clouisle_package import (
    ClouisleConflictAction,
    ClouisleImportInstallRequest,
    ClouislePackageDependency,
)
from app.schemas.response import BusinessError
from app.services import clouisle_package_resources as resources
from app.services.clouisle_package_resources import (
    AgentPackageAdapter,
    KnowledgeBasePackageAdapter,
    ToolPackageAdapter,
    WorkflowPackageAdapter,
    _lookup_dependency_summary,
    _restore_kb_document_file,
)


class Query:
    def __init__(self, *, first=None, items=(), exists=False):
        self.value = first
        self.items = list(items)
        self.exists_value = exists

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.value

    async def all(self):
        return self.items

    async def exists(self):
        return self.exists_value

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


@asynccontextmanager
async def transaction():
    yield


def endpoint(monkeypatch, name, function, value):
    module_name = f"app.api.v1.endpoints.{name}"
    module = ModuleType(module_name)
    setattr(module, function, value)
    monkeypatch.setitem(sys.modules, module_name, module)


def agent(**overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "assistant",
        "description": "Helpful",
        "icon": None,
        "avatar_url": None,
        "model_id": None,
        "system_prompt": "Help",
        "max_iterations": 5,
        "hide_tool_calls": False,
        "tools_config": [],
        "enable_vision": False,
        "enable_file_upload": False,
        "file_upload_config": {},
        "enable_user_input_request": False,
        "enable_memory": False,
        "memory_config": {},
        "context_compression_config": {},
        "enable_image_generation": False,
        "image_generation_config": {},
        "enable_video_generation": False,
        "video_generation_config": {},
        "rag_mode": "agentic",
        "variables": [],
        "opening_message": None,
        "suggested_questions": [],
        "embed_config": {},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def workflow(**overrides):
    values = {
        "id": uuid4(),
        "team_id": uuid4(),
        "name": "flow",
        "description": "Flow",
        "icon": None,
        "definition": {},
        "variables": [],
        "trigger_type": "manual",
        "trigger_config": {"authorization": "secret", "safe": True},
        "visibility": "private",
        "embed_config": {},
        "version": 2,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def knowledge_base(**overrides):
    values = {
        "id": uuid4(),
        "created_by_id": uuid4(),
        "name": "docs",
        "description": "Docs",
        "icon": None,
        "settings": {},
        "embedding_model_id": None,
        "rerank_model_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_agent_export_adapts_model_tool_and_kb_dependencies(monkeypatch):
    team_model_id, tool_id, kb_id = uuid4(), uuid4(), uuid4()
    existing = agent(model_id=team_model_id, tools_config=[{"tool_id": str(tool_id)}])
    endpoint(
        monkeypatch, "agents", "check_agent_access", AsyncMock(return_value=existing)
    )
    model = SimpleNamespace(
        name="Claude", provider="provider", model_id="model", model_type="llm"
    )
    monkeypatch.setattr(
        resources.TeamModel,
        "filter",
        lambda **_kwargs: Query(first=SimpleNamespace(id=team_model_id, model=model)),
    )
    monkeypatch.setattr(
        resources.Tool,
        "filter",
        lambda **_kwargs: Query(
            first=SimpleNamespace(name="weather", display_name="Weather")
        ),
    )
    link = SimpleNamespace(
        knowledge_base_id=kb_id,
        knowledge_base=SimpleNamespace(name="Knowledge"),
        retrieval_top_k=3,
        score_threshold=0.2,
        search_mode="hybrid",
    )
    monkeypatch.setattr(
        resources.AgentKnowledgeBase,
        "filter",
        lambda **_kwargs: Query(items=[link]),
    )

    payload, dependencies, name = await AgentPackageAdapter().export(
        existing.id, SimpleNamespace(is_superuser=True)
    )

    assert name == "assistant"
    assert payload["model"]["team_model_id"] == str(team_model_id)
    assert {dependency["type"] for dependency in dependencies} == {
        "model",
        "tool",
        "knowledge_base",
    }
    assert payload["knowledge_base_configs"][0]["score_threshold"] == 0.2


@pytest.mark.asyncio
async def test_workflow_export_discovers_nested_dependencies_and_sanitizes(monkeypatch):
    tool_id = uuid4()
    existing = workflow(
        definition={"nodes": [{"data": {"nested": {"toolId": str(tool_id)}}}]}
    )
    endpoint(
        monkeypatch,
        "workflows",
        "check_workflow_access",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(
        resources.Tool,
        "filter",
        lambda **_kwargs: Query(
            first=SimpleNamespace(name="weather", display_name="Weather")
        ),
    )

    payload, dependencies, name = await WorkflowPackageAdapter().export(
        existing.id, SimpleNamespace(is_superuser=True)
    )

    assert name == "flow"
    assert payload["trigger_config"] == {"safe": True}
    assert dependencies == [
        {
            "type": "tool",
            "source_id": str(tool_id),
            "name": "Weather",
            "required": True,
            "hints": {"name": "weather"},
        }
    ]


@pytest.mark.asyncio
async def test_kb_export_without_scope_requires_owner(monkeypatch):
    owner_id = uuid4()
    existing = knowledge_base(created_by_id=owner_id)
    monkeypatch.setattr(
        resources.KnowledgeBase, "filter", lambda **_kwargs: Query(first=existing)
    )
    monkeypatch.setattr(resources.Document, "filter", lambda **_kwargs: Query())

    payload, dependencies, name = await KnowledgeBasePackageAdapter().export(
        existing.id,
        SimpleNamespace(id=owner_id, is_superuser=True),
        check_scope=False,
    )

    assert (name, dependencies, payload["documents"]) == ("docs", [], [])

    with pytest.raises(BusinessError) as exc_info:
        await KnowledgeBasePackageAdapter().export(
            existing.id,
            SimpleNamespace(id=uuid4(), is_superuser=True),
            check_scope=False,
        )
    assert exc_info.value.msg_key == "operation_not_permitted"


@pytest.mark.asyncio
async def test_dependency_resolution_matches_model_and_reports_missing(monkeypatch):
    matching = SimpleNamespace(
        id=uuid4(),
        model=SimpleNamespace(provider="p", model_id="m", model_type="llm"),
    )
    monkeypatch.setattr(
        resources.TeamModel, "filter", lambda **_kwargs: Query(items=[matching])
    )
    monkeypatch.setattr(resources.Tool, "filter", lambda **_kwargs: Query())

    resolved = await resources._resolve_model_dependency(
        ClouislePackageDependency(type="model", hints={"provider": "p"}), uuid4()
    )
    missing = await resources._resolve_resource_dependency(
        ClouislePackageDependency(type="tool", name="absent"), uuid4()
    )

    assert resolved.matched_id == matching.id
    assert resolved.status.value == "resolved"
    assert missing.status.value == "missing"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dep_type", "model", "expected"),
    [
        ("agent", resources.Agent, "Agent"),
        ("workflow", resources.Workflow, "Workflow"),
        ("knowledge_base", resources.KnowledgeBase, "KB"),
    ],
)
async def test_dependency_summary_adapts_resource_names(
    monkeypatch, dep_type, model, expected
):
    monkeypatch.setattr(
        model, "filter", lambda **_kwargs: Query(first=SimpleNamespace(name=expected))
    )

    summary = await _lookup_dependency_summary(dep_type, uuid4(), uuid4())

    assert summary == {"name": expected, "hints": {}}


@pytest.mark.asyncio
async def test_agent_install_creates_private_draft_and_replaces_kbs(monkeypatch):
    created = agent()
    create = AsyncMock(return_value=created)
    replace = AsyncMock()
    monkeypatch.setattr(resources, "in_transaction", transaction)
    monkeypatch.setattr(resources.Agent, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(resources.Agent, "create", create)
    monkeypatch.setattr(resources, "_replace_agent_kbs", replace)

    result = await AgentPackageAdapter().install(
        manifest=None,
        resource_payload={"name": "assistant"},
        team=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(is_superuser=True),
        install_in=ClouisleImportInstallRequest(),
    )

    assert result.installed == created.id
    assert create.await_args.kwargs["status"] == AgentStatus.DRAFT
    assert create.await_args.kwargs["visibility"] == AgentVisibility.PRIVATE
    replace.assert_awaited_once()


@pytest.mark.asyncio
async def test_workflow_install_updates_version_and_checks_permission(monkeypatch):
    existing = workflow()
    existing.save = AsyncMock()
    monkeypatch.setattr(resources, "in_transaction", transaction)
    monkeypatch.setattr(
        resources.Workflow, "filter", lambda **_kwargs: Query(first=existing)
    )
    request = ClouisleImportInstallRequest(action=ClouisleConflictAction.UPDATE)

    result = await WorkflowPackageAdapter().install(
        manifest=None,
        resource_payload={"name": existing.name, "trigger_type": "webhook"},
        team=SimpleNamespace(id=existing.team_id),
        user=SimpleNamespace(is_superuser=True),
        install_in=request,
    )

    assert result.updated == existing.id
    assert existing.version == 3
    assert existing.trigger_type.value == "manual"

    with pytest.raises(BusinessError) as exc_info:
        await WorkflowPackageAdapter().install(
            manifest=None,
            resource_payload={"name": existing.name},
            team=SimpleNamespace(id=existing.team_id),
            user=SimpleNamespace(is_superuser=False, roles=[]),
            install_in=request,
        )
    assert exc_info.value.msg_key == "operation_not_permitted"


@pytest.mark.asyncio
async def test_kb_install_creates_documents_chunks_and_ignores_traversal(
    tmp_path, monkeypatch
):
    created = knowledge_base()
    document = SimpleNamespace(id=uuid4())
    kb_create = AsyncMock(return_value=created)
    doc_create = AsyncMock(return_value=document)
    chunk_create = AsyncMock()
    monkeypatch.setattr(resources, "in_transaction", transaction)
    monkeypatch.setattr(resources.KnowledgeBase, "filter", lambda **_kwargs: Query())
    monkeypatch.setattr(resources.KnowledgeBase, "create", kb_create)
    monkeypatch.setattr(resources.Document, "create", doc_create)
    monkeypatch.setattr(resources.DocumentChunk, "create", chunk_create)

    result = await KnowledgeBasePackageAdapter().install(
        manifest=None,
        resource_payload={
            "name": "docs",
            "documents": [
                {
                    "name": "doc.txt",
                    "package_file": "../outside.txt",
                    "source_url": "https://example.test/doc.txt",
                    "chunks": [{"content": "hello", "chunk_index": 0}],
                }
            ],
        },
        team=SimpleNamespace(id=uuid4()),
        user=SimpleNamespace(is_superuser=True),
        install_in=ClouisleImportInstallRequest(),
        package_dir=tmp_path / "package",
    )

    assert result.installed == created.id
    assert doc_create.await_args.kwargs["file_path"] is None
    assert doc_create.await_args.kwargs["source_url"].startswith("https://")
    chunk_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_missing_and_provider_failures_propagate(monkeypatch, tmp_path):
    monkeypatch.setattr(resources, "in_transaction", transaction)
    monkeypatch.setattr(resources.Tool, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc_info:
        await ToolPackageAdapter().install(
            manifest=None,
            resource_payload={"name": "missing"},
            team=SimpleNamespace(id=uuid4()),
            user=SimpleNamespace(is_superuser=True),
            install_in=ClouisleImportInstallRequest(
                action=ClouisleConflictAction.UPDATE
            ),
        )
    assert exc_info.value.msg_key == "tool_not_found"

    package_dir = tmp_path / "package"
    asset = package_dir / "assets" / "icon.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"data")
    monkeypatch.setattr(
        resources,
        "save_generated_upload",
        AsyncMock(side_effect=RuntimeError("provider unavailable")),
    )
    with pytest.raises(RuntimeError, match="provider unavailable"):
        await resources._restore_payload_assets(
            {"assets": {"icon": "assets/icon.png"}}, package_dir
        )


@pytest.mark.asyncio
async def test_transaction_failure_prevents_success_result(monkeypatch):
    @asynccontextmanager
    async def failing_transaction():
        raise RuntimeError("rollback")
        yield

    monkeypatch.setattr(resources, "in_transaction", failing_transaction)

    with pytest.raises(RuntimeError, match="rollback"):
        await ToolPackageAdapter().install(
            manifest=None,
            resource_payload={"name": "tool"},
            team=SimpleNamespace(id=uuid4()),
            user=SimpleNamespace(is_superuser=True),
            install_in=ClouisleImportInstallRequest(),
        )


def test_document_restore_rejects_missing_and_outside_sources(tmp_path):
    package_dir = tmp_path / "package"
    package_dir.mkdir()

    assert _restore_kb_document_file(package_dir, uuid4(), "missing.txt", "x") is None
    assert (
        _restore_kb_document_file(package_dir, uuid4(), "../outside.txt", "x") is None
    )


def test_adapter_registry_and_explicit_target_name():
    assert (
        resources.get_adapter(resources.ClouisleResourceType.AGENT).resource_type.value
        == "agent"
    )
    assert (
        ToolPackageAdapter().ensure_import_permission(
            SimpleNamespace(is_superuser=True)
        )
        is None
    )
