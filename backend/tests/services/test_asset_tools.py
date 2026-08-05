"""Unit tests for inspect_asset / read_asset / parse_asset tools."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints.chat_tools import _execute_asset_tool
from app.schemas.response import BusinessError


def _agent(team_id=None):
    return SimpleNamespace(id=uuid4(), team_id=team_id, max_file_size=None)


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


@pytest.mark.anyio
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


@pytest.mark.anyio
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


@pytest.mark.anyio
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


@pytest.mark.anyio
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


@pytest.mark.anyio
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


@pytest.mark.anyio
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

    with (
        patch("app.services.asset.asset_service", svc),
        patch(
            "app.services.upload_storage.get_upload_storage_backend",
            AsyncMock(return_value=object()),
        ),
        patch(
            "app.services.file_parser.file_parser_service.parse_file",
            AsyncMock(return_value=fake_parsed),
        ),
    ):
        result = await _execute_asset_tool(
            "parse_asset",
            {"ref": "abcd"},
            agent=_agent(),
            user=_user(),
            conversation_id=convo_id,
        )

    data = json.loads(result)
    assert data["content"] == "parsed content"
    assert "truncated" in data


@pytest.mark.anyio
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


@pytest.mark.anyio
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


@pytest.mark.anyio
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


@pytest.mark.anyio
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
