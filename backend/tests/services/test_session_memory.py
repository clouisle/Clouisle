from types import SimpleNamespace
from uuid import uuid4

from app.models.agent import ConversationSessionMemoryStatus
from app.services.session_memory import (
    MACRO_COMPACTION_ORIGIN,
    _should_skip_already_extracted_snapshot,
)


def test_macro_compaction_snapshot_does_not_skip_extractor_refresh():
    source_id = uuid4()
    snapshot = SimpleNamespace(
        source_message_id=source_id,
        status=ConversationSessionMemoryStatus.READY,
        snapshot_payload={"origin": MACRO_COMPACTION_ORIGIN},
    )

    assert _should_skip_already_extracted_snapshot(snapshot, source_id) is False


def test_extracted_ready_snapshot_skips_duplicate_extraction():
    source_id = uuid4()
    snapshot = SimpleNamespace(
        source_message_id=source_id,
        status=ConversationSessionMemoryStatus.READY,
        snapshot_payload={"overview": "ready"},
    )

    assert _should_skip_already_extracted_snapshot(snapshot, source_id) is True
