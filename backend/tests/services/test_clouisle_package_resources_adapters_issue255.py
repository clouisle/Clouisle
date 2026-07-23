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
    def __init__(self, *, first=None, items=(), exists=False):
        self.first_value = first
        self.items = list(items)
        self.exists_value = exists

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.first_value

    async def all(self):
        return self.items

    async def exists(self):
        return self.exists_value

    async def delete(self):
        return None

    def __await__(self):
        async def resolve():
            return self.items

        return resolve().__await__()


@asynccontextmanager
async def transaction():
    yield


def install_request(action=ClouisleConflictAction.INSTALL, mapping=None):
    return ClouisleImportInstallRequest(action=action, dependency_mapping=mapping or {})


@pytest.mark.asyncio
async def test_kb_export_includes_models_documents_chunks_and_files(
    tmp_path, monkeypatch
):
    kb_id, embedding_id, rerank_id, document_id = uuid4(), uuid4(), uuid4(), uuid4()
    kb = SimpleNamespace(
        id=kb_id,
        name="Docs",
        description="Knowledge",
        icon=None,
        settings={"safe": True},
        embedding_model_id=embedding_id,
        rerank_model_id=rerank_id,
    )
    endpoint = ModuleType("app.api.v1.endpoints.knowledge_bases")
    endpoint.check_kb_access = AsyncMock(return_value=kb)
    monkeypatch.setitem(sys.modules, endpoint.__name__, endpoint)
    models = {
        embedding_id: SimpleNamespace(
            id=embedding_id,
            name="Embed",
            provider="local",
            model_id="embed-v1",
            model_type="embedding",
        ),
        rerank_id: SimpleNamespace(
            id=rerank_id,
            name="Rerank",
            provider="local",
            model_id="rerank-v1",
            model_type="rerank",
        ),
    }
    monkeypatch.setattr(
        resources.Model,
        "filter",
        lambda **kwargs: Query(first=models.get(kwargs.get("id"))),
    )
    source = tmp_path / "source.txt"
    source.write_bytes(b"contents")
    document = SimpleNamespace(
        id=document_id,
        name="source.txt",
        doc_type="txt",
        file_path=str(source),
        source_url=None,
        file_size=8,
        metadata={"page": 1},
    )
    chunk = SimpleNamespace(
        content="contents", chunk_index=0, token_count=1, metadata={}
    )
    monkeypatch.setattr(
        resources.Document,
        "filter",
        lambda **_kwargs: Query(items=[document]),
    )
    monkeypatch.setattr(
        resources.DocumentChunk,
        "filter",
        lambda **_kwargs: Query(items=[chunk]),
    )

    adapter = resources.KnowledgeBasePackageAdapter()
    payload, dependencies, name = await adapter.export(
        kb_id, SimpleNamespace(is_superuser=True)
    )
    files = await adapter.export_files(payload)

    assert name == "Docs"
    assert [dependency["required"] for dependency in dependencies] == [True, False]
    assert payload["embedding_model"]["name"] == "Embed"
    assert payload["documents"][0]["chunks"][0]["content"] == "contents"
    package_file = payload["documents"][0]["package_file"]
    assert files == {package_file: b"contents"}
    assert "source_file" not in payload["documents"][0]


@pytest.mark.asyncio
async def test_kb_export_without_scope_reports_missing(monkeypatch):
    monkeypatch.setattr(resources.KnowledgeBase, "filter", lambda **_kwargs: Query())

    with pytest.raises(BusinessError) as exc_info:
        await resources.KnowledgeBasePackageAdapter().export(
            uuid4(), SimpleNamespace(id=uuid4(), is_superuser=True), check_scope=False
        )

    assert exc_info.value.msg_key == "kb_not_found"


@pytest.mark.asyncio
async def test_agent_update_rewrites_dependencies_and_kbs(monkeypatch):
    agent_id, team_id, mapped_model, mapped_kb = uuid4(), uuid4(), uuid4(), uuid4()
    existing = SimpleNamespace(id=agent_id, name="Agent", save=AsyncMock())
    monkeypatch.setattr(resources, "in_transaction", transaction)
    monkeypatch.setattr(
        resources.Agent, "filter", lambda **_kwargs: Query(first=existing)
    )
    delete = AsyncMock()
    create_link = AsyncMock()

    class LinkQuery(Query):
        async def delete(self):
            await delete()

    monkeypatch.setattr(
        resources.AgentKnowledgeBase, "filter", lambda **_kwargs: LinkQuery()
    )
    monkeypatch.setattr(resources.AgentKnowledgeBase, "create", create_link)
    request = install_request(
        ClouisleConflictAction.UPDATE,
        {"source-model": mapped_model, "source-kb": mapped_kb},
    )

    result = await resources.AgentPackageAdapter().install(
        manifest=None,
        resource_payload={
            "name": "Agent",
            "model": {"team_model_id": "source-model"},
            "knowledge_base_configs": [
                {
                    "knowledge_base_id": "missing",
                    "score_threshold": 0,
                },
                {
                    "knowledge_base_id": "source-kb",
                    "retrieval_top_k": 2,
                    "score_threshold": None,
                    "search_mode": "vector",
                },
            ],
        },
        team=SimpleNamespace(id=team_id),
        user=SimpleNamespace(is_superuser=True),
        install_in=request,
    )

    assert result.updated == agent_id
    assert existing.model_id == mapped_model
    existing.save.assert_awaited_once_with()
    delete.assert_awaited_once_with()
    assert create_link.await_args.kwargs["knowledge_base_id"] == mapped_kb
    assert create_link.await_args.kwargs["score_threshold"] == 0.3


@pytest.mark.asyncio
async def test_agent_update_missing_reports_not_found(monkeypatch):
    monkeypatch.setattr(resources, "in_transaction", transaction)
    monkeypatch.setattr(resources.Agent, "filter", lambda **_kwargs: Query())

    with pytest.raises(BusinessError) as exc_info:
        await resources.AgentPackageAdapter().install(
            manifest=None,
            resource_payload={"name": "missing"},
            team=SimpleNamespace(id=uuid4()),
            user=SimpleNamespace(is_superuser=True),
            install_in=install_request(ClouisleConflictAction.UPDATE),
        )

    assert exc_info.value.msg_key == "agent_not_found"


@pytest.mark.asyncio
async def test_workflow_create_and_duplicate_branches(monkeypatch):
    created = SimpleNamespace(id=uuid4())
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(resources, "in_transaction", transaction)
    monkeypatch.setattr(resources.Workflow, "create", create)
    monkeypatch.setattr(
        resources.Workflow, "filter", lambda **_kwargs: Query(exists=False)
    )
    team, user = SimpleNamespace(id=uuid4()), SimpleNamespace(is_superuser=True)

    result = await resources.WorkflowPackageAdapter().install(
        manifest=None,
        resource_payload={"name": "Flow", "definition": {}},
        team=team,
        user=user,
        install_in=install_request(),
    )

    assert result.installed == created.id
    assert create.await_args.kwargs["webhook_token"] is None

    monkeypatch.setattr(
        resources.Workflow, "filter", lambda **_kwargs: Query(exists=True)
    )
    with pytest.raises(BusinessError) as exc_info:
        await resources.WorkflowPackageAdapter().install(
            manifest=None,
            resource_payload={"name": "Flow"},
            team=team,
            user=user,
            install_in=install_request(),
        )
    assert exc_info.value.msg_key == "clouisle_name_conflict"


@pytest.mark.asyncio
async def test_kb_update_and_create_duplicate_branches(monkeypatch):
    existing = SimpleNamespace(id=uuid4(), name="Docs", save=AsyncMock())
    monkeypatch.setattr(resources, "in_transaction", transaction)
    monkeypatch.setattr(
        resources, "_kb_fields", AsyncMock(return_value={"icon": "new"})
    )
    monkeypatch.setattr(
        resources.KnowledgeBase, "filter", lambda **_kwargs: Query(first=existing)
    )
    team, user = SimpleNamespace(id=uuid4()), SimpleNamespace(is_superuser=True)

    result = await resources.KnowledgeBasePackageAdapter().install(
        manifest=None,
        resource_payload={"name": "Docs"},
        team=team,
        user=user,
        install_in=install_request(ClouisleConflictAction.UPDATE),
    )

    assert result.updated == existing.id
    assert result.warnings == ["clouisle_kb_documents_not_updated"]
    assert existing.icon == "new"

    monkeypatch.setattr(
        resources.KnowledgeBase, "filter", lambda **_kwargs: Query(exists=True)
    )
    with pytest.raises(BusinessError) as exc_info:
        await resources.KnowledgeBasePackageAdapter().install(
            manifest=None,
            resource_payload={"name": "Docs"},
            team=team,
            user=user,
            install_in=install_request(),
        )
    assert exc_info.value.msg_key == "clouisle_name_conflict"
