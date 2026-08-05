from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import app.services  # noqa: F401  # Complete package initialization before endpoint import.
from app.api.v1.endpoints import upload
from app.schemas.response import BusinessError, ResponseCode


def _file(
    content: bytes = b"ok",
    *,
    filename: str = "report.txt",
    content_type: str | None = "text/plain",
):
    return SimpleNamespace(
        filename=filename,
        content_type=content_type,
        read=AsyncMock(return_value=content),
    )


@pytest.mark.anyio
async def test_validate_upload_storage_config_uses_backend_and_propagates_errors():
    storage = SimpleNamespace(validate=AsyncMock())

    with patch.object(upload, "_upload_storage", AsyncMock(return_value=storage)):
        await upload.validate_upload_storage_config()

    storage.validate.assert_awaited_once_with()

    storage.validate.side_effect = RuntimeError("invalid storage settings")
    with (
        patch.object(upload, "_upload_storage", AsyncMock(return_value=storage)),
        pytest.raises(RuntimeError, match="invalid storage settings"),
    ):
        await upload.validate_upload_storage_config()


@pytest.mark.anyio
async def test_upload_image_rejects_invalid_type_before_reading_file():
    file = _file(content_type="application/zip")

    with pytest.raises(BusinessError) as exc_info:
        await upload.upload_image(SimpleNamespace(), file, "general", SimpleNamespace())

    assert exc_info.value.code == ResponseCode.VALIDATION_ERROR
    file.read.assert_not_awaited()


@pytest.mark.anyio
async def test_upload_file_rejects_unsupported_file():
    file = _file(filename="payload.exe", content_type="application/octet-stream")

    with (
        patch.object(
            upload.file_parser_service,
            "is_supported",
            create=True,
            return_value=False,
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await upload.upload_file(SimpleNamespace(), file, "general", SimpleNamespace())

    assert exc_info.value.code == ResponseCode.VALIDATION_ERROR
    file.read.assert_not_awaited()


@pytest.mark.anyio
async def test_upload_file_infers_type_saves_and_audits():
    storage = SimpleNamespace(save=AsyncMock(return_value="s3://uploads/docs/file.txt"))
    audit = AsyncMock()
    register = AsyncMock(return_value=SimpleNamespace(id="asset-1"))
    file = _file(content=b"document", content_type="application/octet-stream")
    user = SimpleNamespace(id="user-1")

    with (
        patch.object(upload, "_upload_storage", AsyncMock(return_value=storage)),
        patch.object(
            upload.file_parser_service,
            "is_supported",
            create=True,
            return_value=True,
        ),
        patch.object(
            upload.file_parser_service,
            "get_mime_type",
            create=True,
            return_value="text/plain",
        ),
        patch.object(upload.AuditLogService, "log", audit),
        patch.object(upload.asset_service, "register_bytes", register),
    ):
        result = await upload.upload_file(SimpleNamespace(), file, "docs", user)

    saved_key = storage.save.await_args.args[0]
    assert saved_key.startswith("docs/")
    assert saved_key.endswith(".txt")
    assert storage.save.await_args.args[1] == b"document"
    assert storage.save.await_args.kwargs == {"content_type": "text/plain"}
    assert result["data"]["content_type"] == "text/plain"
    assert result["data"]["size"] == 8
    audit.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("exists", [False, True])
async def test_get_file_handles_missing_and_download(exists: bool):
    response = SimpleNamespace(media_type="text/plain")
    storage = SimpleNamespace(
        exists=AsyncMock(return_value=exists),
        response=AsyncMock(return_value=response),
    )

    with patch.object(upload, "_upload_storage", AsyncMock(return_value=storage)):
        if not exists:
            with pytest.raises(BusinessError) as exc_info:
                await upload.get_file("docs", "2026", "07", "report.txt")
            assert exc_info.value.code == ResponseCode.NOT_FOUND
            storage.response.assert_not_awaited()
        else:
            assert await upload.get_file("docs", "2026", "07", "report.txt") is response
            storage.response.assert_awaited_once_with("docs/2026/07/report.txt")


@pytest.mark.anyio
async def test_get_file_rejects_path_traversal_before_storage_access():
    storage_factory = AsyncMock()

    with (
        patch.object(upload, "_upload_storage", storage_factory),
        pytest.raises(BusinessError) as exc_info,
    ):
        await upload.get_file("..", "2026", "07", "report.txt")

    assert exc_info.value.code == ResponseCode.VALIDATION_ERROR
    storage_factory.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("exists", [False, True])
async def test_delete_file_handles_missing_and_success(exists: bool):
    storage = SimpleNamespace(
        exists=AsyncMock(return_value=exists),
        delete=AsyncMock(),
    )
    audit = AsyncMock()
    user = SimpleNamespace(id="admin-1")

    with (
        patch.object(upload, "_upload_storage", AsyncMock(return_value=storage)),
        patch.object(upload.AuditLogService, "log", audit),
    ):
        if not exists:
            with pytest.raises(BusinessError) as exc_info:
                await upload.delete_file(
                    "docs", "2026", "07", "report.txt", SimpleNamespace(), user
                )
            assert exc_info.value.code == ResponseCode.NOT_FOUND
            storage.delete.assert_not_awaited()
            audit.assert_not_awaited()
        else:
            result = await upload.delete_file(
                "docs", "2026", "07", "report.txt", SimpleNamespace(), user
            )
            storage.delete.assert_awaited_once_with("docs/2026/07/report.txt")
            audit.assert_awaited_once()
            assert result["code"] == ResponseCode.SUCCESS
