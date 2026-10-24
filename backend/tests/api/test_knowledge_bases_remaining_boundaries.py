from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import knowledge_bases as endpoint
from app.models.knowledge_base import DocumentStatus


@pytest.mark.asyncio
async def test_failed_dispatch_does_not_rollback_a_newer_task_reservation(monkeypatch):
    connection = object()

    class Transaction:
        async def __aenter__(self):
            return connection

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(endpoint, "in_transaction", Transaction)
    doc = SimpleNamespace(
        id=uuid4(),
        status=DocumentStatus.PENDING.value,
        error_message="previous error",
        metadata={"task_id": "previous-task", "source": "upload"},
        save=AsyncMock(),
    )
    locked_doc = SimpleNamespace(
        id=doc.id,
        status=DocumentStatus.PENDING.value,
        error_message="previous error",
        metadata={"task_id": "previous-task", "source": "upload"},
        save=AsyncMock(),
    )

    class Query:
        def using_db(self, _connection):
            return self

        def select_for_update(self):
            return self

        async def get(self):
            return locked_doc

    monkeypatch.setattr(endpoint.Document, "filter", lambda **_kwargs: Query())

    class Task:
        name = "process_document"

        def apply_async(self, **_kwargs):
            # A concurrent request replaced this reservation after our publish
            # transaction committed but before the broker error was handled.
            locked_doc.metadata = {"task_id": "newer-task", "source": "upload"}
            locked_doc.status = DocumentStatus.PROCESSING.value
            locked_doc.error_message = None
            raise RuntimeError("broker unavailable")

    with pytest.raises(RuntimeError, match="broker unavailable"):
        await endpoint._dispatch_document_task(
            doc,
            Task(),
            str(doc.id),
            status=DocumentStatus.PROCESSING.value,
        )

    # The failed dispatch may only undo its own reservation; it must not erase
    # the newer task metadata written by another request.
    assert locked_doc.metadata == {"task_id": "newer-task", "source": "upload"}
    assert locked_doc.status == DocumentStatus.PROCESSING.value
    assert locked_doc.error_message is None
    assert locked_doc.save.await_count == 1
    assert locked_doc.save.await_args.kwargs == {
        "using_db": connection,
        "update_fields": ["metadata", "status", "error_message"],
    }
