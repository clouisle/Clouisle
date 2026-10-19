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


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx.ReadTimeout("private url"), "feishu_knowledge_connection_failed"),
        (service._ImportIndexingError(), "feishu_knowledge_processing_failed"),
        (
            service.ImportProcessingError("secret details"),
            "feishu_knowledge_conversion_failed",
        ),
        (RuntimeError("provider secret"), "feishu_knowledge_sync_failed"),
    ],
)
def test_public_error_redacts_transport_indexing_conversion_and_unknown_errors(
    error, expected
):
    message = service.public_error(error)
    assert "secret details" not in message
    assert "provider secret" not in message
    assert message == service.t(expected)


@pytest.mark.asyncio
async def test_configured_client_fails_closed_for_missing_disabled_and_invalid_secret(
    monkeypatch,
):
    async def missing(_name):
        raise ValueError("must not leak")

    monkeypatch.setattr(service, "get_builtin_integration", missing)
    with pytest.raises(BusinessError) as absent:
        await service.configured_client()
    assert absent.value.msg_key == "feishu_not_configured"

    async def return_integration(value):
        return value

    monkeypatch.setattr(
        service,
        "get_builtin_integration",
        lambda _name: return_integration(SimpleNamespace(is_enabled=False)),
    )
    with pytest.raises(BusinessError) as disabled:
        await service.configured_client()
    assert disabled.value.msg_key == "feishu_knowledge_disabled"

    monkeypatch.setattr(
        service,
        "get_builtin_integration",
        lambda _name: return_integration(
            SimpleNamespace(
                is_enabled=True,
                config={"app_id": "id"},
                credentials={"app_secret": "encrypted"},
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "FeishuClient",
        Mock(side_effect=service.IntegrationSecretError("secret")),
    )
    with pytest.raises(BusinessError) as secret:
        await service.configured_client()
    assert secret.value.msg_key == "feishu_not_configured"


@pytest.mark.asyncio
async def test_import_removal_hides_document_before_external_cleanup_and_keeps_retry_identity(
    monkeypatch,
):
    document = SimpleNamespace(
        id=uuid4(),
        status="completed",
        file_path="source.md",
        save=AsyncMock(),
        delete=AsyncMock(),
    )
    mapping = SimpleNamespace(
        document_id=document.id, content_hash="old-hash", save=AsyncMock()
    )
    kb = SimpleNamespace(id=uuid4(), team_id=uuid4())
    monkeypatch.setattr(service, "_cleanup_pending", AsyncMock())
    monkeypatch.setattr(service.Document, "filter", Mock(return_value=Query(document)))

    async def fail_projection(*args, **kwargs):
        assert document.status == "error"
        document.save.assert_awaited_once_with(update_fields=["status"])
        raise OSError("vector store unavailable")

    monkeypatch.setattr(service, "_delete_projection", fail_projection)
    with pytest.raises(OSError, match="vector store unavailable"):
        await service.remove_import(mapping, kb)
    assert mapping.document_id == document.id
    assert mapping.content_hash == "old-hash"
    document.delete.assert_not_awaited()
    mapping.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_removal_clears_mapping_only_after_document_cleanup(monkeypatch):
    document = SimpleNamespace(
        id=uuid4(),
        status="completed",
        file_path="source.md",
        save=AsyncMock(),
        delete=AsyncMock(),
    )
    mapping = SimpleNamespace(
        document_id=document.id, content_hash="old-hash", save=AsyncMock()
    )
    kb = SimpleNamespace(id=uuid4(), team_id=uuid4())
    monkeypatch.setattr(service, "_cleanup_pending", AsyncMock())
    monkeypatch.setattr(service.Document, "filter", Mock(return_value=Query(document)))
    monkeypatch.setattr(service, "_delete_projection", AsyncMock())
    monkeypatch.setattr(service, "delete_lexical_document", AsyncMock())
    monkeypatch.setattr(service, "_delete_import_file", AsyncMock())
    monkeypatch.setattr(service, "_recount_kb", AsyncMock())
    await service.remove_import(mapping, kb)
    assert document.status == "error"
    document.delete.assert_awaited_once()
    assert mapping.document_id is None and mapping.content_hash is None


@pytest.mark.asyncio
@pytest.mark.parametrize("has_metadata", [False, True])
async def test_promoted_media_uses_stable_document_urls_without_losing_stage_identity(
    monkeypatch, has_metadata
):
    stage_id, final_id = uuid4(), uuid4()
    old = f"/documents/{stage_id}/media/photo.png"
    new = f"/documents/{final_id}/media/photo.png"
    stage = SimpleNamespace(id=stage_id, metadata={"image": old})
    chunk = SimpleNamespace(
        content=f"![photo]({old})",
        metadata={"image": old} if has_metadata else None,
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        service.DocumentChunk, "filter", Mock(return_value=Query([chunk]))
    )
    await service._promote_media(stage, final_id)
    assert stage.metadata == {"image": new, "feishu_media_document_id": str(stage_id)}
    assert chunk.content == f"![photo]({new})"
    assert chunk.metadata == ({"image": new} if has_metadata else None)
    chunk.save.assert_awaited_once_with(update_fields=["content", "metadata"])


def test_rich_inline_preserves_mentions_equations_and_code_escaping():
    text = service._inline(
        [
            {"mention_doc": {"title": "Guide", "url": "https://example.com/guide"}},
            {"mention_user": {"user_id": "author"}},
            {"equation": {"content": "x^2"}},
            {
                "text_run": {
                    "content": "a`b",
                    "text_element_style": {"inline_code": True},
                }
            },
            {
                "text_run": {
                    "content": "old",
                    "text_element_style": {"italic": True, "strikethrough": True},
                }
            },
        ]
    )
    assert text == "[Guide](https://example.com/guide)@author$x^2$`a\\`b`~~*old*~~"


@pytest.mark.parametrize("key", ["is_notify", "is_whole_day"])
@pytest.mark.parametrize("value", ["true", 1, None])
def test_reminder_rejects_nonboolean_flags_instead_of_silently_changing_meaning(
    key, value
):
    with pytest.raises(service.ImportProcessingError, match="flag"):
        service._inline(
            [{"reminder": {"expire_time": 0, "notify_time": 0, key: value}}]
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_pending_cleanup_keeps_retry_handles_until_external_cleanup_succeeds(
    monkeypatch, fail
):
    stage_id = uuid4()
    mapping = SimpleNamespace(
        staging_document_id=stage_id,
        document_id=None,
        pending_file_path="pending.md",
        obsolete_file_path="old.md",
        cleanup_chunk_ids=[str(uuid4())],
        save=AsyncMock(),
    )
    kb = SimpleNamespace(id=uuid4())
    deleted = []

    async def delete_projection(*args, **kwargs):
        if fail:
            raise OSError("vector store unavailable")

    async def delete_file(kb_id, path):
        deleted.append(path)

    monkeypatch.setattr(service, "_delete_projection", delete_projection)
    monkeypatch.setattr(service, "_delete_import_file", delete_file)
    if fail:
        with pytest.raises(OSError):
            await service._cleanup_pending(mapping, kb)
        assert mapping.staging_document_id == stage_id
        assert mapping.pending_file_path == "pending.md"
        mapping.save.assert_not_awaited()
    else:
        await service._cleanup_pending(mapping, kb)
        assert deleted == ["pending.md", "old.md"]
        assert mapping.staging_document_id is None
        assert mapping.pending_file_path is None and mapping.obsolete_file_path is None
        assert mapping.cleanup_chunk_ids == []
        mapping.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_continues_past_busy_and_failed_sources(monkeypatch):
    identifiers = [uuid4() for _ in range(3)]
    query = SimpleNamespace(values_list=AsyncMock(return_value=identifiers))
    monkeypatch.setattr(
        service.FeishuKnowledgeSource, "filter", Mock(return_value=query)
    )
    attempted = []

    async def queue(identifier):
        attempted.append(identifier)
        if identifier == identifiers[0]:
            raise service.SourceBusyError()
        if identifier == identifiers[1]:
            raise OSError("broker unavailable")

    monkeypatch.setattr(service, "queue_source", queue)
    assert await service.dispatch_due_sources() == {"queued": 1, "failed": 1}
    assert attempted == identifiers


@pytest.mark.asyncio
async def test_failed_source_deletion_persists_pause_before_cleanup(
    monkeypatch, source
):
    source.delete = AsyncMock()
    source.dispatch_token = uuid4()
    source.lease_expires_at = service.utcnow() + timedelta(minutes=1)
    monkeypatch.setattr(service, "source_lock", unlocked)
    monkeypatch.setattr(service, "get_source", AsyncMock(return_value=source))
    monkeypatch.setattr(
        service.KnowledgeBase,
        "get",
        AsyncMock(return_value=SimpleNamespace(id=source.knowledge_base_id)),
    )
    mapping = SimpleNamespace(delete=AsyncMock())
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument, "filter", Mock(return_value=Query([mapping]))
    )

    async def fail(*args):
        assert source.is_enabled is False
        assert source.status == "idle" and source.dispatch_token is None
        source.save.assert_awaited_once()
        raise OSError("cleanup unavailable")

    monkeypatch.setattr(service, "remove_import", fail)
    with pytest.raises(OSError):
        await service.delete_source(source.id)
    mapping.delete.assert_not_awaited()
    source.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_scan_aborts_before_listing_when_target_knowledge_base_is_inactive(
    monkeypatch, source
):
    monkeypatch.setattr(service.KnowledgeBase, "filter", Mock(return_value=Query(None)))
    client = SimpleNamespace(list_wiki_nodes=AsyncMock())
    with pytest.raises(BusinessError) as raised:
        await service._scan_source(source, client)
    assert raised.value.msg_key == "feishu_knowledge_target_unavailable"
    client.list_wiki_nodes.assert_not_awaited()


@pytest.mark.asyncio
async def test_scan_carries_space_name_and_deduplicates_repeated_nodes(
    monkeypatch, source
):
    source.last_result = {"space_name": "工程空间"}
    kb = SimpleNamespace(id=source.knowledge_base_id)
    mapping = SimpleNamespace(
        obj_type="docx", obj_token="doc", node_token="n1", save=AsyncMock()
    )
    monkeypatch.setattr(service.KnowledgeBase, "filter", Mock(return_value=Query(kb)))
    get_or_create = AsyncMock(return_value=(mapping, False))
    monkeypatch.setattr(service.FeishuKnowledgeDocument, "get_or_create", get_or_create)
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument, "filter", Mock(return_value=Query([]))
    )
    monkeypatch.setattr(
        service,
        "load_rich_content",
        AsyncMock(return_value=service.FeishuContent("source.md", b"text")),
    )
    import_content = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "import_content", import_content)
    client = SimpleNamespace(
        list_wiki_nodes=AsyncMock(
            return_value=[
                {
                    "node_token": "n1",
                    "obj_type": "docx",
                    "obj_token": "doc",
                    "title": "一",
                },
                {
                    "node_token": "n2",
                    "obj_type": "docx",
                    "obj_token": "doc",
                    "title": "重复",
                },
            ]
        )
    )
    result = await service._scan_source(source, client)
    assert result["space_name"] == "工程空间"
    assert result["scanned"] == 1 and result["indexed"] == 1
    assert get_or_create.await_count == 1
    assert import_content.await_args.args[0] is source
    assert import_content.await_args.args[2]["node_token"] == "n1"


@pytest.mark.asyncio
async def test_scan_imports_tabular_content_and_reports_conversion_warnings(
    monkeypatch, source
):
    kb = SimpleNamespace(id=source.knowledge_base_id)
    mapping = SimpleNamespace(
        obj_type="sheet",
        obj_token="sheet-token",
        node_token="n",
        last_error=None,
        save=AsyncMock(),
    )
    monkeypatch.setattr(service.KnowledgeBase, "filter", Mock(return_value=Query(kb)))
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument,
        "get_or_create",
        AsyncMock(return_value=(mapping, False)),
    )
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument, "filter", Mock(return_value=Query([]))
    )
    load_tabular = AsyncMock(
        return_value=service.FeishuContent(
            "sheet.csv", b"a,b", warnings=["unsupported_block:99"]
        )
    )
    monkeypatch.setattr(service, "load_tabular", load_tabular)
    monkeypatch.setattr(service, "load_rich_content", AsyncMock())
    monkeypatch.setattr(service, "download_file", AsyncMock())
    monkeypatch.setattr(service, "import_content", AsyncMock(return_value=False))
    client = SimpleNamespace(
        list_wiki_nodes=AsyncMock(
            return_value=[
                {
                    "node_token": "n",
                    "obj_type": "sheet",
                    "obj_token": "sheet-token",
                    "title": "表格",
                }
            ]
        )
    )
    result = await service._scan_source(source, client)
    assert load_tabular.await_args.args == (client, "sheet", "sheet-token", "表格")
    service.load_rich_content.assert_not_awaited()
    service.download_file.assert_not_awaited()
    assert result["unchanged"] == 1 and result["indexed"] == 0
    assert result["warnings"] == [
        {"node_token": "n", "node_title": "表格", "blocks": ["unsupported_block:99"]}
    ]
    assert mapping.last_error is None


@pytest.mark.asyncio
async def test_document_permission_revocation_removes_only_that_import(
    monkeypatch, source
):
    kb = SimpleNamespace(id=source.knowledge_base_id)
    mapping = SimpleNamespace(
        obj_type="docx",
        obj_token="doc",
        node_token="n",
        last_error="stale failure",
        save=AsyncMock(),
    )
    monkeypatch.setattr(service.KnowledgeBase, "filter", Mock(return_value=Query(kb)))
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument,
        "get_or_create",
        AsyncMock(return_value=(mapping, False)),
    )
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument, "filter", Mock(return_value=Query([]))
    )
    denied = feishu.FeishuAPIError(
        "doc is not shared with the app", code=131006, status_code=403
    )
    assert denied.permission_denied
    monkeypatch.setattr(service, "load_rich_content", AsyncMock(side_effect=denied))
    remove = AsyncMock()
    monkeypatch.setattr(service, "remove_import", remove)
    client = SimpleNamespace(
        list_wiki_nodes=AsyncMock(
            return_value=[
                {
                    "node_token": "n",
                    "obj_type": "docx",
                    "obj_token": "doc",
                    "title": "正文",
                }
            ]
        )
    )
    result = await service._scan_source(source, client)
    remove.assert_awaited_once_with(mapping, kb)
    assert result["removed"] == 1 and result["failed"] == 1
    assert result["errors"] == [
        {"node_token": "n", "node_title": "正文", "error": mapping.last_error}
    ]
    assert mapping.last_error == service.public_error(denied)
    assert "not shared" not in mapping.last_error
    mapping.save.assert_awaited_once_with(update_fields=["last_error"])


@pytest.mark.asyncio
async def test_failed_removal_of_unseen_import_keeps_it_retryable(monkeypatch, source):
    kb = SimpleNamespace(id=source.knowledge_base_id)
    stale = SimpleNamespace(
        obj_type="docx",
        obj_token="gone",
        node_token="stale-node",
        last_error=None,
        save=AsyncMock(),
        delete=AsyncMock(),
    )
    monkeypatch.setattr(service.KnowledgeBase, "filter", Mock(return_value=Query(kb)))
    monkeypatch.setattr(
        service.FeishuKnowledgeDocument, "filter", Mock(return_value=Query([stale]))
    )
    monkeypatch.setattr(
        service, "remove_import", AsyncMock(side_effect=OSError("vector unavailable"))
    )
    client = SimpleNamespace(list_wiki_nodes=AsyncMock(return_value=[]))
    result = await service._scan_source(source, client)
    assert result["scanned"] == 0 and result["removed"] == 0 and result["failed"] == 1
    assert result["errors"] == [{"node_token": "stale-node", "error": stale.last_error}]
    assert stale.last_error == service.public_error(OSError("any other failure"))
    stale.delete.assert_not_awaited()
    stale.save.assert_awaited_once_with(update_fields=["last_error"])


@pytest.mark.asyncio
async def test_failed_scan_marks_error_and_reschedules_the_source(monkeypatch, source):
    source.interval_minutes = 1
    monkeypatch.setattr(service, "source_lock", unlocked)
    monkeypatch.setattr(service, "get_source", AsyncMock(return_value=source))
    failure = RuntimeError("provider secret detail")
    monkeypatch.setattr(service, "configured_client", AsyncMock(side_effect=failure))
    scan = AsyncMock()
    monkeypatch.setattr(service, "_scan_source", scan)
    result = await service.sync_source(source.id)
    assert result["status"] == "error"
    assert result["scan_complete"] is False and result["failed"] == 1
    assert result["errors"] == [{"error": service.public_error(failure)}]
    assert "provider secret detail" not in result["errors"][0]["error"]
    assert source.status == "error"
    assert source.last_error == result["errors"][0]["error"]
    assert source.last_result == {
        key: value for key, value in result.items() if key != "status"
    }
    assert source.dispatch_token is None and source.lease_expires_at is None
    assert not hasattr(source, "last_synced_at")
    assert 59 < (source.next_sync_at - service.utcnow()).total_seconds() <= 60
    scan.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_reports_busy_deleted_and_propagates_unexpected_failures(
    monkeypatch, source
):
    from app.schemas.response import ResponseCode

    class BusyLock:
        def __call__(self, _source_id):
            return self

        async def __aenter__(self):
            raise service.SourceBusyError()

        async def __aexit__(self, *_exception):
            return False

    monkeypatch.setattr(service, "source_lock", BusyLock())
    lookup = AsyncMock(return_value=source)
    monkeypatch.setattr(service, "get_source", lookup)
    assert await service.sync_source(source.id) == {"status": "busy"}
    lookup.assert_not_awaited()
    source.save.assert_not_awaited()

    async def missing(_source_id):
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="feishu_knowledge_source_not_found",
            status_code=404,
        )

    monkeypatch.setattr(service, "source_lock", unlocked)
    monkeypatch.setattr(service, "get_source", missing)
    assert await service.sync_source(source.id) == {"status": "deleted"}

    async def rejected(_source_id):
        raise BusinessError(
            code=ResponseCode.BAD_REQUEST, msg_key="feishu_knowledge_target_unavailable"
        )

    monkeypatch.setattr(service, "get_source", rejected)
    with pytest.raises(BusinessError) as raised:
        await service.sync_source(source.id)
    assert raised.value.msg_key == "feishu_knowledge_target_unavailable"


@pytest.mark.asyncio
async def test_heartbeat_refreshes_the_lease_for_its_own_dispatch_token(monkeypatch):
    import asyncio

    source_id, token = uuid4(), uuid4()
    leases = []
    query = SimpleNamespace(
        update=AsyncMock(
            side_effect=lambda **kwargs: leases.append(kwargs["lease_expires_at"])
        )
    )
    monkeypatch.setattr(
        service.FeishuKnowledgeSource, "filter", Mock(return_value=query)
    )
    sleeps = AsyncMock(side_effect=[None, RuntimeError("heartbeat stopped")])
    monkeypatch.setattr(
        service,
        "asyncio",
        SimpleNamespace(create_task=asyncio.create_task, sleep=sleeps),
    )
    with pytest.raises(RuntimeError, match="heartbeat stopped"):
        await asyncio.create_task(service._heartbeat(source_id, token))
    assert sleeps.await_count == 2
    assert len(leases) == 1
    assert service.FeishuKnowledgeSource.filter.call_args.kwargs == {
        "id": source_id,
        "dispatch_token": token,
    }
    assert 299 < (leases[0] - service.utcnow()).total_seconds() <= 300


@pytest.mark.asyncio
async def test_sqlite_source_lock_serializes_concurrent_runs(monkeypatch):
    source_id = uuid4()
    monkeypatch.setattr(
        service,
        "connections",
        SimpleNamespace(
            get=Mock(
                return_value=SimpleNamespace(
                    capabilities=SimpleNamespace(dialect="sqlite")
                )
            )
        ),
    )
    async with service.source_lock(source_id):
        with pytest.raises(service.SourceBusyError):
            async with service.source_lock(source_id):
                pytest.fail("a held source lock must not be reentrant")
    async with service.source_lock(source_id):
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("acquired", [True, False])
async def test_postgres_session_lock_reports_busy_and_always_releases(
    monkeypatch, acquired
):
    import hashlib

    source_id = uuid4()
    database = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="postgres"),
        host="db",
        port=5432,
        user="clouisle",
        password="secret",
        database="clouisle",
        server_settings={},
        extra={},
    )
    monkeypatch.setattr(
        service, "connections", SimpleNamespace(get=Mock(return_value=database))
    )
    connection = SimpleNamespace(
        fetchval=AsyncMock(return_value=acquired), close=AsyncMock()
    )
    monkeypatch.setattr(
        service, "asyncpg", SimpleNamespace(connect=AsyncMock(return_value=connection))
    )
    key = int.from_bytes(
        hashlib.sha256(f"feishu-wiki:{source_id}".encode()).digest()[:8],
        "big",
        signed=True,
    )
    if acquired:
        async with service.source_lock(source_id):
            assert connection.fetchval.await_args.args == (
                "SELECT pg_try_advisory_lock($1::bigint)",
                key,
            )
    else:
        with pytest.raises(service.SourceBusyError):
            async with service.source_lock(source_id):
                pytest.fail("an unacquired advisory lock must not yield")
        connection.fetchval.assert_awaited_once()
    connection.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_source_is_reported_as_not_found(monkeypatch):
    from app.schemas.response import ResponseCode

    monkeypatch.setattr(
        service.FeishuKnowledgeSource, "filter", Mock(return_value=Query(None))
    )
    with pytest.raises(BusinessError) as raised:
        await service.get_source(uuid4())
    assert raised.value.status_code == 404
    assert raised.value.code == ResponseCode.NOT_FOUND
    assert raised.value.msg_key == "feishu_knowledge_source_not_found"


def test_source_output_exposes_last_known_space_name_and_managed_fields():
    identifier, kb_id = uuid4(), uuid4()
    synced = service.utcnow()
    output = service.source_output(
        SimpleNamespace(
            id=identifier,
            knowledge_base_id=kb_id,
            knowledge_base=SimpleNamespace(name="工程库"),
            space_id="space",
            last_result={"space_name": "工程空间"},
            name="Wiki 源",
            interval_minutes=30,
            is_enabled=True,
            status="success",
            last_synced_at=synced,
            last_error=None,
            created_at=synced,
            updated_at=synced,
        )
    )
    assert output == {
        "id": str(identifier),
        "knowledge_base_id": str(kb_id),
        "knowledge_base_name": "工程库",
        "space_id": "space",
        "space_name": "工程空间",
        "name": "Wiki 源",
        "interval_minutes": 30,
        "is_enabled": True,
        "status": "success",
        "last_synced_at": synced,
        "last_error": None,
        "last_result": {"space_name": "工程空间"},
        "created_at": synced,
        "updated_at": synced,
    }


def test_public_error_reports_api_and_business_failures_without_provider_detail():
    api_error = feishu.FeishuAPIError(
        "raw provider detail", code=1770001, status_code=500
    )
    assert not api_error.permission_denied
    message = service.public_error(api_error)
    assert "1770001" in message and "500" in message
    assert "raw provider detail" not in message
    assert service.public_error(BusinessError()) == service.public_error(
        RuntimeError("boom")
    )


@pytest.mark.asyncio
async def test_configured_client_requires_app_id_and_secret(monkeypatch):
    async def integration(_name):
        return SimpleNamespace(is_enabled=True, config={}, credentials={})

    monkeypatch.setattr(service, "get_builtin_integration", integration)
    with pytest.raises(BusinessError) as raised:
        await service.configured_client()
    assert raised.value.msg_key == "feishu_not_configured"


class _Collections:
    def __init__(self, names):
        self.collections = [SimpleNamespace(name=name) for name in names]


class _Qdrant:
    def __init__(self, names):
        self.names = names
        self.deletes = []
        self.payloads = []

    async def get_collections(self):
        return _Collections(self.names)

    async def delete(self, collection_name, points_selector, wait):
        self.deletes.append((collection_name, points_selector, wait))

    async def set_payload(self, collection_name, payload, points, wait):
        self.payloads.append((collection_name, payload, points, wait))


def vector_shim(monkeypatch, client, dimension=1024):
    real = service.vectors
    monkeypatch.setattr(
        service,
        "vectors",
        SimpleNamespace(
            _get_qdrant_client=AsyncMock(return_value=client),
            get_kb_embedding_dimension=AsyncMock(return_value=dimension),
            _collection_name=real._collection_name,
            qmodels=real.qmodels,
            settings=SimpleNamespace(
                QDRANT_COLLECTION_PREFIX=real.settings.QDRANT_COLLECTION_PREFIX
            ),
        ),
    )
    return SimpleNamespace(qmodels=real.qmodels)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selection",
    ["document", "chunks", "nothing"],
)
async def test_projection_deletion_targets_managed_collections_or_skips_empty_selection(
    monkeypatch, selection
):
    kb = SimpleNamespace(id=uuid4())
    client = _Qdrant(["kb_dim_1024", "kb_dim_768", "unrelated_collection"])
    vector_shim(monkeypatch, client)
    document_id = uuid4()
    if selection == "document":
        await service._delete_projection(kb, document_id=document_id)
    elif selection == "chunks":
        await service._delete_projection(kb, chunk_ids=["chunk-a", "chunk-b"])
    else:
        await service._delete_projection(kb, chunk_ids=[])
    if selection == "nothing":
        assert client.deletes == []
        return
    assert [name for name, _, _ in client.deletes] == ["kb_dim_1024", "kb_dim_768"]
    assert all(wait for _, _, wait in client.deletes)
    selector = client.deletes[0][1]
    if selection == "document":
        assert type(selector).__name__ == "FilterSelector"
        condition = selector.filter.must[0]
        assert condition.key == "document_id"
        assert condition.match.value == str(document_id)
    else:
        assert type(selector).__name__ == "PointIdsList"
        assert selector.points == ["chunk-a", "chunk-b"]


class _ChunkIds(Query):
    def __init__(self, values):
        super().__init__(values)

    async def values_list(self, *_args, **_kwargs):
        return self.value


@pytest.mark.asyncio
@pytest.mark.parametrize("promoted", [True, False])
async def test_pending_cleanup_retags_vectors_then_drops_or_deletes_the_stage(
    monkeypatch, promoted
):
    kb = SimpleNamespace(id=uuid4())
    document_id = uuid4()
    chunk_id = uuid4()
    staging_id = document_id if promoted else uuid4()
    mapping = SimpleNamespace(
        staging_document_id=staging_id,
        document_id=document_id,
        pending_file_path=None,
        obsolete_file_path=None,
        cleanup_chunk_ids=[],
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        service.DocumentChunk, "filter", Mock(return_value=_ChunkIds([chunk_id]))
    )
    client = _Qdrant([])
    vector_shim(monkeypatch, client)
    delete_projection = AsyncMock()
    monkeypatch.setattr(service, "_delete_projection", delete_projection)
    delete_file = AsyncMock()
    monkeypatch.setattr(service, "_delete_import_file", delete_file)
    await service._cleanup_pending(mapping, kb)
    assert client.payloads == [
        (
            "kb_dim_1024",
            {"document_id": str(document_id)},
            [str(chunk_id)],
            True,
        )
    ]
    if promoted:
        assert mapping.staging_document_id is None
        delete_projection.assert_not_awaited()
    else:
        delete_projection.assert_awaited_once_with(kb, document_id=staging_id)
    assert mapping.staging_document_id is None
    delete_file.assert_not_awaited()
    mapping.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_promoted_media_keeps_stage_identity_without_rewriting_urls(monkeypatch):
    stage_id = uuid4()
    stage = SimpleNamespace(id=stage_id, metadata=None)
    chunks = Mock(return_value=Query([]))
    monkeypatch.setattr(service.DocumentChunk, "filter", chunks)
    await service._promote_media(stage, stage_id)
    assert stage.metadata == {"feishu_media_document_id": str(stage_id)}
    chunks.assert_not_called()


class _GatewayClient:
    def __init__(self):
        self.calls = []
        self.status_checks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exception):
        return False

    async def put(self, path, params=None, content=None):
        self.calls.append((path, params, content))
        return SimpleNamespace(raise_for_status=self.raise_for_status)

    def raise_for_status(self):
        self.status_checks += 1


@pytest.mark.asyncio
async def test_import_file_uses_the_gateway_in_remote_mode_and_disk_locally(
    monkeypatch,
):
    gateway = _GatewayClient()
    monkeypatch.setattr(
        service, "upload_gateway", SimpleNamespace(client=lambda: gateway)
    )
    save = AsyncMock()
    monkeypatch.setattr(service.document_processor, "save_file", save)
    monkeypatch.setattr(
        service.document_processor, "_remote_mode", Mock(return_value=True)
    )
    await service._save_import_file(b"payload", "/documents/kb/stage.md")
    assert gateway.calls == [
        ("/internal/uploads/save", {"key": "/documents/kb/stage.md"}, b"payload")
    ]
    assert gateway.status_checks == 1
    save.assert_not_awaited()
    monkeypatch.setattr(
        service.document_processor, "_remote_mode", Mock(return_value=False)
    )
    await service._save_import_file(b"payload", "stage.md")
    save.assert_awaited_once_with(b"payload", "stage.md")


class _Totals(Query):
    def __init__(self, rows=None, count=0):
        super().__init__(rows or [])
        self.count_value = count

    def annotate(self, **_kwargs):
        return self

    def group_by(self, *_args):
        return self

    def values(self, *_args):
        return self

    async def count(self):
        return self.count_value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rows", "count"),
    [([{"chunks": 12, "tokens": 340}], 3), ([], 0)],
)
async def test_recount_publishes_document_and_token_totals(monkeypatch, rows, count):
    updates = []
    monkeypatch.setattr(
        service.Document,
        "filter",
        Mock(side_effect=[_Totals(rows), _Totals(count=count)]),
    )
    monkeypatch.setattr(
        service.KnowledgeBase,
        "filter",
        Mock(
            return_value=SimpleNamespace(
                update=AsyncMock(side_effect=lambda **kwargs: updates.append(kwargs))
            )
        ),
    )
    await service._recount_kb(uuid4())
    assert updates == [
        {
            "document_count": count,
            "total_chunks": int((rows[0].get("chunks") if rows else 0) or 0),
            "total_tokens": int((rows[0].get("tokens") if rows else 0) or 0),
        }
    ]


@pytest.mark.parametrize(
    ("table", "cells"),
    [
        ({"property": {"column_size": 2}}, ["c1"]),
        ({"property": {"column_size": 0}}, []),
    ],
)
def test_invalid_table_dimensions_abort_the_import(table, cells):
    blocks = [
        text_block("page", 1, "", children=["table"]),
        {
            "block_id": "table",
            "block_type": 31,
            "children": [],
            "table": {**table, "cells": cells},
        },
        text_block("c1", 2, "A"),
    ]
    with pytest.raises(service.ImportProcessingError, match="table dimensions"):
        service.blocks_to_markdown(blocks, "Title")


def test_docx_dividers_and_todo_states_render_as_markdown():
    done = text_block("done", 17, "Shipped")
    done["todo"]["style"] = {"done": True}
    blocks = [
        text_block("page", 1, "", children=["done", "open", "rule"]),
        done,
        text_block("open", 17, "Pending"),
        {"block_id": "rule", "block_type": 22},
    ]
    markdown, warnings = service.blocks_to_markdown(blocks, "Title")
    assert "- [x] Shipped\n\n- [ ] Pending\n\n---" in markdown
    assert warnings == []


def test_wiki_renderer_ignores_repeated_references_but_rejects_duplicate_blocks():
    blocks = [
        text_block("page", 1, "", children=["section", "section"]),
        text_block("section", 2, "Shared content"),
    ]
    markdown, warnings = service.blocks_to_markdown(blocks, "Shared")
    assert markdown.count("Shared content") == 1
    assert warnings == []

    with pytest.raises(service.ImportProcessingError, match="repeated Feishu block ID"):
        service.blocks_to_markdown(
            [text_block("same", 2, "first"), text_block("same", 2, "second")],
            "Duplicate",
        )


@pytest.mark.parametrize(
    "blocks",
    [
        [{"block_id": 7, "block_type": 2, "text": {}}],
        [
            text_block("a", 2, "A", children=["b"]),
            text_block("b", 2, "B", children=["a"]),
        ],
        [text_block("blank", 2, "   ")],
    ],
)
def test_wiki_renderer_rejects_invalid_unreachable_or_empty_content(blocks):
    with pytest.raises(service.ImportProcessingError):
        service.blocks_to_markdown(blocks, "Invalid")
