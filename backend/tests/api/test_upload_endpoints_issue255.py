from io import BytesIO
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

# Importing app.services currently cycles through media_asset_service back to upload.
file_parser = ModuleType("app.services.file_parser")
file_parser.file_parser_service = SimpleNamespace(
    SUPPORTED_EXTENSIONS={".txt": "text/plain"}
)
file_parser.FileParseConfig = lambda **kwargs: SimpleNamespace(**kwargs)
services = ModuleType("app.services")
services.__path__ = [str(Path(__file__).parents[2] / "app" / "services")]
original_services = sys.modules.get("app.services")
original_file_parser = sys.modules.get("app.services.file_parser")
sys.modules["app.services"] = services
sys.modules["app.services.file_parser"] = file_parser
try:
    from app.api.v1.endpoints import upload  # noqa: E402
finally:
    if original_services is None:
        sys.modules.pop("app.services", None)
    else:
        sys.modules["app.services"] = original_services
    if original_file_parser is None:
        sys.modules.pop("app.services.file_parser", None)
    else:
        sys.modules["app.services.file_parser"] = original_file_parser

from app.schemas.response import BusinessError  # noqa: E402


def file(
    name: str | None, content: bytes = b"content", content_type: str = "text/plain"
):
    return UploadFile(
        BytesIO(content), filename=name, headers=Headers({"content-type": content_type})
    )


def request():
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


def parsed(name="notes.txt"):
    return SimpleNamespace(
        filename=name,
        content="parsed text",
        mime_type="text/plain",
        size=11,
        truncated=False,
        original_length=None,
        title=None,
    )


@pytest.mark.parametrize("value", ["", ".", "..", "a/b"])
def test_path_segments_reject_unsafe_values(value):
    with pytest.raises(BusinessError):
        upload._validate_path_segment(value, "category")


def test_extension_inference_uses_mime_filename_and_default(monkeypatch):
    assert upload.infer_extension("image/png", "ignored.txt") == ".png"
    assert upload.infer_extension(filename="REPORT.PDF") == ".pdf"
    assert upload.infer_extension() == ".bin"
    monkeypatch.setattr(
        upload.mimetypes, "guess_extension", lambda *_args, **_kwargs: ".odd"
    )
    assert upload.infer_extension("application/x-custom") == ".odd"


@pytest.mark.asyncio
async def test_upload_file_infers_supported_filename_type_and_audits(monkeypatch):
    saved = AsyncMock(
        return_value={
            "path": "documents/2026/07/saved.md",
            "url": "/api/v1/upload/files/documents/2026/07/saved.md",
            "filename": "saved.md",
            "size": 7,
            "content_type": "text/markdown",
        }
    )
    audit = AsyncMock()
    monkeypatch.setattr(
        upload.file_parser_service, "is_supported", lambda _: True, raising=False
    )
    monkeypatch.setattr(
        upload.file_parser_service,
        "get_mime_type",
        lambda _: "text/markdown",
        raising=False,
    )
    monkeypatch.setattr(upload, "save_generated_upload", saved)
    monkeypatch.setattr(upload.AuditLogService, "log", audit)

    response = await upload.upload_file(
        request(),
        file("notes.md", b"# hello", "application/octet-stream"),
        "documents",
        SimpleNamespace(id="user"),
    )

    assert response["data"]["content_type"] == "text/markdown"
    saved.assert_awaited_once()
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_image_rejects_type_and_size(monkeypatch):
    with pytest.raises(BusinessError):
        await upload.upload_image(
            request(), file("bad.txt"), "images", SimpleNamespace(id="user")
        )

    with pytest.raises(BusinessError):
        upload._validate_upload_size(b"xx", max_size=1)


@pytest.mark.asyncio
async def test_parse_file_success(monkeypatch):
    parse = AsyncMock(return_value=parsed())
    monkeypatch.setattr(
        upload.file_parser_service, "is_supported", lambda _: True, raising=False
    )
    monkeypatch.setattr(upload.file_parser_service, "parse_file", parse, raising=False)

    response = await upload.parse_file(
        file("notes.txt"), 1000, "middle", SimpleNamespace()
    )

    assert response["data"].content == "parsed text"
    assert parse.await_args.kwargs["config"].truncate_strategy == "middle"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("uploaded", "strategy", "supported"),
    [
        (file(None), "end", True),
        (file("bad.exe"), "end", False),
        (file("ok.txt"), "sideways", True),
    ],
)
async def test_parse_file_rejects_invalid_inputs(
    monkeypatch, uploaded, strategy, supported
):
    monkeypatch.setattr(
        upload.file_parser_service, "is_supported", lambda _: supported, raising=False
    )
    with pytest.raises(BusinessError):
        await upload.parse_file(uploaded, 1000, strategy, SimpleNamespace())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [ValueError("bad document"), RuntimeError("parser down")]
)
async def test_parse_file_translates_parser_errors(monkeypatch, error):
    monkeypatch.setattr(
        upload.file_parser_service, "is_supported", lambda _: True, raising=False
    )
    monkeypatch.setattr(
        upload.file_parser_service,
        "parse_file",
        AsyncMock(side_effect=error),
        raising=False,
    )

    with pytest.raises(BusinessError):
        await upload.parse_file(file("notes.txt"), 1000, "end", SimpleNamespace())


@pytest.mark.asyncio
async def test_batch_parse_keeps_successes_and_skips_failures(monkeypatch):
    parse = AsyncMock(side_effect=[parsed("good.txt"), RuntimeError("broken")])
    monkeypatch.setattr(
        upload.file_parser_service,
        "is_supported",
        lambda name: not name.endswith(".exe"),
        raising=False,
    )
    monkeypatch.setattr(upload.file_parser_service, "parse_file", parse, raising=False)
    monkeypatch.setattr(upload, "MAX_PARSE_FILE_SIZE", 3)

    response = await upload.parse_files_batch(
        [
            file(None),
            file("bad.exe"),
            file("large.txt", b"large"),
            file("good.txt", b"ok"),
            file("broken.txt", b"ok"),
        ],
        1000,
        "end",
        SimpleNamespace(),
    )

    assert [item.filename for item in response["data"]] == ["good.txt"]


@pytest.mark.asyncio
async def test_batch_parse_rejects_limits_and_all_failed(monkeypatch):
    with pytest.raises(BusinessError):
        await upload.parse_files_batch(
            [file(f"{index}.txt") for index in range(6)], 1000, "end", SimpleNamespace()
        )

    monkeypatch.setattr(
        upload.file_parser_service, "is_supported", lambda _: False, raising=False
    )
    with pytest.raises(BusinessError) as exc:
        await upload.parse_files_batch(
            [file("bad.exe")], 1000, "end", SimpleNamespace()
        )
    assert exc.value.data["errors"][0]["filename"] == "bad.exe"


@pytest.mark.asyncio
async def test_get_and_delete_file_use_storage_boundary(monkeypatch):
    storage = SimpleNamespace(
        exists=AsyncMock(return_value=True),
        response=AsyncMock(return_value="response"),
        delete=AsyncMock(),
    )
    audit = AsyncMock()
    monkeypatch.setattr(upload, "_upload_storage", AsyncMock(return_value=storage))
    monkeypatch.setattr(upload.AuditLogService, "log", audit)

    assert await upload.get_file("docs", "2026", "07", "notes.txt") == "response"
    result = await upload.delete_file(
        "docs", "2026", "07", "notes.txt", request(), SimpleNamespace(id="admin")
    )

    assert result["code"] == 0
    storage.delete.assert_awaited_once_with("docs/2026/07/notes.txt")
    audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_and_delete_missing_file(monkeypatch):
    storage = SimpleNamespace(exists=AsyncMock(return_value=False))
    monkeypatch.setattr(upload, "_upload_storage", AsyncMock(return_value=storage))

    with pytest.raises(BusinessError):
        await upload.get_file("docs", "2026", "07", "missing.txt")
    with pytest.raises(BusinessError):
        await upload.delete_file(
            "docs", "2026", "07", "missing.txt", request(), SimpleNamespace()
        )
