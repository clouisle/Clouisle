import asyncio
import importlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.agent import ConversationSessionMemoryStatus, MessageRole

session_memory = importlib.import_module("app.services.session_memory")


class Query:
    def __init__(self, result):
        self.result = result

    def prefetch_related(self, *args):
        return self

    async def first(self):
        return self.result


def message(role=MessageRole.ASSISTANT, **overrides):
    values = {
        "id": uuid4(),
        "role": role,
        "content": "content",
        "created_at": datetime.now(UTC),
        "tool_calls": None,
        "tool_name": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.anyio
async def test_get_ready_session_memory_handles_success_timeout_and_error(monkeypatch):
    snapshot = object()
    monkeypatch.setattr(
        session_memory.ConversationSessionMemory,
        "filter",
        MagicMock(return_value=Query(snapshot)),
    )
    assert await session_memory.get_ready_session_memory(uuid4()) is snapshot

    wait_for = AsyncMock(
        side_effect=[asyncio.TimeoutError, RuntimeError("database unavailable")]
    )
    monkeypatch.setattr(asyncio, "wait_for", wait_for)
    assert await session_memory.get_ready_session_memory(uuid4()) is None
    assert await session_memory.get_ready_session_memory(uuid4()) is None
    for call in wait_for.await_args_list:
        call.args[0].close()


@pytest.mark.anyio
async def test_extraction_skips_missing_conversation_agent_and_disabled_modes(
    monkeypatch,
):
    conversation_id = uuid4()
    source_id = uuid4()
    agent_id = uuid4()
    conversation = SimpleNamespace(agent_id=agent_id)
    agent = SimpleNamespace()

    monkeypatch.setattr(
        session_memory.Conversation,
        "filter",
        MagicMock(
            side_effect=[
                Query(None),
                Query(SimpleNamespace(agent_id=None)),
                Query(conversation),
                Query(conversation),
                Query(conversation),
            ]
        ),
    )
    monkeypatch.setattr(
        session_memory.Agent,
        "filter",
        MagicMock(side_effect=[Query(None), Query(agent), Query(agent)]),
    )
    from app.services import chat_context

    config = MagicMock(
        side_effect=[
            {"session_memory_enabled": False},
            {"session_memory_enabled": True, "session_memory_async_extract": False},
        ]
    )
    monkeypatch.setattr(chat_context, "get_context_compression_config", config)

    assert (
        await session_memory.extract_session_memory_for_message(
            conversation_id, source_id
        )
    )["reason"] == "conversation_not_found"
    assert (
        await session_memory.extract_session_memory_for_message(
            conversation_id, source_id
        )
    )["reason"] == "conversation_not_found"
    assert (
        await session_memory.extract_session_memory_for_message(
            conversation_id, source_id
        )
    )["reason"] == "agent_not_found"
    assert (
        await session_memory.extract_session_memory_for_message(
            conversation_id, source_id
        )
    )["reason"] == "session_memory_disabled"
    assert (
        await session_memory.extract_session_memory_for_message(
            conversation_id, source_id
        )
    )["reason"] == "async_extract_disabled"


@pytest.mark.anyio
async def test_extraction_rejects_invalid_source_and_insufficient_history(monkeypatch):
    conversation_id = uuid4()
    source_id = uuid4()
    agent = SimpleNamespace()
    conversation = SimpleNamespace(agent_id=uuid4())
    assistant = message(id=source_id)

    monkeypatch.setattr(
        session_memory.Conversation,
        "filter",
        MagicMock(return_value=Query(conversation)),
    )
    monkeypatch.setattr(
        session_memory.Agent, "filter", MagicMock(return_value=Query(agent))
    )
    monkeypatch.setattr(
        session_memory.Message,
        "filter",
        MagicMock(
            side_effect=[
                Query(None),
                Query(message(MessageRole.USER)),
                Query(assistant),
            ]
        ),
    )
    monkeypatch.setattr(
        session_memory,
        "is_message_on_active_branch",
        AsyncMock(side_effect=[True, False]),
    )
    monkeypatch.setattr(
        session_memory,
        "get_visible_conversation_messages",
        AsyncMock(return_value=[assistant]),
    )
    from app.services import chat_context

    monkeypatch.setattr(
        chat_context, "get_context_compression_config", MagicMock(return_value={})
    )

    assert (
        await session_memory.extract_session_memory_for_message(
            conversation_id, source_id
        )
    )["reason"] == "invalid_source_message"
    assert (
        await session_memory.extract_session_memory_for_message(
            conversation_id, source_id
        )
    )["reason"] == "invalid_source_message"
    assert (
        await session_memory.extract_session_memory_for_message(
            conversation_id, source_id
        )
    )["reason"] == "insufficient_turns"


@pytest.mark.anyio
async def test_extraction_skips_duplicate_and_outdated_tasks(monkeypatch):
    conversation_id = uuid4()
    source_id = uuid4()
    now = datetime.now(UTC)
    source = message(id=source_id, created_at=now)
    conversation = SimpleNamespace(agent_id=uuid4())
    agent = SimpleNamespace()
    duplicate = SimpleNamespace(
        source_message_id=source_id,
        status=ConversationSessionMemoryStatus.READY,
        snapshot_payload={},
    )
    newer_id = uuid4()
    outdated = SimpleNamespace(
        source_message_id=newer_id,
        status=ConversationSessionMemoryStatus.READY,
        snapshot_payload={},
    )

    monkeypatch.setattr(
        session_memory.Conversation,
        "filter",
        MagicMock(return_value=Query(conversation)),
    )
    monkeypatch.setattr(
        session_memory.Agent, "filter", MagicMock(return_value=Query(agent))
    )
    monkeypatch.setattr(
        session_memory.Message,
        "filter",
        MagicMock(
            side_effect=[
                Query(source),
                Query(source),
                Query(message(id=newer_id, created_at=now + timedelta(seconds=1))),
            ]
        ),
    )
    monkeypatch.setattr(
        session_memory, "is_message_on_active_branch", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        session_memory,
        "get_visible_conversation_messages",
        AsyncMock(return_value=[source]),
    )
    monkeypatch.setattr(
        session_memory.ConversationSessionMemory,
        "filter",
        MagicMock(side_effect=[Query(duplicate), Query(outdated)]),
    )
    from app.services import chat_context

    monkeypatch.setattr(
        chat_context,
        "get_context_compression_config",
        MagicMock(return_value={"session_memory_min_turns": 1}),
    )

    assert (
        await session_memory.extract_session_memory_for_message(
            conversation_id, source_id
        )
    )["reason"] == "already_extracted"
    assert (
        await session_memory.extract_session_memory_for_message(
            conversation_id, source_id
        )
    )["reason"] == "outdated_task"


@pytest.mark.anyio
async def test_extraction_persists_ready_snapshot_with_authorized_model(monkeypatch):
    conversation_id = uuid4()
    source_id = uuid4()
    source = message(id=source_id)
    conversation = SimpleNamespace(agent_id=uuid4())
    team_model_id = uuid4()
    agent = SimpleNamespace(model_id=team_model_id, team_id=uuid4())
    team_model = SimpleNamespace(
        id=team_model_id,
        model=SimpleNamespace(provider="openai", model_id="gpt-4o"),
    )
    snapshot = SimpleNamespace(
        source_message_id=source_id,
        status=ConversationSessionMemoryStatus.PENDING,
        snapshot_payload=None,
        summary_text=None,
        failure_count=2,
        save=AsyncMock(),
    )

    monkeypatch.setattr(
        session_memory.Conversation,
        "filter",
        MagicMock(return_value=Query(conversation)),
    )
    monkeypatch.setattr(
        session_memory.Agent, "filter", MagicMock(return_value=Query(agent))
    )
    monkeypatch.setattr(
        session_memory.Message, "filter", MagicMock(return_value=Query(source))
    )
    monkeypatch.setattr(
        session_memory, "is_message_on_active_branch", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        session_memory,
        "get_visible_conversation_messages",
        AsyncMock(return_value=[source]),
    )
    monkeypatch.setattr(
        session_memory.ConversationSessionMemory,
        "filter",
        MagicMock(return_value=Query(snapshot)),
    )
    monkeypatch.setattr(
        session_memory.TeamModel,
        "filter",
        MagicMock(return_value=Query(team_model)),
    )
    monkeypatch.setattr(
        session_memory.model_manager,
        "team_chat",
        AsyncMock(
            return_value=SimpleNamespace(
                content='{"overview": "Current goal"}', model=None
            )
        ),
    )
    monkeypatch.setattr(session_memory, "count_tokens", MagicMock(return_value=12))
    from app.services import chat_context

    monkeypatch.setattr(
        chat_context,
        "get_context_compression_config",
        MagicMock(return_value={"session_memory_min_turns": 1}),
    )

    result = await session_memory.extract_session_memory_for_message(
        conversation_id, source_id
    )

    assert result["status"] == "success"
    assert result["token_estimate"] == 12
    assert snapshot.status == ConversationSessionMemoryStatus.READY
    assert snapshot.extractor_model == str(team_model_id)
    assert session_memory.model_manager.team_chat.await_args.kwargs["model_id"] == str(
        team_model_id
    )
    snapshot.save.assert_awaited_once_with()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("summary", "expected_status"),
    [
        ("old summary", ConversationSessionMemoryStatus.STALE),
        ("", ConversationSessionMemoryStatus.FAILED),
    ],
)
async def test_extraction_records_model_failure(monkeypatch, summary, expected_status):
    conversation_id = uuid4()
    source_id = uuid4()
    source = message(id=source_id)
    conversation = SimpleNamespace(agent_id=uuid4())
    agent = SimpleNamespace(model_id=None, team_id=uuid4())
    snapshot = SimpleNamespace(
        source_message_id=None,
        snapshot_payload={},
        summary_text=summary,
        failure_count=None,
        save=AsyncMock(),
    )

    monkeypatch.setattr(
        session_memory.Conversation,
        "filter",
        MagicMock(return_value=Query(conversation)),
    )
    monkeypatch.setattr(
        session_memory.Agent, "filter", MagicMock(return_value=Query(agent))
    )
    monkeypatch.setattr(
        session_memory.Message, "filter", MagicMock(return_value=Query(source))
    )
    monkeypatch.setattr(
        session_memory, "is_message_on_active_branch", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        session_memory,
        "get_visible_conversation_messages",
        AsyncMock(return_value=[source]),
    )
    monkeypatch.setattr(
        session_memory.ConversationSessionMemory,
        "filter",
        MagicMock(return_value=Query(snapshot)),
    )
    monkeypatch.setattr(
        session_memory.model_manager,
        "team_chat",
        AsyncMock(side_effect=RuntimeError("model failed")),
    )
    monkeypatch.setattr(session_memory, "t", MagicMock(return_value="translated error"))
    from app.services import chat_context

    monkeypatch.setattr(
        chat_context,
        "get_context_compression_config",
        MagicMock(return_value={"session_memory_min_turns": 1}),
    )

    result = await session_memory.extract_session_memory_for_message(
        conversation_id, source_id
    )

    assert result["status"] == "error"
    assert result["error"] == "translated error"
    assert snapshot.status == expected_status
    assert snapshot.failure_count == 1
    assert snapshot.last_error == "model failed"


def test_payload_transcript_and_text_helpers_cover_edge_branches(monkeypatch):
    assert session_memory._get_model_identifier(None) is None
    assert session_memory._get_model_identifier(SimpleNamespace(model=None)) is None
    team_model_id = uuid4()
    team_model = SimpleNamespace(
        id=team_model_id,
        model=SimpleNamespace(id=uuid4(), provider="openai", model_id="gpt-4o"),
    )
    assert session_memory._get_model_identifier(team_model) == str(team_model_id)

    assert session_memory._parse_json_object(None) == {}
    assert session_memory._parse_json_object('```json\n{"overview": "ok"}\n```') == {
        "overview": "ok"
    }
    assert session_memory._parse_json_object('```\n{"overview": "ok"}\n```') == {
        "overview": "ok"
    }
    with pytest.raises(ValueError, match="JSON object"):
        session_memory._parse_json_object("[]")

    payload = session_memory._normalize_snapshot_payload(
        {
            "overview": None,
            "constraints": [" Same ", "same", "", 2] + [str(i) for i in range(8)],
        },
        previous_payload={"overview": " fallback ", "decisions": ["keep"]},
    )
    assert payload["overview"] == "fallback"
    assert payload["constraints"] == ["Same", "0", "1", "2", "3", "4"]
    assert payload["decisions"] == ["keep"]
    assert session_memory._normalize_list("bad") == []
    assert session_memory._normalize_text(None, max_chars=5) == ""
    assert session_memory._normalize_text("   ", max_chars=5) == ""
    assert session_memory._truncate_text("abcdef", 5) == "ab..."

    first = message(MessageRole.USER, content="question")
    assistant = message(
        content="answer",
        tool_calls=[{"name": "search"}, {"missing": "name"}, "invalid"],
    )
    second = message(MessageRole.USER, content="next")
    blocks = session_memory._split_turn_blocks([first, assistant, second])
    assert len(blocks) == 2
    assert session_memory._split_turn_blocks([]) == []
    assert (
        session_memory._render_transcript(
            [[message(content="", tool_calls=[{"name": ""}])]]
        )
        == "## Turn 1"
    )
    transcript = session_memory._render_transcript(blocks)
    assert "ASSISTANT_TOOL_CALLS: search" in transcript

    tool = message(MessageRole.TOOL, content="raw", tool_name="search")
    from app.services import chat_context

    monkeypatch.setattr(
        chat_context, "summarize_tool_result_for_llm", MagicMock(return_value="summary")
    )
    assert session_memory._format_message_content(tool) == "summary"
    assert session_memory._render_summary_text({}) == "Conversation session memory"
    rendered = session_memory._render_summary_text(
        {"overview": "goal", "decisions": ["ship"]}
    )
    assert "Overview: goal" in rendered and "- ship" in rendered

    assert (
        session_memory._fit_summary_to_budget(
            "", max_tokens=1, model_id="gpt-4", provider=None
        )
        == ""
    )
    monkeypatch.setattr(session_memory, "count_tokens", MagicMock(side_effect=[10, 1]))
    fitted = session_memory._fit_summary_to_budget(
        "x" * 300, max_tokens=1, model_id="gpt-4", provider=None
    )
    assert 0 < len(fitted) < 256
