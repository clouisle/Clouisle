"""Unit tests for inspect_asset / read_asset / parse_asset tools."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_tools import _execute_asset_tool
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
        return_value=capabilities or ["inspect", "read", "parse", "sandbox"]
    )
    svc.read = AsyncMock(return_value=b"hello")
    return svc


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
async def test_read_asset_returns_text():
    asset = _asset(ctype="text/plain", orig="readme.txt")
    svc = _make_service(asset, capabilities=["inspect", "read", "sandbox"])
    svc.read = AsyncMock(return_value=b"hello world")
    convo_id = str(uuid4())

    with (
        patch("app.services.asset.asset_service", svc),
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            AsyncMock(return_value=object()),
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
    assert data["content"] == "hello world"
    assert data["ref"] == "abcd"


@pytest.mark.asyncio
async def test_read_asset_refuses_binary():
    asset = _asset(ctype="image/png", orig="photo.png")
    svc = _make_service(asset, capabilities=["inspect", "vision", "sandbox"])
    convo_id = str(uuid4())

    with patch("app.services.asset.asset_service", svc):
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
async def test_parse_asset_returns_parsed_content():
    from app.services.file_parser import ParsedFile

    asset = _asset(ctype="text/plain", orig="doc.txt")
    svc = _make_service(asset)
    svc.read = AsyncMock(return_value=b"raw bytes")
    convo_id = str(uuid4())

    fake_parsed = ParsedFile(
        filename="doc.txt",
        content="parsed content",
        mime_type="text/plain",
        size=14,
    )

    parse_file = AsyncMock(return_value=fake_parsed)
    with (
        patch("app.services.asset.asset_service", svc),
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            AsyncMock(return_value=object()),
        ),
        patch("app.services.file_parser.file_parser_service.parse_file", parse_file),
    ):
        result = await _execute_asset_tool(
            "parse_asset",
            {"ref": "abcd"},
            agent=_agent(
                attachment_config={
                    "max_file_size": 10 * 1024 * 1024,
                    "max_content_length": 1234,
                    "truncate_strategy": "middle",
                }
            ),
            user=_user(),
            conversation_id=convo_id,
        )

    data = json.loads(result)
    assert data["content"] == "parsed content"
    assert "truncated" in data
    parse_config = parse_file.await_args.args[2]
    assert parse_config.max_content_length == 1234
    assert parse_config.truncate_strategy == "middle"


@pytest.mark.asyncio
async def test_parse_asset_refuses_unsupported():
    asset = _asset(ctype="image/png", orig="photo.png")
    svc = _make_service(asset, capabilities=["inspect", "vision", "sandbox"])
    convo_id = str(uuid4())

    with patch("app.services.asset.asset_service", svc):
        result = await _execute_asset_tool(
            "parse_asset",
            {"ref": "abcd"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
        )

    data = json.loads(result)
    assert "error" in data


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
