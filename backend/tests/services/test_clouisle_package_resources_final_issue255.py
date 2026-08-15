import sys
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.schemas.clouisle_package import (
    ClouisleConflictAction,
    ClouisleImportInstallRequest,
)
from app.schemas.response import BusinessError
from app.services import clouisle_package_resources as resources


class Query:
    def __init__(self, *, first=None, exists=False, items=()):
        self.first_value = first
        self.exists_value = exists
        self.items = list(items)

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.first_value

    async def exists(self):
        return self.exists_value

    async def all(self):
        return self.items

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


@asynccontextmanager
async def transaction():
    yield


def install_request(action):
    return ClouisleImportInstallRequest(action=action, dependency_mapping={})


def endpoint(monkeypatch, name, check_name, result):
    module = ModuleType(name)
    check = AsyncMock(return_value=result)
    setattr(module, check_name, check)
    monkeypatch.setitem(sys.modules, name, module)
    return check


@pytest.mark.asyncio
async def test_base_asset_and_tool_export_skip_paths(monkeypatch):
    adapter = resources.ToolPackageAdapter()
    payload = {"assets": "invalid"}
    assert await resources.ResourcePackageAdapter.export_files(adapter, payload) == {}
    assert (
        await resources._restore_payload_assets(payload, SimpleNamespace()) is payload
    )

    tool = SimpleNamespace(
        name="Tool",
        display_name="Tool",
        description=None,
        icon=None,
        category="other",
        type="custom",
        custom_type=None,
        parameters=[],
        http_config={},
        code_config={},
        mcp_config={},
        is_enabled=True,
        team_id=uuid4(),
    )
    monkeypatch.setattr(resources.Tool, "filter", lambda **_kwargs: Query(first=tool))
    check = endpoint(
        monkeypatch,
        "app.api.v1.endpoints.tools",
        "check_team_access",
        None,
    )

    exported, _, name = await adapter.export(
        uuid4(),
        SimpleNamespace(is_superuser=False),
        check_permission=False,
        check_scope=False,
    )

    assert name == "Tool"
    assert exported["type"] == "custom"
    check.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_export_without_model_tools_or_permission(monkeypatch):
    agent = SimpleNamespace(
        id=uuid4(),
        name="Agent",
        description=None,
        icon=None,
        avatar_url=None,
        model_id=None,
        system_prompt=None,
        max_iterations=5,
        hide_tool_calls=False,
        hide_message_actions=False,
        hide_reasoning=False,
        tools_config=[{"name": "ignored"}],
        enable_attachments=False,
        attachment_config={},
        enable_user_input_request=False,
        enable_memory=False,
        memory_config={},
        context_compression_config={},
        enable_image_generation=False,
        image_generation_config={},
        enable_video_generation=False,
        video_generation_config={},
        rag_mode="agentic",
        variables=[],
        opening_message=None,
        suggested_questions=[],
        powered_by_text=None,
        embed_config={},
    )
    endpoint(
        monkeypatch,
        "app.api.v1.endpoints.agents",
        "check_agent_access",
        agent,
    )
    monkeypatch.setattr(
        resources.AgentKnowledgeBase, "filter", lambda **_kwargs: Query(items=[])
    )

    payload, dependencies, name = await resources.AgentPackageAdapter().export(
        agent.id, SimpleNamespace(is_superuser=False), check_permission=False
    )

    assert name == "Agent"
    assert payload["model"] is None
    assert dependencies == []

    agent.model_id = uuid4()
    monkeypatch.setattr(resources.TeamModel, "filter", lambda **_kwargs: Query())
    payload, dependencies, _ = await resources.AgentPackageAdapter().export(
        agent.id, SimpleNamespace(is_superuser=False), check_permission=False
    )
    assert payload["model"] is None
    assert dependencies == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter", "model", "missing_key"),
    [
        (resources.ToolPackageAdapter(), resources.Tool, "tool_not_found"),
        (resources.AgentPackageAdapter(), resources.Agent, "agent_not_found"),
        (resources.WorkflowPackageAdapter(), resources.Workflow, "workflow_not_found"),
        (
            resources.KnowledgeBasePackageAdapter(),
            resources.KnowledgeBase,
            "kb_not_found",
        ),
    ],
)
async def test_updates_skip_permission_and_report_missing(
    monkeypatch, adapter, model, missing_key
):
    monkeypatch.setattr(resources, "in_transaction", transaction)
    monkeypatch.setattr(model, "filter", lambda **_kwargs: Query())
    if model is resources.KnowledgeBase:
        monkeypatch.setattr(resources, "_kb_fields", AsyncMock(return_value={}))

    with pytest.raises(BusinessError) as exc_info:
        await adapter.install(
            manifest=None,
            resource_payload={"name": "missing"},
            team=SimpleNamespace(id=uuid4()),
            user=SimpleNamespace(is_superuser=False),
            install_in=install_request(ClouisleConflictAction.UPDATE),
            check_update_permission=False,
        )

    assert exc_info.value.msg_key == missing_key


@pytest.mark.asyncio
async def test_agent_duplicate_and_workflow_export_permission_skip(monkeypatch):
    monkeypatch.setattr(resources, "in_transaction", transaction)
    monkeypatch.setattr(resources.Agent, "filter", lambda **_kwargs: Query(exists=True))
    with pytest.raises(BusinessError) as exc_info:
        await resources.AgentPackageAdapter().install(
            manifest=None,
            resource_payload={"name": "Agent"},
            team=SimpleNamespace(id=uuid4()),
            user=SimpleNamespace(is_superuser=True),
            install_in=install_request(ClouisleConflictAction.INSTALL),
        )
    assert exc_info.value.msg_key == "clouisle_name_conflict"

    workflow = SimpleNamespace(
        name="Flow",
        description=None,
        icon=None,
        definition={},
        variables=[],
        trigger_type="manual",
        trigger_config={},
        visibility="private",
        embed_config={},
        run_page_config={},
        team_id=uuid4(),
    )
    endpoint(
        monkeypatch,
        "app.api.v1.endpoints.workflows",
        "check_workflow_access",
        workflow,
    )
    monkeypatch.setattr(resources, "_workflow_dependencies", AsyncMock(return_value=[]))

    payload, dependencies, name = await resources.WorkflowPackageAdapter().export(
        uuid4(), SimpleNamespace(is_superuser=False), check_permission=False
    )
    assert (name, dependencies, payload["definition"]) == ("Flow", [], {})


@pytest.mark.asyncio
async def test_kb_export_missing_models_files_and_permission_skip(
    tmp_path, monkeypatch
):
    embedding_id, rerank_id = uuid4(), uuid4()
    kb = SimpleNamespace(
        id=uuid4(),
        name="Docs",
        description=None,
        icon=None,
        settings={},
        embedding_model_id=embedding_id,
        rerank_model_id=rerank_id,
    )
    endpoint(
        monkeypatch,
        "app.api.v1.endpoints.knowledge_bases",
        "check_kb_access",
        kb,
    )
    monkeypatch.setattr(resources.Model, "filter", lambda **_kwargs: Query())
    missing = tmp_path / "missing.txt"
    documents = [
        {"package_file": None, "source_file": str(missing)},
        {"package_file": "documents/missing.txt", "source_file": None},
        {"package_file": "documents/missing.txt", "source_file": str(missing)},
    ]
    monkeypatch.setattr(resources.Document, "filter", lambda **_kwargs: Query(items=[]))

    payload, dependencies, _ = await resources.KnowledgeBasePackageAdapter().export(
        kb.id, SimpleNamespace(is_superuser=False), check_permission=False
    )
    files = await resources.KnowledgeBasePackageAdapter().export_files(
        {"documents": documents}
    )

    assert payload["embedding_model"] is None
    assert payload["rerank_model"] is None
    assert dependencies == []
    assert files == {}
    assert ["source_file" in document for document in documents] == [True, True, False]
