from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.services.vector_store import VectorStore

vector_store_module = pytest.importorskip("app.services.vector_store")


class FakeDocumentChunk:
    created = []

    def __init__(self, **kwargs):
        self.id = uuid4()
        self.save = AsyncMock()
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    async def create(cls, **kwargs):
        chunk = cls(**kwargs)
        cls.created.append(chunk)
        return chunk


@pytest.fixture(autouse=True)
def fake_document_chunk(monkeypatch):
    FakeDocumentChunk.created = []
    monkeypatch.setattr(vector_store_module, "DocumentChunk", FakeDocumentChunk)


@pytest.fixture
def document():
    return SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000010"),
        knowledge_base_id=UUID("00000000-0000-0000-0000-000000000001"),
    )


@pytest.mark.asyncio
async def test_store_chunks_with_progress_returns_empty_without_work(document):
    calls = []

    result = await VectorStore().store_chunks_with_progress(
        document,
        [],
        progress_callback=lambda *args: calls.append(args),
    )

    assert result == []
    assert calls == []
    assert FakeDocumentChunk.created == []


@pytest.mark.asyncio
async def test_store_chunks_with_progress_embeds_each_chunk(monkeypatch, document):
    progress = []
    payloads = []
    ensured = []

    async def fake_embed_texts(self, texts):
        return [[float(len(texts[0])), 0.2]]

    async def fake_ensure_kb_dimension(kb_id, dimension):
        ensured.append((kb_id, dimension))

    async def fake_store_embedding(
        self, chunk_id, embedding, dimension=None, payload=None
    ):
        payloads.append((chunk_id, embedding, dimension, payload))

    async def fake_progress(embedded, failed, total):
        progress.append((embedded, failed, total))

    monkeypatch.setattr(VectorStore, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(VectorStore, "_store_embedding", fake_store_embedding)
    monkeypatch.setattr(
        vector_store_module, "_ensure_kb_dimension", fake_ensure_kb_dimension
    )

    chunks = [
        {"content": "alpha", "chunk_index": 0, "token_count": 2, "metadata": {"p": 1}},
        {"content": "beta", "chunk_index": 1},
    ]

    result = await VectorStore().store_chunks_with_progress(
        document,
        chunks,
        progress_callback=fake_progress,
    )

    assert result == FakeDocumentChunk.created
    assert [chunk.status for chunk in result] == ["embedded", "embedded"]
    assert [chunk.error_message for chunk in result] == [None, None]
    assert progress == [(1, 0, 2), (2, 0, 2)]
    assert ensured == [(document.knowledge_base_id, 2)]
    assert [call[1] for call in payloads] == [[5.0, 0.2], [4.0, 0.2]]
    assert [call[3] for call in payloads] == [
        {
            "kb_id": "00000000-0000-0000-0000-000000000001",
            "document_id": "00000000-0000-0000-0000-000000000010",
        },
        {
            "kb_id": "00000000-0000-0000-0000-000000000001",
            "document_id": "00000000-0000-0000-0000-000000000010",
        },
    ]
    for chunk in result:
        chunk.save.assert_awaited_once_with(update_fields=["status", "error_message"])


@pytest.mark.asyncio
async def test_store_chunks_with_progress_marks_failed_chunk(monkeypatch, document):
    progress = []

    async def fake_embed_texts(self, texts):
        if texts == ["bad"]:
            raise RuntimeError("embedding failed")
        return [[0.1, 0.2, 0.3]]

    async def fake_ensure_kb_dimension(kb_id, dimension):
        assert kb_id == document.knowledge_base_id
        assert dimension == 3

    async def fake_store_embedding(
        self, chunk_id, embedding, dimension=None, payload=None
    ):
        assert embedding == [0.1, 0.2, 0.3]
        assert dimension == 3

    async def fake_progress(embedded, failed, total):
        progress.append((embedded, failed, total))

    monkeypatch.setattr(VectorStore, "embed_texts", fake_embed_texts)
    monkeypatch.setattr(VectorStore, "_store_embedding", fake_store_embedding)
    monkeypatch.setattr(
        vector_store_module, "_ensure_kb_dimension", fake_ensure_kb_dimension
    )

    result = await VectorStore().store_chunks_with_progress(
        document,
        [
            {"content": "bad", "chunk_index": 0},
            {"content": "good", "chunk_index": 1},
        ],
        progress_callback=fake_progress,
    )

    assert [chunk.status for chunk in result] == ["failed", "embedded"]
    assert result[0].error_message == "document_process_failed"
    assert result[1].error_message is None
    assert progress == [(0, 1, 2), (1, 1, 2)]
