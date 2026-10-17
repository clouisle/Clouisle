from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.schemas.response import BusinessError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler,extra",
    [
        (knowledge_bases.update_document, {"doc_in": None}),
        (knowledge_bases.delete_document, {}),
        (knowledge_bases.process_document, {}),
        (knowledge_bases.process_document_with_chunks, {"process_request": None}),
        (knowledge_bases.reprocess_document, {}),
        (knowledge_bases.retry_failed_chunks, {}),
        (knowledge_bases.retry_failed_chunk, {"chunk_id": uuid4()}),
        (
            knowledge_bases.update_document_chunk,
            {"chunk_id": uuid4(), "chunk_in": None},
        ),
        (knowledge_bases.delete_document_chunk, {"chunk_id": uuid4()}),
        (knowledge_bases.create_document_chunk, {"chunk_in": None}),
        (knowledge_bases.rechunk_document, {"rechunk_in": None}),
    ],
)
async def test_source_managed_documents_reject_local_mutations(
    monkeypatch, handler, extra
):
    doc = SimpleNamespace(metadata={"feishu_read_only": True})
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock())
    monkeypatch.setattr(
        knowledge_bases.Document,
        "filter",
        lambda **kwargs: SimpleNamespace(first=AsyncMock(return_value=doc)),
    )
    with pytest.raises(BusinessError) as error:
        await handler(
            kb_id=uuid4(),
            doc_id=uuid4(),
            request=SimpleNamespace(),
            current_user=SimpleNamespace(),
            **extra,
        )
    assert error.value.status_code == 403
    assert error.value.msg_key == "feishu_document_source_managed"


@pytest.mark.asyncio
async def test_sync_target_requires_source_removal_before_kb_deletion(monkeypatch):
    kb = SimpleNamespace(id=uuid4(), delete=AsyncMock())
    monkeypatch.setattr(knowledge_bases, "check_kb_access", AsyncMock(return_value=kb))
    monkeypatch.setattr(
        knowledge_bases.FeishuKnowledgeSource,
        "filter",
        lambda **kwargs: SimpleNamespace(exists=AsyncMock(return_value=True)),
    )
    with pytest.raises(BusinessError) as error:
        await knowledge_bases.delete_knowledge_base(
            kb.id,
            SimpleNamespace(),
            SimpleNamespace(),
        )
    assert error.value.msg_key == "feishu_kb_has_sync_sources"
    kb.delete.assert_not_awaited()
