from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.agent import ConversationSessionMemoryStatus, MessageRole
from app.services import session_memory
from app.services.session_memory import (
    _fit_summary_to_budget,
    _normalize_list,
    _parse_json_object,
    _render_transcript,
    _should_skip_already_extracted_snapshot,
)


class QueryResult:
    def __init__(self, value):
        self.value = value

    def prefetch_related(self, *args):
        return self

    async def first(self):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def test_extracted_ready_snapshot_skips_duplicate_extraction():
    source_id = uuid4()
    snapshot = SimpleNamespace(
        source_message_id=source_id,
        status=ConversationSessionMemoryStatus.READY,
        snapshot_payload={"overview": "ready"},
    )

    assert _should_skip_already_extracted_snapshot(snapshot, source_id) is True


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure", [TimeoutError(), RuntimeError("database unavailable")]
)
async def test_get_ready_session_memory_returns_none_on_query_failure(
    monkeypatch, failure
):
    monkeypatch.setattr(
        session_memory.ConversationSessionMemory,
        "filter",
        lambda **kwargs: QueryResult(failure),
    )

    assert await session_memory.get_ready_session_memory(uuid4()) is None


@pytest.mark.anyio
async def test_get_ready_session_memory_ignores_legacy_macro_snapshot(monkeypatch):
    snapshot = SimpleNamespace(
        status=ConversationSessionMemoryStatus.READY,
        snapshot_payload={"origin": "macro_compaction"},
    )
    monkeypatch.setattr(
        session_memory.ConversationSessionMemory,
        "filter",
        lambda **kwargs: QueryResult(snapshot),
    )

    assert await session_memory.get_ready_session_memory(uuid4()) is None


@pytest.mark.anyio
async def test_extract_session_memory_persists_normalized_snapshot(monkeypatch):
    conversation_id = uuid4()
    source_id = uuid4()
    agent_id = uuid4()
    created_at = datetime.now(UTC)
    conversation = SimpleNamespace(id=conversation_id, agent_id=agent_id)
    agent = SimpleNamespace(id=agent_id, team_id=uuid4(), model_id=None)
    source = SimpleNamespace(
        id=source_id,
        role=MessageRole.ASSISTANT,
        created_at=created_at,
        content="answer",
        tool_calls=None,
    )
    history = [
        SimpleNamespace(
            role=MessageRole.USER,
            created_at=created_at,
            content="question",
            tool_calls=None,
        ),
        source,
    ]
    snapshot = SimpleNamespace(
        source_message_id=None,
        status=ConversationSessionMemoryStatus.PENDING,
        snapshot_payload={},
        summary_text="",
        failure_count=0,
        save=AsyncMock(),
    )

    monkeypatch.setattr(
        session_memory.Conversation,
        "filter",
        lambda **kwargs: QueryResult(conversation),
    )
    monkeypatch.setattr(
        session_memory.Agent,
        "filter",
        lambda **kwargs: QueryResult(agent),
    )
    monkeypatch.setattr(
        session_memory.Message,
        "filter",
        lambda **kwargs: QueryResult(source),
    )
    monkeypatch.setattr(
        session_memory.ConversationSessionMemory,
        "filter",
        lambda **kwargs: QueryResult(None),
    )
    monkeypatch.setattr(
        session_memory.ConversationSessionMemory,
        "create",
        AsyncMock(return_value=snapshot),
    )
    monkeypatch.setattr(
        "app.services.chat_context.get_context_compression_config",
        lambda agent: {"session_memory_min_turns": 1, "session_memory_max_tokens": 50},
    )
    monkeypatch.setattr(
        session_memory,
        "is_message_on_active_branch",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        session_memory,
        "get_visible_conversation_messages",
        AsyncMock(return_value=history),
    )
    monkeypatch.setattr(
        session_memory.model_manager,
        "team_chat",
        AsyncMock(
            return_value=SimpleNamespace(
                content='```json\n{"overview":"  Keep   context ",'
                '"decisions":["Ship", "ship", ""]}\n```',
                model="test-model",
            )
        ),
    )
    monkeypatch.setattr(session_memory, "count_tokens", lambda *args, **kwargs: 7)

    result = await session_memory.extract_session_memory_for_message(
        conversation_id, source_id
    )

    assert result == {
        "status": "success",
        "conversation_id": str(conversation_id),
        "source_message_id": str(source_id),
        "token_estimate": 7,
    }
    assert snapshot.status == ConversationSessionMemoryStatus.READY
    assert snapshot.snapshot_payload["overview"] == "Keep context"
    assert snapshot.snapshot_payload["decisions"] == ["Ship"]
    assert snapshot.failure_count == 0
    snapshot.save.assert_awaited_once_with()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("existing_summary", "expected_status"),
    [
        ("", ConversationSessionMemoryStatus.FAILED),
        ("previous summary", ConversationSessionMemoryStatus.STALE),
    ],
)
async def test_extract_session_memory_records_model_failure(
    monkeypatch, existing_summary, expected_status
):
    conversation_id = uuid4()
    source_id = uuid4()
    created_at = datetime.now(UTC)
    conversation = SimpleNamespace(agent_id=uuid4())
    agent = SimpleNamespace(team_id=uuid4(), model_id=None)
    source = SimpleNamespace(
        role=MessageRole.ASSISTANT,
        created_at=created_at,
        content="answer",
        tool_calls=None,
    )
    snapshot = SimpleNamespace(
        source_message_id=None,
        status=ConversationSessionMemoryStatus.PENDING,
        snapshot_payload={},
        summary_text=existing_summary,
        failure_count=None,
        save=AsyncMock(),
    )

    monkeypatch.setattr(
        session_memory.Conversation,
        "filter",
        lambda **kwargs: QueryResult(conversation),
    )
    monkeypatch.setattr(
        session_memory.Agent,
        "filter",
        lambda **kwargs: QueryResult(agent),
    )
    monkeypatch.setattr(
        session_memory.Message,
        "filter",
        lambda **kwargs: QueryResult(source),
    )
    monkeypatch.setattr(
        session_memory.ConversationSessionMemory,
        "filter",
        lambda **kwargs: QueryResult(snapshot),
    )
    monkeypatch.setattr(
        "app.services.chat_context.get_context_compression_config",
        lambda agent: {"session_memory_min_turns": 1},
    )
    monkeypatch.setattr(
        session_memory,
        "is_message_on_active_branch",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        session_memory,
        "get_visible_conversation_messages",
        AsyncMock(return_value=[source]),
    )
    monkeypatch.setattr(
        session_memory.model_manager,
        "team_chat",
        AsyncMock(side_effect=RuntimeError("provider failed")),
    )
    monkeypatch.setattr(session_memory, "t", lambda key: "localized failure")

    result = await session_memory.extract_session_memory_for_message(
        conversation_id, source_id
    )

    assert result["status"] == "error"
    assert result["error"] == "localized failure"
    assert snapshot.status == expected_status
    assert snapshot.failure_count == 1
    assert snapshot.last_error == "provider failed"
    snapshot.save.assert_awaited_once()


def test_payload_helpers_cover_fences_deduplication_and_invalid_shape():
    assert _parse_json_object('```json\n{"overview": "ready"}\n```') == {
        "overview": "ready"
    }
    with pytest.raises(ValueError, match="JSON object"):
        _parse_json_object("[]")

    assert _normalize_list([" Same  item ", "same item", 4, "other"]) == [
        "Same item",
        "other",
    ]


def test_transcript_and_budget_helpers_cover_tool_and_truncation(monkeypatch):
    monkeypatch.setattr(
        "app.services.chat_context.summarize_tool_result_for_llm",
        lambda name, content: f"summary:{name}:{content}",
    )
    transcript = _render_transcript(
        [
            [
                SimpleNamespace(
                    role=MessageRole.ASSISTANT,
                    content="calling",
                    tool_calls=[{"name": "search"}, {}, "invalid"],
                ),
                SimpleNamespace(
                    role=MessageRole.TOOL,
                    content="result",
                    tool_name="search",
                    tool_calls=None,
                ),
            ]
        ]
    )

    assert "ASSISTANT_TOOL_CALLS: search" in transcript
    assert "TOOL: summary:search:result" in transcript

    monkeypatch.setattr(
        session_memory,
        "count_tokens",
        lambda text, **kwargs: len(text),
    )
    fitted = _fit_summary_to_budget(
        "x" * 500,
        max_tokens=20,
        model_id="test",
        provider=None,
    )
    assert len(fitted) <= 20
