"""Unit tests for inspect_asset / read_asset / search_asset tools."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_tools import _execute_asset_tool
from app.services.citations import stable_citation_id
from app.schemas.response import BusinessError


def _agent(team_id=None, attachment_config=None):
    return SimpleNamespace(
        id=uuid4(), team_id=team_id, attachment_config=attachment_config or {}
    )


def _user(uid=None):
    return SimpleNamespace(id=uid or uuid4(), locale="en")


def _asset(*, ctype="text/plain", orig="file.txt", size=100):
    return SimpleNamespace(
        id=uuid4(),
        display_filename=orig,
        original_filename=orig,
        content_type=ctype,
        size=size,
        checksum="a" * 64,
        source=SimpleNamespace(value="upload"),
    )


def _make_service(asset, capabilities=None):
    svc = MagicMock()
    svc.resolve_ref = AsyncMock(return_value=asset)
    svc.capabilities = MagicMock(
        return_value=capabilities or ["inspect", "read", "search", "sandbox"]
    )
    svc.read = AsyncMock(return_value=b"hello")
    return svc


@pytest.fixture(autouse=True)
def mock_scoped_asset_resolution(monkeypatch):
    async def resolve_asset_ref(
        ref,
        *,
        scope_type,
        scope_id,
        user,
        api_key=None,
        expected_team_id=None,
    ):
        from app.services.asset import asset_service

        return await asset_service.resolve_ref(
            scope_type=scope_type,
            scope_id=scope_id,
            ref=ref,
            team_id=expected_team_id,
            user_id=user.id if user is not None else None,
        )

    monkeypatch.setattr(
        "app.services.asset_access.resolve_authorized_asset_ref", resolve_asset_ref
    )


@pytest.mark.asyncio
async def test_inspect_asset_returns_no_uuid():
    asset = _asset()
    svc = _make_service(asset)
    convo_id = str(uuid4())

    with (
        patch("app.services.asset.asset_service", svc),
        patch("app.api.v1.endpoints.upload.UPLOAD_ROOT", None),
        patch("app.services.upload_storage.get_upload_storage_backend", AsyncMock()),
    ):
        result = await _execute_asset_tool(
            "inspect_asset",
            {"ref": "abcd"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
        )

    data = json.loads(result)
    assert "asset_id" not in data
    assert data["ref"] == "abcd"
    assert data["filename"] == "file.txt"
    assert "capabilities" in data


@pytest.mark.asyncio
async def test_inspect_asset_missing_returns_not_found():
    svc = MagicMock()
    svc.resolve_ref = AsyncMock(
        side_effect=BusinessError(
            code="NOT_FOUND", msg_key="file_not_found", status_code=404
        )
    )
    convo_id = str(uuid4())

    with patch("app.services.asset.asset_service", svc):
        result = await _execute_asset_tool(
            "inspect_asset",
            {"ref": "abcd"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
        )

    data = json.loads(result)
    assert "error" in data
    assert "access_denied" not in data["error"]


@pytest.mark.asyncio
async def test_inspect_asset_forbidden_returns_access_denied():
    svc = MagicMock()
    svc.resolve_ref = AsyncMock(
        side_effect=BusinessError(
            code="FORBIDDEN", msg_key="access_denied", status_code=403
        )
    )
    convo_id = str(uuid4())

    with patch("app.services.asset.asset_service", svc):
        result = await _execute_asset_tool(
            "inspect_asset",
            {"ref": "abcd"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
        )

    data = json.loads(result)
    assert "error" in data
    assert data["error"] != ""


@pytest.mark.asyncio
async def test_read_asset_returns_bounded_document_page():
    asset = _asset(ctype="text/plain", orig="readme.txt")
    svc = _make_service(asset, capabilities=["inspect", "read", "search", "sandbox"])
    convo_id = str(uuid4())
    document = {
        "asset_id": str(asset.id),
        "filename": "readme.txt",
        "representation_id": "v1",
        "start_line": 1,
        "total_lines": 240,
        "segments": [{"line": 1, "text": "hello world", "continuation": False}],
        "next_cursor": "cursor-1",
        "eof": False,
    }

    with (
        patch("app.services.asset.asset_service", svc),
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            AsyncMock(return_value=object()),
        ),
        patch(
            "app.services.asset_document.read_document",
            new=AsyncMock(return_value=document),
        ) as read_document,
    ):
        result = await _execute_asset_tool(
            "read_asset",
            {"ref": "abcd", "start_line": 1, "line_count": 50},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
        )

    data = json.loads(result)
    assert data["segments"] == document["segments"]
    assert data["next_cursor"] == "cursor-1"
    assert data["eof"] is False
    assert data["ref"] == "abcd"
    assert data["citation_id"] == stable_citation_id("asset", asset.id)
    assert read_document.await_args.kwargs["start_line"] == 1
    assert read_document.await_args.kwargs["line_count"] == 50


@pytest.mark.asyncio
async def test_search_asset_returns_bounded_matches():
    asset = _asset(ctype="text/plain", orig="readme.txt")
    svc = _make_service(asset, capabilities=["inspect", "read", "search", "sandbox"])
    convo_id = str(uuid4())
    document = {
        "asset_id": str(asset.id),
        "filename": "readme.txt",
        "representation_id": "v1",
        "query": "hello",
        "total_lines": 240,
        "matches": [
            {
                "line": 4,
                "text": "hello world",
                "match_start": 0,
                "match_end": 5,
                "context": [{"line": 3, "text": "before"}],
            }
        ],
        "next_cursor": None,
        "eof": True,
    }

    with (
        patch("app.services.asset.asset_service", svc),
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            AsyncMock(return_value=object()),
        ),
        patch(
            "app.services.asset_document.search_document",
            new=AsyncMock(return_value=document),
        ) as search_document,
    ):
        result = await _execute_asset_tool(
            "search_asset",
            {"ref": "abcd", "query": "hello", "context_lines": 1, "limit": 5},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
        )

    data = json.loads(result)
    assert data["matches"] == document["matches"]
    assert data["ref"] == "abcd"
    assert data["citation_id"] == stable_citation_id("asset", asset.id)
    assert search_document.await_args.kwargs["query"] == "hello"
    assert search_document.await_args.kwargs["context_lines"] == 1
    assert search_document.await_args.kwargs["limit"] == 5


@pytest.mark.asyncio
async def test_search_asset_requires_query():
    asset = _asset(ctype="text/plain", orig="readme.txt")
    svc = _make_service(asset)
    convo_id = str(uuid4())

    with patch("app.services.asset.asset_service", svc):
        result = await _execute_asset_tool(
            "search_asset",
            {"ref": "abcd"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
        )

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_view_asset_validates_ref_without_materializing_bytes(monkeypatch):
    asset = _asset(ctype="image/png", orig="photo.png")
    from app.models.asset import AssetScopeType

    monkeypatch.setattr(
        "app.services.asset_access.resolve_authorized_asset_ref",
        AsyncMock(return_value=asset),
    )
    resolve = AsyncMock(
        return_value=(
            asset,
            None,
            json.dumps(
                {
                    "kind": "asset.view",
                    "version": 1,
                    "ref": "abcd",
                    "modality": "image",
                    "mime_type": "image/png",
                    "wire_mime_type": "image/png",
                    "checksum": asset.checksum,
                    "size": asset.size,
                    "extracted_text": False,
                    "selection": None,
                    "representation": {"kind": "native", "selection": None},
                }
            ),
        )
    )
    monkeypatch.setattr("app.services.asset_view.resolve_view_content", resolve)
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_helpers.model_utils.resolve_agent_chat_model",
        AsyncMock(return_value=SimpleNamespace(model=SimpleNamespace())),
    )

    result = await _execute_asset_tool(
        "view_asset",
        {"ref": "abcd"},
        agent=_agent(),
        user=_user(),
        conversation_id=str(uuid4()),
    )

    assert result.display_result["modality"] == "image"
    resolve.assert_awaited_once()
    assert resolve.await_args.kwargs["materialize"] is False
    assert resolve.await_args.kwargs["scope_type"] == AssetScopeType.CONVERSATION


@pytest.mark.asyncio
async def test_view_asset_requires_pdf_page_selection(monkeypatch):
    from app.llm.types import ContentType

    asset = _asset(ctype="application/pdf", orig="plan.pdf")
    svc = _make_service(asset)
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_helpers.model_utils.resolve_agent_chat_model",
        AsyncMock(return_value=SimpleNamespace(model=SimpleNamespace())),
    )
    monkeypatch.setattr(
        "app.llm.capabilities.get_effective_input_capabilities",
        lambda _model: SimpleNamespace(
            modalities=frozenset({ContentType.FILE}),
            mime_types={},
            limits={},
        ),
    )

    with patch("app.services.asset.asset_service", svc):
        result = await _execute_asset_tool(
            "view_asset",
            {"ref": "abcd"},
            agent=_agent(),
            user=_user(),
            conversation_id=str(uuid4()),
        )

    data = json.loads(result)
    assert "page selection" in data["error"]


@pytest.mark.asyncio
async def test_view_asset_pdf_without_file_support_falls_back_to_text(monkeypatch):
    from app.llm.types import ContentType

    asset = _asset(ctype="application/pdf", orig="plan.pdf")
    svc = _make_service(asset)
    document = {
        "asset_id": str(asset.id),
        "filename": "plan.pdf",
        "representation_id": "v1",
        "start_line": 1,
        "total_lines": 1,
        "segments": [{"line": 1, "text": "plan", "continuation": False}],
        "next_cursor": None,
        "eof": True,
    }
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_helpers.model_utils.resolve_agent_chat_model",
        AsyncMock(return_value=SimpleNamespace(model=SimpleNamespace())),
    )
    monkeypatch.setattr(
        "app.llm.capabilities.get_effective_input_capabilities",
        lambda _model: SimpleNamespace(
            modalities=frozenset({ContentType.TEXT}),
            mime_types={},
            limits={},
        ),
    )

    with (
        patch("app.services.asset.asset_service", svc),
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            AsyncMock(return_value=object()),
        ),
        patch(
            "app.services.asset_document.read_document",
            new=AsyncMock(return_value=document),
        ),
    ):
        result = await _execute_asset_tool(
            "view_asset",
            {"ref": "abcd"},
            agent=_agent(),
            user=_user(),
            conversation_id=str(uuid4()),
        )

    data = json.loads(result)
    assert data["segments"] == document["segments"]


@pytest.mark.asyncio
async def test_view_asset_extracted_text_returns_bounded_document(monkeypatch):
    asset = _asset(ctype="text/plain", orig="notes.txt")
    svc = _make_service(asset)
    document = {
        "asset_id": str(asset.id),
        "filename": "notes.txt",
        "representation_id": "v1",
        "start_line": 1,
        "total_lines": 2,
        "segments": [{"line": 1, "text": "notes", "continuation": False}],
        "next_cursor": "cursor-1",
        "eof": False,
    }
    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_helpers.model_utils.resolve_agent_chat_model",
        AsyncMock(return_value=SimpleNamespace(model=SimpleNamespace())),
    )
    resolve_view = AsyncMock()
    monkeypatch.setattr("app.services.asset_view.resolve_view_content", resolve_view)

    with (
        patch("app.services.asset.asset_service", svc),
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            AsyncMock(return_value=object()),
        ),
        patch(
            "app.services.asset_document.read_document",
            new=AsyncMock(return_value=document),
        ),
    ):
        result = await _execute_asset_tool(
            "view_asset",
            {"ref": "abcd", "extracted_text": True},
            agent=_agent(),
            user=_user(),
            conversation_id=str(uuid4()),
        )

    data = json.loads(result)
    assert data["eof"] is False
    assert data["ref"] == "abcd"
    resolve_view.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_asset_refuses_binary():
    asset = _asset(ctype="image/png", orig="photo.png")
    svc = _make_service(asset, capabilities=["inspect", "vision", "sandbox"])
    convo_id = str(uuid4())

    with (
        patch("app.services.asset.asset_service", svc),
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            AsyncMock(return_value=object()),
        ),
        patch(
            "app.services.asset_document.read_document",
            new=AsyncMock(side_effect=ValueError("unsupported_file_type")),
        ),
    ):
        result = await _execute_asset_tool(
            "read_asset",
            {"ref": "abcd"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
        )

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_read_asset_maps_document_service_errors():
    asset = _asset(ctype="image/png", orig="photo.png")
    svc = _make_service(asset, capabilities=["inspect", "vision", "sandbox"])
    convo_id = str(uuid4())

    with (
        patch("app.services.asset.asset_service", svc),
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            AsyncMock(return_value=object()),
        ),
        patch(
            "app.services.asset_document.read_document",
            new=AsyncMock(side_effect=ValueError("unsupported_file_type")),
        ),
    ):
        result = await _execute_asset_tool(
            "read_asset",
            {"ref": "abcd"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
        )

    data = json.loads(result)
    assert data["error"] == "Unsupported file type"


@pytest.mark.asyncio
async def test_asset_tool_rejects_non_string_ref():
    result = await _execute_asset_tool(
        "inspect_asset",
        {"ref": 123},
        agent=_agent(),
        user=_user(),
        conversation_id=str(uuid4()),
    )

    data = json.loads(result)
    assert data["error"] != ""


@pytest.mark.asyncio
async def test_asset_tool_missing_agent_or_user():
    convo_id = str(uuid4())
    result = await _execute_asset_tool(
        "inspect_asset",
        {"ref": "abcd"},
        agent=None,
        user=None,
        conversation_id=convo_id,
    )
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_asset_tool_invalid_conversation_id():
    result = await _execute_asset_tool(
        "inspect_asset",
        {"ref": "abcd"},
        agent=_agent(),
        user=_user(),
        conversation_id="not-a-uuid",
    )
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_asset_tool_no_conversation_id():
    result = await _execute_asset_tool(
        "inspect_asset",
        {"ref": "abcd"},
        agent=_agent(),
        user=_user(),
        conversation_id=None,
    )
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_read_asset_resolves_workflow_run_ref_without_user():
    from app.models.asset import AssetScopeType
    from app.models.workflow import Workflow, WorkflowRun

    team_id = uuid4()
    run_id = uuid4()
    workflow_id = uuid4()
    asset = _asset(ctype="text/plain", orig="report.txt")
    svc = _make_service(asset)
    run = SimpleNamespace(id=run_id, workflow_id=workflow_id)
    workflow = SimpleNamespace(id=workflow_id, team_id=team_id)

    document = {
        "asset_id": str(asset.id),
        "filename": "report.txt",
        "representation_id": "v1",
        "start_line": 1,
        "total_lines": 1,
        "segments": [{"line": 1, "text": "hello", "continuation": False}],
        "next_cursor": None,
        "eof": True,
    }

    with (
        patch.object(WorkflowRun, "get_or_none", AsyncMock(return_value=run)),
        patch.object(Workflow, "get_or_none", AsyncMock(return_value=workflow)),
        patch("app.services.asset.asset_service", svc),
        patch("app.api.v1.endpoints.upload.UPLOAD_ROOT", None),
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            AsyncMock(return_value=object()),
        ),
        patch(
            "app.services.asset_document.read_document",
            new=AsyncMock(return_value=document),
        ),
    ):
        result = await _execute_asset_tool(
            "read_asset",
            {"ref": "a1b2"},
            agent=_agent(team_id=team_id),
            user=None,
            conversation_id=None,
            workflow_run_id=run_id,
        )

    data = json.loads(result)
    assert data["segments"] == document["segments"]
    svc.resolve_ref.assert_awaited_once_with(
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=run_id,
        ref="a1b2",
        team_id=team_id,
        user_id=None,
    )


@pytest.mark.asyncio
async def test_materialize_asset_stages_file():
    asset = _asset(
        orig="report.xlsx",
        ctype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    svc = _make_service(asset, capabilities=["inspect", "sandbox"])
    convo_id = str(uuid4())
    fake_result = SimpleNamespace(success=True, error=None)

    with (
        patch("app.services.asset.asset_service", svc),
        patch(
            "app.services.sandbox.gateway.sandbox_gateway.submit_and_wait",
            new=AsyncMock(return_value=fake_result),
        ) as mock_submit,
    ):
        result = await _execute_asset_tool(
            "materialize_asset",
            {"ref": "abcd", "path": "/workspace/report.xlsx"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
            session_id="session-1",
        )

    data = json.loads(result)
    assert data["path"] == "/workspace/report.xlsx"
    assert data["filename"] == "report.xlsx"
    assert data["ref"] == "abcd"
    mock_submit.assert_awaited_once()
    job = mock_submit.call_args.args[0]
    assert job.input_files[0].asset_id == asset.id
    assert job.input_files[0].expected_checksum == asset.checksum
    assert job.input_files[0].expected_size == asset.size
    assert mock_submit.call_args.kwargs["session_id"] == "session-1"


@pytest.mark.asyncio
async def test_materialize_asset_missing_session_returns_error():
    asset = _asset()
    svc = _make_service(asset)
    convo_id = str(uuid4())

    with patch("app.services.asset.asset_service", svc):
        result = await _execute_asset_tool(
            "materialize_asset",
            {"ref": "abcd", "path": "/workspace/report.xlsx"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
            session_id=None,
        )

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_materialize_asset_missing_path_returns_error():
    asset = _asset()
    svc = _make_service(asset)
    convo_id = str(uuid4())

    with patch("app.services.asset.asset_service", svc):
        result = await _execute_asset_tool(
            "materialize_asset",
            {"ref": "abcd"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
            session_id="session-1",
        )

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_materialize_asset_rejects_path_escape():
    asset = _asset()
    svc = _make_service(asset)
    convo_id = str(uuid4())

    with patch("app.services.asset.asset_service", svc):
        result = await _execute_asset_tool(
            "materialize_asset",
            {"ref": "abcd", "path": "/etc/passwd"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
            session_id="session-1",
        )

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_materialize_asset_returns_error_on_sandbox_failure():
    asset = _asset(orig="report.xlsx")
    svc = _make_service(asset, capabilities=["inspect", "sandbox"])
    convo_id = str(uuid4())
    fake_result = SimpleNamespace(success=False, error="target already exists")

    with (
        patch("app.services.asset.asset_service", svc),
        patch(
            "app.services.sandbox.gateway.sandbox_gateway.submit_and_wait",
            new=AsyncMock(return_value=fake_result),
        ),
    ):
        result = await _execute_asset_tool(
            "materialize_asset",
            {"ref": "abcd", "path": "/workspace/report.xlsx"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
            session_id="session-1",
        )

    data = json.loads(result)
    assert data["error"] == "target already exists"
