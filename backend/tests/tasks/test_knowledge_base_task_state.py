from types import SimpleNamespace
from uuid import UUID

import pytest

from app.models.knowledge_base import DocumentStatus
from app.tasks.knowledge_base import (
    _clear_task_metadata,
    _finish_already_finished_task,
    _finish_stale_task,
    _is_finished_task,
    _is_stale_task,
)


@pytest.mark.parametrize(
    ("metadata", "task_id", "expected"),
    [
        ({"task_id": "current"}, "current", False),
        ({"task_id": "other"}, "current", True),
        ({}, "current", False),
        ({"task_id": "current"}, None, False),
    ],
)
def test_is_stale_task_only_skips_different_active_task(metadata, task_id, expected):
    document = SimpleNamespace(metadata=metadata)

    assert _is_stale_task(document, task_id) is expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (DocumentStatus.COMPLETED.value, True),
        (DocumentStatus.ERROR.value, True),
        (DocumentStatus.PROCESSING.value, False),
    ],
)
def test_is_finished_task_only_skips_terminal_matching_task(status, expected):
    document = SimpleNamespace(metadata={"task_id": "current"}, status=status)

    assert _is_finished_task(document, "current") is expected


def test_clear_task_metadata_preserves_unrelated_metadata():
    document = SimpleNamespace(
        metadata={
            "task_id": "current",
            "embed_progress": {"embedded": 1},
            "task_name": "embed",
            "task_args": ["document-id"],
        }
    )

    _clear_task_metadata(document)

    assert document.metadata == {"task_id": "current"}


@pytest.mark.asyncio
async def test_task_skip_results_identify_document_and_terminal_status():
    document = SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        status=DocumentStatus.ERROR.value,
    )

    assert await _finish_stale_task(document, "stale") == {
        "status": "stale",
        "document_id": "00000000-0000-0000-0000-000000000001",
    }
    assert await _finish_already_finished_task(document, "current") == {
        "status": "already_finished",
        "document_id": "00000000-0000-0000-0000-000000000001",
        "document_status": DocumentStatus.ERROR.value,
    }
