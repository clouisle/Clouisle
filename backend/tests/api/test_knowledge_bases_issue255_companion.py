from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import knowledge_bases
from app.models import (
    KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
    KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB,
    KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB,
)


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("bad", KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB),
        (KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB - 1, KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB),
        (KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB + 1, KB_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB),
        (
            KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB + 1,
            KB_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB + 1,
        ),
    ],
)
@pytest.mark.anyio
async def test_upload_size_setting_is_defaulted_clamped_or_returned(
    monkeypatch, stored, expected
):
    async def fake_get_value(key, default):
        assert key == "kb_document_max_upload_size_mb"
        assert default == KB_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB
        return stored

    monkeypatch.setattr(knowledge_bases.SiteSetting, "get_value", fake_get_value)

    assert await knowledge_bases.get_kb_document_max_upload_size_mb() == expected


@pytest.mark.anyio
async def test_dispatch_document_task_records_task_metadata_then_dispatches():
    saves = []
    doc = SimpleNamespace(metadata=None)

    async def save(*args, **kwargs):
        saves.append((args, kwargs, dict(doc.metadata)))

    doc.save = save
    task = SimpleNamespace(
        name="process_document_task", apply_async=lambda **kwargs: saves.append(kwargs)
    )

    task_id = await knowledge_bases._dispatch_document_task(doc, task, "doc-1")

    assert doc.metadata == {
        "task_id": task_id,
        "task_name": "process_document_task",
        "task_args": ["doc-1"],
    }
    assert saves[0][2] == doc.metadata
    assert saves[1] == {"args": ("doc-1",), "task_id": task_id}


@pytest.mark.anyio
async def test_dispatch_document_task_rolls_back_metadata_when_dispatch_fails():
    saves = []
    doc = SimpleNamespace(metadata={"kept": "value"})

    async def save(*args, **kwargs):
        saves.append((args, kwargs, dict(doc.metadata)))

    def fail_dispatch(**kwargs):
        raise RuntimeError("worker unavailable")

    doc.save = save
    task = SimpleNamespace(name="process_document_task", apply_async=fail_dispatch)

    with pytest.raises(RuntimeError, match="worker unavailable"):
        await knowledge_bases._dispatch_document_task(doc, task, "doc-1")

    assert doc.metadata == {"kept": "value"}
    assert saves[-1][1] == {"update_fields": ["metadata"]}
