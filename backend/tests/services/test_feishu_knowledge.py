from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest

from app.integrations import feishu
from app.integrations.credentials import encrypt_secret
from app.schemas.response import BusinessError
from app.services import feishu_knowledge as service
from app.api.v1.admin.endpoints import feishu_knowledge as api


class Query:
    def __init__(self, value):
        self.value = value

    def __await__(self):
        async def result():
            return self.value

        return result().__await__()

    def prefetch_related(self, *_args):
        return self

    def first(self):
        return self

    async def update(self, **_kwargs):
        return 1


@pytest.fixture
def transport_client(monkeypatch):
    original = httpx.AsyncClient

    def install(handler):
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            feishu.httpx,
            "AsyncClient",
            lambda **kwargs: original(transport=transport, **kwargs),
        )
        monkeypatch.setattr(feishu.asyncio, "sleep", AsyncMock())
        return feishu.FeishuClient("app-id", encrypt_secret("never-display-secret"))

    return install


@pytest.mark.asyncio
async def test_wiki_scan_follows_empty_pages_and_recurses(transport_client):
    requests = []

    def handler(request):
        requests.append(request)
        path = request.url.path
        if path.endswith("/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "tenant"}
            )
        assert request.headers["authorization"] == "Bearer tenant"
        if not request.url.params.get(
            "parent_node_token"
        ) and not request.url.params.get("page_token"):
            data = {"items": [], "has_more": True, "page_token": "next"}
        elif request.url.params.get("page_token"):
            data = {
                "items": [
                    {
                        "node_token": "root",
                        "obj_token": "doc-a",
                        "obj_type": "docx",
                        "has_child": True,
                    }
                ],
                "has_more": False,
            }
        else:
            data = {
                "items": [
                    {
                        "node_token": "child",
                        "obj_token": "doc-b",
                        "obj_type": "docx",
                        "has_child": False,
                    }
                ],
                "has_more": False,
            }
        return httpx.Response(200, json={"code": 0, "data": data})

    nodes = await transport_client(handler).list_wiki_nodes("space")
    assert [node["node_token"] for node in nodes] == ["root", "child"]
    assert requests[-1].url.params["parent_node_token"] == "root"


@pytest.mark.asyncio
async def test_wiki_repeated_page_token_aborts(transport_client):
    def handler(request):
        if request.url.path.endswith("/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "tenant"}
            )
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {"items": [], "has_more": True, "page_token": "same"},
            },
        )

    with pytest.raises(feishu.FeishuAPIError, match="did not advance"):
        await transport_client(handler).list_wiki_nodes("space")


@pytest.mark.asyncio
async def test_docx_requests_and_permission_error_classification(transport_client):
    def handler(request):
        if request.url.path.endswith("/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "tenant"}
            )
        assert request.url.path == "/open-apis/docx/v1/documents/doc/blocks"
        assert request.url.params["document_revision_id"] == "-1"
        assert request.url.params["page_size"] == "500"
        return httpx.Response(
            400, json={"code": 1770032, "msg": "secret provider details"}
        )

    with pytest.raises(feishu.FeishuAPIError) as raised:
        await transport_client(handler).get_docx_blocks("doc")
    assert raised.value.permission_denied
    assert raised.value.code == 1770032
    assert "secret provider details" not in service.public_error(raised.value)
    assert not feishu.FeishuAPIError(
        "ambiguous not found", code=131005
    ).permission_denied


def text_block(block_id, kind, text, **extra):
    key = {
        1: "page",
        2: "text",
        12: "bullet",
        13: "ordered",
        14: "code",
        15: "quote",
        17: "todo",
    }.get(kind, f"heading{kind - 2}")
    return {
        "block_id": block_id,
        "block_type": kind,
        key: {"elements": [{"text_run": {"content": text}}]},
        **extra,
    }


def test_docx_blocks_preserve_rich_text_tables_and_report_unknown_blocks():
    blocks = [
        text_block(
            "page",
            1,
            "",
            children=["heading", "bullet", "code", "quote", "table", "unknown"],
        ),
        text_block("heading", 3, "Heading"),
        text_block("bullet", 12, "List", children=["nested"]),
        text_block("nested", 13, "Nested"),
        text_block("code", 14, "print(1)"),
        text_block("quote", 15, "Quote"),
        {
            "block_id": "table",
            "block_type": 31,
            "children": ["c1", "c2"],
            "table": {"property": {"column_size": 2}, "cells": ["c1", "c2"]},
        },
        {"block_id": "c1", "block_type": 32, "children": ["a"]},
        {"block_id": "c2", "block_type": 32, "children": ["b"]},
        text_block("a", 2, "A"),
        text_block("b", 2, "B"),
        {"block_id": "unknown", "block_type": 999},
    ]
    markdown, warnings = service.blocks_to_markdown(blocks, "Title")
    assert "# Heading" in markdown
    assert "- List\n\n  1. Nested" in markdown
    assert "```\nprint(1)\n```" in markdown
    assert "> Quote" in markdown
    assert "| A | B |" in markdown
    assert warnings == ["unsupported_block:999"]
    link = service._inline(
        [
            {
                "text_run": {
                    "content": "link",
                    "text_element_style": {
                        "bold": True,
                        "link": {"url": "https://example.com"},
                    },
                }
            }
        ]
    )
    assert link == "[**link**](https://example.com)"


def test_incomplete_and_cyclic_docx_is_not_imported_as_empty():
    for blocks in (
        [],
        [{"block_id": "a", "block_type": 1, "children": ["missing"]}],
        [{"block_id": "a", "block_type": 1, "children": ["a"]}],
    ):
        with pytest.raises(service.ImportProcessingError):
            service.blocks_to_markdown(blocks, "Title")


@pytest.fixture
def source():
    return SimpleNamespace(
        id=uuid4(),
        knowledge_base_id=uuid4(),
        space_id="space",
        name="Docs",
        interval_minutes=60,
        is_enabled=True,
        status="idle",
        dispatch_token=None,
        lease_expires_at=None,
        save=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_incomplete_inventory_never_removes_imports(monkeypatch, source):
    monkeypatch.setattr(
        service.KnowledgeBase,
        "filter",
        Mock(return_value=Query(SimpleNamespace(id=source.knowledge_base_id))),
    )
    imports = Mock()
    monkeypatch.setattr(service.FeishuKnowledgeDocument, "filter", imports)
    remove = AsyncMock()
    monkeypatch.setattr(service, "remove_import", remove)
    client = SimpleNamespace(
        list_wiki_nodes=AsyncMock(
            side_effect=feishu.FeishuAPIError("later page failed", code=99991400)
        )
    )
    with pytest.raises(feishu.FeishuAPIError):
        await service._scan_source(source, client)
    imports.assert_not_called()
    remove.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_confirmed_space_permission_revocation_removes_all(
    monkeypatch, source
):
    kb = SimpleNamespace(id=source.knowledge_base_id)
    mapping = SimpleNamespace(save=AsyncMock())
    monkeypatch.setattr(service.KnowledgeBase, "filter", Mock(return_value=Query(kb)))
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument, "filter", Mock(return_value=Query([mapping]))
    )
    remove = AsyncMock()
    monkeypatch.setattr(service, "remove_import", remove)
    error = feishu.FeishuAPIError("denied", code=131006)
    error.resource_scope = "wiki_node"
    client = SimpleNamespace(list_wiki_nodes=AsyncMock(side_effect=error))
    with pytest.raises(feishu.FeishuAPIError):
        await service._scan_source(source, client)
    remove.assert_not_awaited()
    error.resource_scope = "wiki_space"
    with pytest.raises(feishu.FeishuAPIError):
        await service._scan_source(source, client)
    remove.assert_awaited_once_with(mapping, kb)


@pytest.mark.asyncio
async def test_complete_inventory_removes_unseen_and_reports_unsupported(
    monkeypatch, source
):
    kb = SimpleNamespace(id=source.knowledge_base_id)
    old = SimpleNamespace(obj_type="docx", obj_token="gone", delete=AsyncMock())
    unsupported = SimpleNamespace(save=AsyncMock())
    monkeypatch.setattr(service.KnowledgeBase, "filter", Mock(return_value=Query(kb)))
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument, "filter", Mock(return_value=Query([old]))
    )
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument,
        "get_or_create",
        AsyncMock(return_value=(unsupported, True)),
    )
    remove = AsyncMock()
    monkeypatch.setattr(service, "remove_import", remove)
    client = SimpleNamespace(
        list_wiki_nodes=AsyncMock(
            return_value=[
                {
                    "node_token": "n",
                    "title": "架构思维笔记",
                    "obj_token": "mindnote",
                    "obj_type": "mindnote",
                }
            ]
        )
    )
    result = await service._scan_source(source, client)
    assert result["unsupported"] == 1 and result["removed"] == 1
    assert result["errors"] == []
    assert result["failed"] == 0
    assert result["skipped"][0]["type"] == "mindnote"
    assert result["skipped"][0]["node_title"] == "架构思维笔记"
    assert unsupported.last_error is None
    remove.assert_awaited_once_with(old, kb)
    old.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_doc_download_retains_previous_document(monkeypatch, source):
    kb = SimpleNamespace(id=source.knowledge_base_id)
    mapping = SimpleNamespace(obj_type="docx", obj_token="doc", save=AsyncMock())
    monkeypatch.setattr(service.KnowledgeBase, "filter", Mock(return_value=Query(kb)))
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument, "filter", Mock(return_value=Query([mapping]))
    )
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument,
        "get_or_create",
        AsyncMock(return_value=(mapping, False)),
    )
    remove = AsyncMock()
    monkeypatch.setattr(service, "remove_import", remove)
    client = SimpleNamespace(
        list_wiki_nodes=AsyncMock(
            return_value=[{"node_token": "n", "obj_token": "doc", "obj_type": "docx"}]
        ),
        get_docx_blocks=AsyncMock(side_effect=httpx.ReadTimeout("temporary")),
    )
    result = await service._scan_source(source, client)
    assert result["failed"] == 1 and result["indexed"] == 0
    remove.assert_not_awaited()


@asynccontextmanager
async def unlocked(_source_id):
    yield


@pytest.mark.asyncio
async def test_queue_publish_failure_releases_lease_and_disabled_source_rejects(
    monkeypatch, source
):
    from app.tasks import feishu_knowledge as tasks

    monkeypatch.setattr(service, "source_lock", unlocked)
    monkeypatch.setattr(service, "get_source", AsyncMock(return_value=source))
    query = Query(None)
    query.update = AsyncMock(return_value=1)
    monkeypatch.setattr(
        service.FeishuKnowledgeSource, "filter", Mock(return_value=query)
    )
    monkeypatch.setattr(
        tasks.sync_source_task,
        "apply_async",
        Mock(side_effect=RuntimeError("redis down")),
    )
    with pytest.raises(BusinessError) as raised:
        await service.queue_source(source.id)
    assert raised.value.msg_key == "feishu_knowledge_publish_failed"
    assert query.update.await_args.kwargs["lease_expires_at"] is None
    source.is_enabled = False
    with pytest.raises(BusinessError) as raised:
        await service.queue_source(source.id)
    assert raised.value.msg_key == "feishu_knowledge_disabled"


@pytest.mark.asyncio
async def test_fresh_queued_job_is_not_republished_and_stale_disabled_job_skips(
    monkeypatch, source
):
    from app.tasks import feishu_knowledge as tasks

    source.status = "queued"
    source.lease_expires_at = service.utcnow() + timedelta(minutes=1)
    source.dispatch_token = uuid4()
    monkeypatch.setattr(service, "source_lock", unlocked)
    monkeypatch.setattr(service, "get_source", AsyncMock(return_value=source))
    publish = Mock()
    monkeypatch.setattr(tasks.sync_source_task, "apply_async", publish)
    await service.queue_source(source.id)
    publish.assert_not_called()
    assert await service.sync_source(source.id, uuid4()) == {"status": "stale"}
    source.is_enabled = False
    assert await service.sync_source(source.id, source.dispatch_token) == {
        "status": "disabled"
    }
    assert source.dispatch_token is None


@pytest.mark.asyncio
async def test_expired_dispatch_lease_is_republished_with_new_token(
    monkeypatch, source
):
    from app.tasks import feishu_knowledge as tasks

    old_token = uuid4()
    source.status = "running"
    source.dispatch_token = old_token
    source.lease_expires_at = service.utcnow() - timedelta(minutes=1)
    monkeypatch.setattr(service, "source_lock", unlocked)
    monkeypatch.setattr(service, "get_source", AsyncMock(return_value=source))
    publish = Mock()
    monkeypatch.setattr(tasks.sync_source_task, "apply_async", publish)
    await service.queue_source(source.id)
    assert source.dispatch_token != old_token
    assert source.status == "queued"
    publish.assert_called_once_with(
        args=[str(source.id), str(source.dispatch_token)],
        task_id=str(source.dispatch_token),
    )


@pytest.mark.asyncio
async def test_failed_source_delete_stays_paused_and_does_not_recreate(
    monkeypatch, source
):
    monkeypatch.setattr(service, "source_lock", unlocked)
    monkeypatch.setattr(service, "get_source", AsyncMock(return_value=source))
    monkeypatch.setattr(
        service.KnowledgeBase,
        "get",
        AsyncMock(return_value=SimpleNamespace(id=source.knowledge_base_id)),
    )
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument, "filter", Mock(return_value=Query([object()]))
    )
    monkeypatch.setattr(
        service,
        "remove_import",
        AsyncMock(side_effect=RuntimeError("vector service unavailable")),
    )
    with pytest.raises(RuntimeError):
        await service.delete_source(source.id)
    assert source.is_enabled is False
    assert source.dispatch_token is None
    assert source.lease_expires_at is None
    source.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_management_requires_system_superuser_not_delegated_admin():
    with pytest.raises(BusinessError) as raised:
        await api.require_superuser(SimpleNamespace(is_superuser=False))
    assert raised.value.status_code == 403
    user = SimpleNamespace(is_superuser=True)
    assert await api.require_superuser(user) is user
    for route in api.router.routes:
        assert any(
            dependency.call is api.require_superuser
            for dependency in route.dependant.dependencies
        )


def test_source_fields_are_immutable_and_intervals_are_bounded():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        api.SourceUpdate(knowledge_base_id=str(uuid4()))
    for value in (0, 43201):
        with pytest.raises(ValidationError):
            api.SourceUpdate(interval_minutes=value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 400, 403])
@pytest.mark.parametrize("structured", [False, True])
async def test_missing_api_permissions_explain_scopes_without_leaking_details(
    transport_client, status, structured
):
    from app.core.i18n import current_language

    def handler(request):
        if request.url.path.endswith("/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "secret-token"}
            )
        body = {"code": 99991672, "msg": "secret provider response"}
        if structured:
            body["error"] = {
                "permission_violations": [
                    {"subject": "wiki:space:retrieve"},
                    {"subject": "https://secret.invalid/token"},
                ]
            }
        return httpx.Response(status, json=body)

    with pytest.raises(feishu.FeishuAPIError) as raised:
        await transport_client(handler).list_wiki_spaces()
    assert (
        not raised.value.permission_denied
    )  # Missing app scopes must not trigger local deletion.
    for language in ("en", "zh"):
        token = current_language.set(language)
        try:
            message = service.public_error(raised.value)
        finally:
            current_language.reset(token)
        assert "wiki:space:retrieve" in message
        assert "99991672" in message
        assert "secret" not in message
        assert ("审批" if language == "zh" else "approval") in message


def test_resource_permission_error_is_not_reported_as_missing_api_scopes():
    message = service.public_error(feishu.FeishuAPIError("secret", code=131006))
    assert "member" in message
    assert "99991672" not in message
    assert "secret" not in message


@pytest.mark.parametrize(
    ("path", "scopes"),
    [
        ("/wiki/v2/spaces", ("wiki:space:retrieve", "wiki:wiki:readonly", "wiki:wiki")),
        (
            "/bitable/v1/apps/app/tables",
            ("bitable:app:readonly", "bitable:app", "base:table:read"),
        ),
    ],
)
def test_missing_scope_guidance_matches_failed_api(path, scopes):
    from app.core.i18n import current_language

    error = feishu.FeishuAPIError("redacted", code=99991672, required_scopes=scopes)
    token = current_language.set("zh")
    try:
        message = service.public_error(error)
    finally:
        current_language.reset(token)
    assert all(scope in message for scope in scopes)
    assert "知识空间列表只需" not in message
    assert "权限管理" in message


@pytest.mark.asyncio
async def test_unchanged_import_without_explicit_model_preserves_existing_document(
    monkeypatch, source
):
    import hashlib

    content = service.FeishuContent(filename="source.md", content=b"existing text")
    original_id = uuid4()
    original = SimpleNamespace(
        id=original_id,
        status="completed",
        name="Old title",
        metadata={},
        save=AsyncMock(),
    )
    mapping = SimpleNamespace(
        document_id=original_id,
        content_hash=hashlib.sha256(content.content).hexdigest(),
        last_error="previous error",
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        service.KnowledgeBase,
        "get",
        AsyncMock(
            return_value=SimpleNamespace(
                id=source.knowledge_base_id, embedding_model_id=None
            )
        ),
    )
    monkeypatch.setattr(service, "_cleanup_pending", AsyncMock())
    monkeypatch.setattr(service.Document, "filter", Mock(return_value=Query(original)))

    changed = await service.import_content(
        source, mapping, {"node_token": "node", "title": "Renamed"}, content
    )

    assert changed is False
    assert mapping.document_id == original_id
    assert mapping.last_error is None
    assert original.name == "Renamed"
    assert original.metadata["feishu_node_token"] == "node"


@pytest.mark.parametrize("language", ["en", "zh"])
def test_conversion_errors_are_not_reported_as_embedding_configuration_failures(
    language,
):
    from app.core.i18n import current_language

    token = current_language.set(language)
    try:
        with pytest.raises(service.ImportProcessingError) as raised:
            service._inline([{"reminder": {"create_user_id": "redacted"}}])
        message = service.public_error(raised.value)
        assert ("转换失败" if language == "zh" else "conversion failed") in message
        assert message != service.public_error(service._ImportIndexingError())
        assert "redacted" not in message
    finally:
        current_language.reset(token)


@pytest.mark.parametrize("whole_day", [True, False])
def test_reminder_preserves_date_notification_flags_and_surrounding_text(whole_day):
    reminder = {
        "expire_time": "1625130000000",
        "notify_time": "1625130000000000",
        "is_notify": False,
        "is_whole_day": whole_day,
        "create_user_id": "user-id",
        "text_element_style": {"bold": True},
    }
    rendered = service._inline(
        [
            {"text_run": {"content": "Before "}},
            {"reminder": reminder},
            {"text_run": {"content": " after"}},
        ]
    )
    assert rendered.startswith("Before **Reminder: 2021-07-01T09:00:00.000+00:00")
    assert "expire_time=1625130000000 ms" in rendered
    assert "notify_time=1625130000000000 ms" in rendered
    assert f"is_whole_day={str(whole_day).lower()}" in rendered
    assert "is_notify=false" in rendered
    assert "create_user_id=user-id" in rendered
    assert rendered.endswith("** after")


@pytest.mark.parametrize("value", [None, True, "invalid", 1.5])
def test_invalid_reminder_timestamp_aborts_instead_of_dropping_content(value):
    with pytest.raises(service.ImportProcessingError):
        service._inline([{"reminder": {"expire_time": value, "notify_time": 0}}])


@pytest.mark.asyncio
@pytest.mark.parametrize("document_fails", [False, True])
async def test_sync_skips_unsupported_types_without_hiding_real_errors(
    monkeypatch, source, document_fails
):
    nodes = [
        {
            "node_token": "mindnote-node",
            "obj_type": "mindnote",
            "obj_token": "mindnote",
            "title": "思维笔记",
        },
        {
            "node_token": "file-node",
            "obj_type": "file",
            "obj_token": "video",
            "title": "视频",
        },
        {
            "node_token": "doc-node",
            "obj_type": "docx",
            "obj_token": "doc",
            "title": "正文",
        },
    ]
    mappings = {
        node["obj_token"]: SimpleNamespace(
            obj_type=node["obj_type"],
            obj_token=node["obj_token"],
            node_token=node["node_token"],
            last_error="previous failure",
            save=AsyncMock(),
        )
        for node in nodes
    }

    async def mapping_for(**kwargs):
        return mappings[kwargs["obj_token"]], False

    monkeypatch.setattr(service, "source_lock", unlocked)
    monkeypatch.setattr(service, "get_source", AsyncMock(return_value=source))
    monkeypatch.setattr(
        service,
        "configured_client",
        AsyncMock(
            return_value=SimpleNamespace(list_wiki_nodes=AsyncMock(return_value=nodes))
        ),
    )
    monkeypatch.setattr(
        service.KnowledgeBase,
        "filter",
        Mock(return_value=Query(SimpleNamespace(id=source.knowledge_base_id))),
    )
    monkeypatch.setattr(service.FeishuKnowledgeDocument, "get_or_create", mapping_for)
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument,
        "filter",
        Mock(return_value=Query(list(mappings.values()))),
    )
    monkeypatch.setattr(
        service,
        "download_file",
        AsyncMock(side_effect=service.UnsupportedContentError("video")),
    )
    monkeypatch.setattr(
        service,
        "load_rich_content",
        AsyncMock(
            return_value=service.FeishuContent("source.md", b"text"),
            side_effect=httpx.ReadTimeout("temporary") if document_fails else None,
        ),
    )
    monkeypatch.setattr(service, "import_content", AsyncMock(return_value=True))

    result = await service.sync_source(source.id)

    assert result["status"] == ("error" if document_fails else "success")
    assert source.status == result["status"]
    assert (source.last_error is not None) == document_fails
    assert result["failed"] == int(document_fails)
    assert result["unsupported"] == 2
    assert result["indexed"] == int(not document_fails)
    assert [entry["node_token"] for entry in result["errors"]] == (
        ["doc-node"] if document_fails else []
    )
    assert [entry["node_title"] for entry in result["skipped"]] == ["思维笔记", "视频"]
    assert all(entry["reason"] for entry in result["skipped"])
    assert mappings["mindnote"].last_error is None
    assert mappings["video"].last_error is None
    assert source.last_result == {
        key: value for key, value in result.items() if key != "status"
    }
