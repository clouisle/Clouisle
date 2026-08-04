from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.agent import (
    ConversationContextCheckpointStatus,
    MessageRole,
)
from app.services import context_checkpoint


class QueryResult:
    def __init__(self, value):
        self.value = value

    async def first(self):
        return self.value

    def using_db(self, _connection):
        return self


class _Transaction:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return None


class _LockQuery:
    def using_db(self, _connection):
        return self

    def select_for_update(self):
        return self

    async def get(self):
        return SimpleNamespace()


def _patch_checkpoint_transaction(monkeypatch):
    connection = object()
    monkeypatch.setattr(
        context_checkpoint, "in_transaction", lambda: _Transaction(connection)
    )
    monkeypatch.setattr(
        context_checkpoint.Conversation, "filter", lambda **_kwargs: _LockQuery()
    )
    return connection


def message(role, content, *, images=None, tool_calls=None, tool_call_id=None):
    return SimpleNamespace(
        id=uuid4(),
        role=role,
        content=content,
        images=images,
        file_urls=None,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        created_at=datetime.now(UTC),
    )


def test_select_checkpoint_candidate_keeps_contiguous_tail_before_media():
    messages = [
        message(MessageRole.USER, "first request"),
        message(MessageRole.ASSISTANT, "first answer"),
        message(MessageRole.USER, "second request"),
        message(MessageRole.ASSISTANT, "second answer"),
        message(MessageRole.USER, "image request", images=[{"url": "image"}]),
        message(MessageRole.ASSISTANT, "image answer"),
        message(MessageRole.USER, "latest request"),
        message(MessageRole.ASSISTANT, "latest answer"),
    ]

    candidate = context_checkpoint.select_checkpoint_candidate(
        messages,
        recent_raw_turns=1,
        recent_tool_turns=0,
        min_new_turns=2,
    )

    assert candidate is not None
    assert candidate.covered_turns == 2
    assert candidate.retained_turns == 2
    assert candidate.source_message_id == messages[3].id
    assert [item.id for item in candidate.retained_messages] == [
        item.id for item in messages[4:]
    ]


def test_select_checkpoint_candidate_keeps_recent_tool_turn_contiguous():
    messages = [
        message(MessageRole.USER, "first request"),
        message(MessageRole.ASSISTANT, "first answer"),
        message(MessageRole.USER, "second request"),
        message(MessageRole.ASSISTANT, "second answer"),
        message(MessageRole.USER, "tool request"),
        message(
            MessageRole.ASSISTANT,
            "calling tool",
            tool_calls=[{"function": {"name": "search"}}],
        ),
        message(MessageRole.TOOL, "tool result", tool_call_id="call-1"),
        message(MessageRole.USER, "latest request"),
        message(MessageRole.ASSISTANT, "latest answer"),
    ]

    candidate = context_checkpoint.select_checkpoint_candidate(
        messages,
        recent_raw_turns=1,
        recent_tool_turns=1,
        min_new_turns=2,
    )

    assert candidate is not None
    assert candidate.covered_turns == 2
    assert candidate.source_message_id == messages[3].id
    assert [item.id for item in candidate.retained_messages] == [
        item.id for item in messages[4:]
    ]


@pytest.mark.anyio
async def test_invalid_active_branch_checkpoint_is_marked_stale(monkeypatch):
    checkpoint = SimpleNamespace(
        id=uuid4(),
        summary_text="Context checkpoint summary:\nold state",
        covered_through_message_id=uuid4(),
        status=ConversationContextCheckpointStatus.READY,
        save=AsyncMock(),
    )
    monkeypatch.setattr(
        context_checkpoint,
        "get_ready_context_checkpoint",
        AsyncMock(return_value=checkpoint),
    )
    monkeypatch.setattr(
        context_checkpoint,
        "is_message_on_active_branch",
        AsyncMock(return_value=False),
    )

    result = await context_checkpoint.get_valid_context_checkpoint(uuid4())

    assert result is None
    assert checkpoint.status == ConversationContextCheckpointStatus.STALE
    checkpoint.save.assert_awaited_once_with(update_fields=["status", "updated_at"])


@pytest.mark.anyio
async def test_create_context_checkpoint_persists_model_summary(monkeypatch):
    conversation = SimpleNamespace(id=uuid4())
    agent = SimpleNamespace(team_id=uuid4())
    created_at = datetime.now(UTC)
    messages = [
        SimpleNamespace(
            id=uuid4(),
            role=MessageRole.USER,
            content="first request " * 50,
            images=None,
            file_urls=None,
            tool_calls=None,
            tool_call_id=None,
            created_at=created_at,
        ),
        SimpleNamespace(
            id=uuid4(),
            role=MessageRole.ASSISTANT,
            content="first answer " * 50,
            images=None,
            file_urls=None,
            tool_calls=None,
            tool_call_id=None,
            created_at=created_at + timedelta(seconds=1),
        ),
        SimpleNamespace(
            id=uuid4(),
            role=MessageRole.USER,
            content="second request " * 50,
            images=None,
            file_urls=None,
            tool_calls=None,
            tool_call_id=None,
            created_at=created_at + timedelta(seconds=2),
        ),
        SimpleNamespace(
            id=uuid4(),
            role=MessageRole.ASSISTANT,
            content="second answer " * 50,
            images=None,
            file_urls=None,
            tool_calls=None,
            tool_call_id=None,
            created_at=created_at + timedelta(seconds=3),
        ),
        SimpleNamespace(
            id=uuid4(),
            role=MessageRole.USER,
            content="latest request",
            images=None,
            file_urls=None,
            tool_calls=None,
            tool_call_id=None,
            created_at=created_at + timedelta(seconds=4),
        ),
    ]
    checkpoint = SimpleNamespace(
        covered_through_message_id=None,
        status=ConversationContextCheckpointStatus.PENDING,
        summary_text="",
        summary_payload={},
        token_estimate=0,
        summarizer_model=None,
        failure_count=0,
        last_error=None,
        last_summarized_at=None,
        save=AsyncMock(),
    )

    get_or_create = AsyncMock(return_value=(checkpoint, True))
    monkeypatch.setattr(
        context_checkpoint.ConversationContextCheckpoint,
        "get_or_create",
        get_or_create,
    )
    monkeypatch.setattr(
        context_checkpoint.model_manager,
        "team_chat",
        AsyncMock(
            return_value=SimpleNamespace(
                content=(
                    '{"conversation_goal":"finish the migration",'
                    '"decisions":["use checkpoints"],'
                    '"pending_work":["write tests"]}'
                ),
                model="provider/test-model",
            )
        ),
    )
    monkeypatch.setattr(
        context_checkpoint,
        "count_tokens",
        lambda text, model_id, provider=None: len(str(text)),
    )
    connection = _patch_checkpoint_transaction(monkeypatch)

    async def wait_for_response(awaitable, *, timeout):
        return await awaitable

    wait_for = AsyncMock(side_effect=wait_for_response)
    monkeypatch.setattr(context_checkpoint.asyncio, "wait_for", wait_for)

    result = await context_checkpoint.create_context_checkpoint(
        agent=agent,
        conversation=conversation,
        messages=messages,
        previous_checkpoint=None,
        model_id="provider/test-model",
        provider="provider",
        summary_max_tokens=100,
        recent_raw_turns=1,
        recent_tool_turns=0,
        min_new_turns=1,
        input_budget=4000,
    )

    assert result.created is True
    assert result.checkpoint is checkpoint
    assert result.covered_turns == 2
    assert result.retained_turns == 1
    assert checkpoint.covered_through_message_id == messages[3].id
    assert checkpoint.status == ConversationContextCheckpointStatus.READY
    assert checkpoint.summary_payload["conversation_goal"] == "finish the migration"
    assert checkpoint.summary_payload["decisions"] == ["use checkpoints"]
    assert checkpoint.summarizer_model == "provider/test-model"
    checkpoint.save.assert_awaited_once_with(using_db=connection)
    assert wait_for.await_args.kwargs["timeout"] == (
        context_checkpoint.CHECKPOINT_SUMMARY_TIMEOUT_SECONDS
    )
    get_or_create.assert_awaited_once_with(
        conversation_id=conversation.id,
        defaults={"status": ConversationContextCheckpointStatus.PENDING},
        using_db=connection,
    )


@pytest.mark.anyio
async def test_create_context_checkpoint_returns_error_when_summary_model_fails(
    monkeypatch,
):
    conversation = SimpleNamespace(id=uuid4())
    source = message(MessageRole.ASSISTANT, "old response")
    candidate = SimpleNamespace(
        source_message_id=source.id,
        covered_messages=[source],
        covered_turns=1,
        retained_turns=1,
    )
    record_failure = AsyncMock()
    model_error = RuntimeError("summary unavailable")
    monkeypatch.setattr(
        context_checkpoint,
        "select_checkpoint_candidate",
        lambda *_args, **_kwargs: candidate,
    )
    monkeypatch.setattr(
        context_checkpoint, "count_tokens", lambda *_args, **_kwargs: 10
    )
    monkeypatch.setattr(
        context_checkpoint.model_manager,
        "team_chat",
        AsyncMock(side_effect=model_error),
    )
    monkeypatch.setattr(
        context_checkpoint, "_record_generation_failure", record_failure
    )

    result = await context_checkpoint.create_context_checkpoint(
        agent=SimpleNamespace(team_id=uuid4()),
        conversation=conversation,
        messages=[source],
        previous_checkpoint=None,
        model_id="provider/test-model",
        provider="provider",
        summary_max_tokens=100,
        recent_raw_turns=1,
        recent_tool_turns=0,
        min_new_turns=1,
        input_budget=4000,
    )

    assert result.created is False
    assert result.error == "summary unavailable"
    record_failure.assert_awaited_once_with(
        conversation=conversation,
        source_message_id=source.id,
        error=model_error,
    )


def test_checkpoint_helpers_preserve_bounded_structured_state():
    empty_candidate = context_checkpoint.CheckpointCandidate([], [], 0, 0)
    assert empty_candidate.source_message_id is None
    assert (
        context_checkpoint.select_checkpoint_candidate(
            [], recent_raw_turns=1, recent_tool_turns=1, min_new_turns=1
        )
        is None
    )

    leading_assistant = message(MessageRole.ASSISTANT, "orphan answer")
    leading_tool = message(MessageRole.TOOL, "orphan tool result")
    assert context_checkpoint._split_turn_blocks([leading_assistant, leading_tool]) == [
        [leading_assistant, leading_tool]
    ]

    no_tool_history = [
        message(MessageRole.USER, "first"),
        message(MessageRole.ASSISTANT, "first answer"),
        message(MessageRole.USER, "second"),
        message(MessageRole.ASSISTANT, "second answer"),
        message(MessageRole.USER, "latest"),
    ]
    no_tool_candidate = context_checkpoint.select_checkpoint_candidate(
        no_tool_history,
        recent_raw_turns=1,
        recent_tool_turns=2,
        min_new_turns=1,
    )
    assert no_tool_candidate is not None
    assert no_tool_candidate.covered_turns == 2

    object_tool_call = SimpleNamespace(function=SimpleNamespace(name="lookup"))
    structured_message = message(
        MessageRole.ASSISTANT,
        {"result": "x" * 2000},
        tool_calls=[
            {"name": "search"},
            {"function": {"name": "calculate"}},
            object_tool_call,
        ],
        tool_call_id="call-1",
    )
    transcript = context_checkpoint.render_checkpoint_transcript([structured_message])
    assert '"result"' in transcript
    assert "TOOL_CALLS: search, calculate, lookup" in transcript
    assert "TOOL_CALL_ID: call-1" in transcript
    bounded_transcript = context_checkpoint.render_checkpoint_transcript(
        [structured_message], max_chars=80
    )
    assert "middle transcript omitted for budget" in bounded_transcript

    decisions = ["same", "same", *[f"decision-{index}" for index in range(12)]]
    normalized = context_checkpoint.normalize_checkpoint_payload(
        {
            "conversation_goal": None,
            "latest_user_intent": 42,
            "constraints": None,
            "decisions": decisions,
        },
        previous_payload={
            "conversation_goal": "  preserve   exact goal  ",
            "constraints": ["keep compatibility"],
        },
    )
    assert normalized["conversation_goal"] == "preserve exact goal"
    assert normalized["latest_user_intent"] == ""
    assert normalized["constraints"] == ["keep compatibility"]
    assert len(normalized["decisions"]) == context_checkpoint.CHECKPOINT_MAX_LIST_ITEMS
    assert normalized["decisions"].count("same") == 1
    assert context_checkpoint._truncate("abcdef", 5) == "ab..."

    assert context_checkpoint._parse_json_object(None) == {}
    assert context_checkpoint._parse_json_object(
        '```json\n{"conversation_goal":"goal"}\n```'
    ) == {"conversation_goal": "goal"}
    assert context_checkpoint._parse_json_object(
        '```\n{"latest_user_intent":"continue"}\n```'
    ) == {"latest_user_intent": "continue"}
    with pytest.raises(ValueError, match="did not return an object"):
        context_checkpoint._parse_json_object("[]")
    assert (
        context_checkpoint.fit_checkpoint_summary(
            "", max_tokens=10, model_id="model", provider=None
        )
        == ""
    )


@pytest.mark.anyio
async def test_valid_checkpoint_returns_active_checkpoint(monkeypatch):
    checkpoint = SimpleNamespace(
        id=uuid4(),
        summary_text="Context checkpoint summary:\ncurrent state",
        covered_through_message_id=uuid4(),
    )
    monkeypatch.setattr(
        context_checkpoint,
        "get_ready_context_checkpoint",
        AsyncMock(return_value=checkpoint),
    )
    active_branch = AsyncMock(return_value=True)
    monkeypatch.setattr(
        context_checkpoint, "is_message_on_active_branch", active_branch
    )

    result = await context_checkpoint.get_valid_context_checkpoint(uuid4())

    assert result is checkpoint
    active_branch.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("existing_summary", [None, "last good summary"])
async def test_checkpoint_failure_bookkeeping_preserves_ready_summary(
    monkeypatch, existing_summary
):
    source_message_id = uuid4()
    checkpoint = SimpleNamespace(
        covered_through_message_id=source_message_id,
        summary_text=existing_summary or "",
        status=(
            ConversationContextCheckpointStatus.READY
            if existing_summary
            else ConversationContextCheckpointStatus.PENDING
        ),
        failure_count=0,
        last_error=None,
        save=AsyncMock(),
    )
    existing = checkpoint if existing_summary else None
    monkeypatch.setattr(
        context_checkpoint.ConversationContextCheckpoint,
        "filter",
        lambda **_kwargs: QueryResult(existing),
    )
    create_checkpoint = AsyncMock(return_value=checkpoint)
    monkeypatch.setattr(
        context_checkpoint.ConversationContextCheckpoint,
        "create",
        create_checkpoint,
    )

    await context_checkpoint._record_generation_failure(
        conversation=SimpleNamespace(id=uuid4()),
        source_message_id=source_message_id,
        error=RuntimeError("summarizer unavailable"),
    )

    assert checkpoint.failure_count == 1
    assert checkpoint.last_error == "summarizer unavailable"
    assert checkpoint.status == (
        ConversationContextCheckpointStatus.READY
        if existing_summary
        else ConversationContextCheckpointStatus.FAILED
    )
    if existing_summary:
        create_checkpoint.assert_not_awaited()
    else:
        create_checkpoint.assert_awaited_once()
    checkpoint.save.assert_awaited_once()


@pytest.mark.anyio
async def test_existing_checkpoint_compares_covered_message_position(monkeypatch):
    conversation_id = uuid4()
    source = message(MessageRole.ASSISTANT, "new source")
    existing_source = message(MessageRole.ASSISTANT, "newer source")
    existing_source.created_at = source.created_at + timedelta(seconds=1)
    checkpoint = SimpleNamespace(
        covered_through_message_id=existing_source.id,
        conversation_id=conversation_id,
    )
    monkeypatch.setattr(
        context_checkpoint.ConversationMessage,
        "filter",
        lambda **_kwargs: QueryResult(existing_source),
    )

    assert await context_checkpoint._existing_checkpoint_is_newer(checkpoint, source)
    assert await context_checkpoint._existing_checkpoint_is_newer(
        checkpoint, source, using_db=object()
    )
    checkpoint.covered_through_message_id = None
    assert not await context_checkpoint._existing_checkpoint_is_newer(
        checkpoint, source
    )


@pytest.mark.anyio
async def test_create_checkpoint_reuses_newer_previous_checkpoint(monkeypatch):
    source = message(MessageRole.ASSISTANT, "covered source")
    candidate = context_checkpoint.CheckpointCandidate([source], [], 1, 0)
    previous_checkpoint = SimpleNamespace(
        covered_through_message_id=uuid4(),
        conversation_id=uuid4(),
    )
    monkeypatch.setattr(
        context_checkpoint,
        "select_checkpoint_candidate",
        lambda *_args, **_kwargs: candidate,
    )
    newer = AsyncMock(return_value=True)
    monkeypatch.setattr(context_checkpoint, "_existing_checkpoint_is_newer", newer)
    team_chat = AsyncMock()
    monkeypatch.setattr(context_checkpoint.model_manager, "team_chat", team_chat)

    result = await context_checkpoint.create_context_checkpoint(
        agent=SimpleNamespace(team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        messages=[source],
        previous_checkpoint=previous_checkpoint,
        model_id="model",
        provider=None,
        summary_max_tokens=100,
        recent_raw_turns=1,
        recent_tool_turns=0,
        min_new_turns=1,
        input_budget=1000,
    )

    assert result.checkpoint is previous_checkpoint
    assert result.created is False
    newer.assert_awaited_once_with(previous_checkpoint, source)
    team_chat.assert_not_awaited()


@pytest.mark.anyio
async def test_create_checkpoint_skips_empty_or_non_compacting_summary(monkeypatch):
    source = message(MessageRole.ASSISTANT, "covered source")
    candidate = context_checkpoint.CheckpointCandidate([source], [], 1, 0)
    monkeypatch.setattr(
        context_checkpoint,
        "select_checkpoint_candidate",
        lambda *_args, **_kwargs: candidate,
    )
    team_chat = AsyncMock(
        return_value=SimpleNamespace(
            content='{"conversation_goal":"same size"}', model="model"
        )
    )
    monkeypatch.setattr(context_checkpoint.model_manager, "team_chat", team_chat)
    monkeypatch.setattr(context_checkpoint, "count_tokens", lambda *_args, **_kwargs: 0)

    empty_result = await context_checkpoint.create_context_checkpoint(
        agent=SimpleNamespace(team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        messages=[source],
        previous_checkpoint=None,
        model_id="model",
        provider=None,
        summary_max_tokens=100,
        recent_raw_turns=1,
        recent_tool_turns=0,
        min_new_turns=1,
        input_budget=1000,
    )
    assert empty_result.created is False
    team_chat.assert_not_awaited()

    monkeypatch.setattr(
        context_checkpoint, "count_tokens", lambda *_args, **_kwargs: 10
    )
    no_benefit_result = await context_checkpoint.create_context_checkpoint(
        agent=SimpleNamespace(team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        messages=[source],
        previous_checkpoint=None,
        model_id="model",
        provider=None,
        summary_max_tokens=100,
        recent_raw_turns=1,
        recent_tool_turns=0,
        min_new_turns=1,
        input_budget=1000,
    )
    assert no_benefit_result.created is False
    team_chat.assert_awaited_once()


@pytest.mark.anyio
async def test_create_checkpoint_loses_concurrent_update_race(monkeypatch):
    source = message(MessageRole.ASSISTANT, "covered source " * 50)
    candidate = context_checkpoint.CheckpointCandidate([source], [], 1, 0)
    checkpoint = SimpleNamespace(save=AsyncMock())
    monkeypatch.setattr(
        context_checkpoint,
        "select_checkpoint_candidate",
        lambda *_args, **_kwargs: candidate,
    )
    monkeypatch.setattr(
        context_checkpoint,
        "count_tokens",
        lambda text, *_args, **_kwargs: 100 if "covered source" in str(text) else 10,
    )
    monkeypatch.setattr(
        context_checkpoint.model_manager,
        "team_chat",
        AsyncMock(
            return_value=SimpleNamespace(
                content='{"conversation_goal":"continue"}', model="model"
            )
        ),
    )
    monkeypatch.setattr(
        context_checkpoint.ConversationContextCheckpoint,
        "get_or_create",
        AsyncMock(return_value=(checkpoint, False)),
    )
    _patch_checkpoint_transaction(monkeypatch)
    monkeypatch.setattr(
        context_checkpoint,
        "_existing_checkpoint_is_newer",
        AsyncMock(return_value=True),
    )

    result = await context_checkpoint.create_context_checkpoint(
        agent=SimpleNamespace(team_id=uuid4()),
        conversation=SimpleNamespace(id=uuid4()),
        messages=[source],
        previous_checkpoint=None,
        model_id="model",
        provider=None,
        summary_max_tokens=100,
        recent_raw_turns=1,
        recent_tool_turns=0,
        min_new_turns=1,
        input_budget=1000,
    )

    assert result.checkpoint is checkpoint
    assert result.created is False
    checkpoint.save.assert_not_awaited()


def test_checkpoint_candidate_requires_new_turns_and_checks_multiple_tools():
    first_only = [message(MessageRole.USER, "only turn")]
    assert (
        context_checkpoint.select_checkpoint_candidate(
            first_only, recent_raw_turns=1, recent_tool_turns=0, min_new_turns=2
        )
        is None
    )

    messages = [
        message(MessageRole.USER, "ordinary old"),
        message(MessageRole.ASSISTANT, "ordinary answer"),
    ]
    for index in range(3):
        messages.extend(
            [
                message(MessageRole.USER, f"tool request {index}"),
                message(
                    MessageRole.ASSISTANT,
                    f"tool call {index}",
                    tool_calls=[{"name": f"tool-{index}"}],
                ),
                message(
                    MessageRole.TOOL, f"tool result {index}", tool_call_id=str(index)
                ),
            ]
        )
    messages.extend(
        [
            message(MessageRole.USER, "latest"),
            message(MessageRole.ASSISTANT, "latest answer"),
        ]
    )
    candidate = context_checkpoint.select_checkpoint_candidate(
        messages, recent_raw_turns=1, recent_tool_turns=3, min_new_turns=1
    )
    assert candidate is not None
    assert candidate.covered_turns == 1


@pytest.mark.anyio
async def test_create_checkpoint_rejects_missing_source_and_team(monkeypatch):
    conversation = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        context_checkpoint,
        "select_checkpoint_candidate",
        lambda *_args, **_kwargs: context_checkpoint.CheckpointCandidate([], [], 0, 0),
    )
    result = await context_checkpoint.create_context_checkpoint(
        agent=SimpleNamespace(team_id=uuid4()),
        conversation=conversation,
        messages=[],
        previous_checkpoint=None,
        model_id="model",
        provider=None,
        summary_max_tokens=100,
        recent_raw_turns=1,
        recent_tool_turns=0,
        min_new_turns=1,
        input_budget=1000,
    )
    assert result.created is False

    source = message(MessageRole.ASSISTANT, "covered")
    monkeypatch.setattr(
        context_checkpoint,
        "select_checkpoint_candidate",
        lambda *_args, **_kwargs: context_checkpoint.CheckpointCandidate(
            [source], [], 1, 0
        ),
    )
    result = await context_checkpoint.create_context_checkpoint(
        agent=SimpleNamespace(team_id=None),
        conversation=conversation,
        messages=[source],
        previous_checkpoint=None,
        model_id="model",
        provider=None,
        summary_max_tokens=100,
        recent_raw_turns=1,
        recent_tool_turns=0,
        min_new_turns=1,
        input_budget=1000,
    )
    assert result.error == "agent_team_missing"


@pytest.mark.anyio
async def test_valid_checkpoint_skips_incomplete_record(monkeypatch):
    monkeypatch.setattr(
        context_checkpoint,
        "get_ready_context_checkpoint",
        AsyncMock(
            return_value=SimpleNamespace(
                summary_text="", covered_through_message_id=uuid4()
            )
        ),
    )
    active_branch = AsyncMock()
    monkeypatch.setattr(
        context_checkpoint, "is_message_on_active_branch", active_branch
    )

    assert await context_checkpoint.get_valid_context_checkpoint(uuid4()) is None
    active_branch.assert_not_awaited()
