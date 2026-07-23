from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from app.models.knowledge_base import DocumentType
from app.services import upload_storage
from app.services.document_processor import DocumentProcessor


def test_storage_key_rejects_malformed_s3_paths(tmp_path: Path):
    processor = DocumentProcessor(upload_dir=str(tmp_path / "uploads" / "documents"))

    for path in ("s3://bucket", "s3://bucket/", "s3:///key"):
        with pytest.raises(ValueError, match="validation_error"):
            processor._storage_key(path)


@pytest.mark.anyio
async def test_document_processor_uses_object_upload_backend(
    monkeypatch, tmp_path: Path
):
    calls: list[tuple[str, dict]] = []

    class FakeBody:
        async def read(self, size=-1):
            return b"# Title"

    class FakeClient:
        async def put_object(self, **kwargs):
            calls.append(("put_object", kwargs))

        async def get_object(self, **kwargs):
            calls.append(("get_object", kwargs))
            return {"Body": FakeBody(), "ContentType": "text/markdown"}

    class FakeClientContext:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeSession:
        def create_client(self, *args, **kwargs):
            return FakeClientContext()

    monkeypatch.setattr(upload_storage, "get_session", lambda: FakeSession())
    processor = DocumentProcessor(upload_dir=str(tmp_path / "uploads" / "documents"))
    kb_id = uuid4()
    storage_key = processor.get_storage_path(kb_id, "sample.md")

    with patch.object(
        upload_storage.SiteSetting,
        "get_all_by_category",
        return_value={
            "upload_storage_backend": "object",
            "object_storage_endpoint": "minio:9000",
            "object_storage_bucket": "uploads",
            "object_storage_access_key": "access",
            "object_storage_secret_key": "secret",
            "object_storage_secure": False,
            "object_storage_force_path_style": True,
        },
    ):
        size = await processor.save_file(b"# Title", storage_key)
        content = await processor.read_file(storage_key)
        text, metadata = await processor.extract_text(
            storage_key, DocumentType.MD.value
        )

    assert size == len(b"# Title")
    assert content == b"# Title"
    assert text == "# Title"
    assert metadata["file_size"] == len(b"# Title")
    assert storage_key.startswith(f"documents/{kb_id}/")
    assert (
        "put_object",
        {
            "Bucket": "uploads",
            "Key": storage_key,
            "Body": b"# Title",
        },
    ) in calls
    assert (
        "get_object",
        {
            "Bucket": "uploads",
            "Key": storage_key,
        },
    ) in calls


@pytest.mark.anyio
async def test_get_upload_storage_backend_merges_storage_defaults(tmp_path: Path):
    with patch.object(
        upload_storage.SiteSetting,
        "get_all_by_category",
        return_value={"upload_storage_backend": "object"},
    ):
        with pytest.raises(RuntimeError, match="object_storage_endpoint"):
            await upload_storage.get_upload_storage_backend(tmp_path)


@pytest.mark.anyio
async def test_storage_methods_delegate_to_backend(tmp_path: Path):
    processor = DocumentProcessor(upload_dir=str(tmp_path / "uploads" / "documents"))
    storage = AsyncMock()
    storage.read.return_value = b"stored"
    storage.exists.side_effect = [True, False]

    with patch(
        "app.services.document_processor.get_upload_storage_backend",
        AsyncMock(return_value=storage),
    ):
        assert await processor.save_file(b"content", "documents/file.txt") == 7
        assert await processor.read_file("documents/file.txt") == b"stored"
        assert await processor.delete_file("documents/file.txt") is True
        assert await processor.delete_file("documents/missing.txt") is False

    storage.save.assert_awaited_once_with("documents/file.txt", b"content")
    storage.delete.assert_awaited_once_with("documents/file.txt")


@pytest.mark.anyio
async def test_extract_text_wraps_parser_errors(tmp_path: Path):
    processor = DocumentProcessor(upload_dir=str(tmp_path / "uploads" / "documents"))

    with (
        patch.object(processor, "read_file", AsyncMock(return_value=b"not-json")),
        pytest.raises(ValueError, match="document_processing_failed_generic"),
    ):
        await processor.extract_text("documents/bad.json", DocumentType.JSON.value)


@pytest.mark.anyio
async def test_extract_text_uses_document_parser_and_cleans_output(tmp_path: Path):
    processor = DocumentProcessor(upload_dir=str(tmp_path / "uploads" / "documents"))
    parser = Mock(
        return_value=(
            "  title\r\n\r\nbody\x00  ",
            {"format": "markdown", "title": "Parsed"},
        )
    )

    with (
        patch.object(processor, "read_file", AsyncMock(return_value=b"pdf")),
        patch.object(processor, "_extract_with_markitdown", parser),
    ):
        text, metadata = await processor.extract_text(
            "documents/sample.pdf", DocumentType.PDF.value
        )

    assert text == "title\nbody"
    assert metadata == {
        "file_size": 3,
        "doc_type": DocumentType.PDF.value,
        "format": "markdown",
        "title": "Parsed",
        "char_count": 10,
    }
    parser.assert_called_once()
