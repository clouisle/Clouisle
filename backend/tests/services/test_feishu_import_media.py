from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.services import feishu_knowledge as service


@pytest.mark.asyncio
async def test_updated_import_media_urls_follow_stable_document_and_keep_stage_storage(
    monkeypatch,
):
    stage_id, final_id = uuid4(), uuid4()
    original_url = f"/api/v1/knowledge-bases/kb/documents/{stage_id}/media/image.png"
    stage = SimpleNamespace(
        id=stage_id,
        metadata={
            "media_assets": [
                {
                    "url": original_url,
                    "path": f"documents/kb/media/{stage_id}/image.png",
                }
            ]
        },
    )
    chunk = SimpleNamespace(
        content=f"![Figure]({original_url})",
        metadata={"source": original_url},
        save=AsyncMock(),
    )

    async def chunks():
        return [chunk]

    monkeypatch.setattr(
        service.DocumentChunk, "filter", Mock(side_effect=lambda **_: chunks())
    )
    await service._promote_media(stage, final_id)
    final_url = original_url.replace(str(stage_id), str(final_id))
    assert chunk.content == f"![Figure]({final_url})"
    assert chunk.metadata["source"] == final_url
    assert stage.metadata["media_assets"][0]["url"] == final_url
    assert (
        stage.metadata["media_assets"][0]["path"]
        == f"documents/kb/media/{stage_id}/image.png"
    )
    assert stage.metadata["feishu_media_document_id"] == str(stage_id)


@pytest.mark.asyncio
async def test_failed_stage_cleanup_removes_stage_media_not_stable_document_media(
    monkeypatch,
):
    kb_id, stage_id = uuid4(), uuid4()
    path = f"documents/{kb_id}/2026/10/abcd1234_{stage_id}.docx"
    removed = []

    async def remove_media(kb, doc):
        removed.append((kb, doc))

    monkeypatch.setattr(service.document_processor, "delete_media_assets", remove_media)
    monkeypatch.setattr(service.document_processor, "delete_file", AsyncMock())
    await service._delete_import_file(kb_id, path)
    assert removed == [(kb_id, stage_id)]
