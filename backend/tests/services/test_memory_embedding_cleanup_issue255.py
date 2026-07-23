from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm import model_manager
from app.services import memory


class Model:
    def __init__(self, **values):
        self.__dict__.update(values)


@pytest.fixture(autouse=True)
def qdrant_models(monkeypatch):
    monkeypatch.setattr(memory, "qmodels", SimpleNamespace(PointIdsList=Model))


@pytest.mark.asyncio
async def test_delete_entity_embedding_skips_missing_model(monkeypatch):
    get_client = AsyncMock()
    monkeypatch.setattr(memory, "_get_qdrant_client", get_client)

    await memory.MemoryService._delete_entity_embedding("embedding-1", None)

    get_client.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_entity_embedding_uses_default_dimension(monkeypatch):
    client = SimpleNamespace(delete=AsyncMock())
    monkeypatch.setattr(memory, "_get_qdrant_client", AsyncMock(return_value=client))
    monkeypatch.setattr(
        model_manager,
        "_get_model_config",
        AsyncMock(return_value=SimpleNamespace(dimensions=None)),
    )

    await memory.MemoryService._delete_entity_embedding("embedding-1", "model-1")

    client.delete.assert_awaited_once()
    assert (
        client.delete.await_args.kwargs["collection_name"] == "memory_entities_dim_1536"
    )
    assert client.delete.await_args.kwargs["points_selector"].points == ["embedding-1"]


@pytest.mark.asyncio
async def test_delete_entity_embedding_swallows_provider_failure(monkeypatch, caplog):
    monkeypatch.setattr(
        model_manager,
        "_get_model_config",
        AsyncMock(side_effect=RuntimeError("provider down")),
    )

    await memory.MemoryService._delete_entity_embedding("embedding-1", "model-1")

    assert "Failed to delete embedding embedding-1" in caplog.text
