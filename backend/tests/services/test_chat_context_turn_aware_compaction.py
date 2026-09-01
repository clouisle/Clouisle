"""
Focused tests for turn-aware, reserve-based context compaction.

Covers the contracts introduced when the fixed 90% whole-history summary was
replaced by:

- reserve-aware trigger: ``context - max(15% of context, output reserve)``,
- turn-aware cut points at complete round / tool-protocol boundaries,
- recent verbatim tail retention (previous summary + compacted old turns +
  recent raw tail),
- incremental summary: only newly covered old turns are summarized and the
  watermark advances to the last summarized message,
- oversized completed-turn prefix compaction (never splits an unfinished tool
  protocol),
- fail-fast: a protected payload that cannot fit raises before any provider
  call.
"""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.errors import ContextLengthError
from app.llm.types import FunctionCall, Message, MessageRole, ToolCall
from app.models.agent import MessageRole as ConversationMessageRole
from app.services import chat_context

SYSTEM = Message(role=MessageRole.SYSTEM, content="system")
CURRENT = Message(role=MessageRole.USER, content="current request")


def _agent():
    return SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        system_prompt="",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        context_compression_config={},
    )


def _conversation():
    return SimpleNamespace(
        id=uuid4(),
        variables={},
        context_summary_text=None,
        context_summary_watermark_id=None,
    )


def _row(
    role,
    content,
    *,
    round_id=None,
    is_canonical=False,
    tool_calls=None,
    tool_call_id=None,
):
    return SimpleNamespace(
        id=uuid4(),
        role=role,
        content=content,
        file_urls=None,
        reasoning_content=None,
        tool_calls=tool_calls,
        round_id=round_id,
        round_role="assistant_final" if is_canonical else None,
        is_round_canonical=is_canonical,
        tool_call_id=tool_call_id,
    )


def _tool_call(call_id):
    return ToolCall(id=call_id, function=FunctionCall(name="tool", arguments="{}"))


def _meta(messages, rows):
    """Meta sidecar aligned with the flattened message list.

    ``rows`` must cover every message after the system prompt; the trailing
    current-user message gets a synthetic entry when not present in ``rows``.
    """
    meta = [{"role": "system", "round_id": None, "source_message_id": None}]
    for row in rows:
        meta.append(
            {
                "role": (
                    row.role.value if hasattr(row.role, "value") else str(row.role)
                ),
                "round_id": row.round_id,
                "round_role": row.round_role,
                "is_round_canonical": row.is_round_canonical,
                "tool_call_id": row.tool_call_id,
                "tool_calls": row.tool_calls or [],
                "source_role": (
                    row.role.value if hasattr(row.role, "value") else str(row.role)
                ),
                "source_message_id": row.id,
            }
        )
    if len(messages) > len(meta):
        for msg in messages[len(meta) :]:
            meta.append(
                {
                    "role": (
                        msg.role.value if hasattr(msg.role, "value") else str(msg.role)
                    ),
                    "round_id": None,
                    "round_role": "user_input",
                    "is_round_canonical": True,
                    "tool_calls": [],
                    "source_role": "user",
                    "source_message_id": uuid4(),
                }
            )
    return meta


async def async_lambda_true(*_args, **_kwargs):
    return True


def _install(monkeypatch, *, build, estimate, summarize=None, persist=None):
    monkeypatch.setattr(chat_context, "_build_messages_with_file_content", build)
    if summarize is not None:
        monkeypatch.setattr(chat_context, "_summarize_context", summarize)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", estimate)
    if persist is not None:
        monkeypatch.setattr(chat_context, "_persist_context_summary", persist)


# ---------- Reserve-aware trigger ----------


@pytest.mark.anyio
async def test_trigger_uses_reserve_not_fixed_90_percent(monkeypatch):
    """A payload at 85% of the window fires the reserve-aware trigger where the
    old fixed 90% would not."""
    agent = _agent()
    conversation = _conversation()
    summarize_calls = 0
    old_round = uuid4()
    rows = [
        _row(ConversationMessageRole.USER, "old q", round_id=old_round),
        _row(
            ConversationMessageRole.ASSISTANT,
            "old a",
            round_id=old_round,
            is_canonical=True,
        ),
    ]
    old_msgs = [
        Message(role=MessageRole.USER, content="old q"),
        Message(role=MessageRole.ASSISTANT, content="old a"),
    ]
    messages = [SYSTEM, *old_msgs, CURRENT]

    async def build_messages(**_kwargs):
        return messages, set(), _meta(messages, rows)

    async def summarize(**_kwargs):
        nonlocal summarize_calls
        summarize_calls += 1
        return "summary"

    def estimate(messages_, *, model_id, provider):
        del model_id, provider
        # system/current ~100 each; old history messages ~42_800 each, so the
        # full payload sits near 85% of the 100_000 window (fires the reserve
        # trigger at 85k but not the old fixed 90% boundary of 90k).
        return sum(
            100
            if getattr(m, "content", "") in ("system", "current request")
            else 42_800
            for m in messages_
        )

    _install(monkeypatch, build=build_messages, estimate=estimate, summarize=summarize)
    plan = await chat_context.build_context_plan(
        agent=agent,
        conversation=conversation,
        user_message="current request",
        model_id="model",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        include_current_user_message=True,
    )
    assert plan.trigger_budget < 90_000
    assert plan.will_summarize is True


@pytest.mark.anyio
async def test_reserve_trigger_is_below_hard_budget(monkeypatch):
    """Reserve-aware trigger is clamped by the hard input budget."""
    agent = _agent()
    conversation = _conversation()

    async def build_messages(**_kwargs):
        return [SYSTEM, CURRENT], set(), _meta([SYSTEM, CURRENT], [])

    def estimate(messages, *, model_id, provider):
        del model_id, provider
        return 100

    _install(monkeypatch, build=build_messages, estimate=estimate)
    plan = await chat_context.build_context_plan(
        agent=agent,
        conversation=conversation,
        user_message="current request",
        model_id="model",
        model_context_limit=10_000,
        model_max_output_tokens=512,
        include_current_user_message=True,
    )
    assert plan.trigger_budget <= plan.token_budget.input_budget
    assert plan.trigger_budget < 10_000


# ---------- Turn-aware cut + recent tail ----------


@pytest.mark.anyio
async def test_tail_keeps_recent_round_verbatim_and_summarizes_old(monkeypatch):
    """Old round summarized; the recent complete round stays verbatim."""
    agent = _agent()
    conversation = _conversation()
    old_round_id = uuid4()
    recent_round_id = uuid4()
    rows = [
        _row(ConversationMessageRole.USER, "old q", round_id=old_round_id),
        _row(
            ConversationMessageRole.ASSISTANT,
            "old a",
            round_id=old_round_id,
            is_canonical=True,
        ),
        _row(ConversationMessageRole.USER, "recent q", round_id=recent_round_id),
        _row(
            ConversationMessageRole.ASSISTANT,
            "recent a",
            round_id=recent_round_id,
            is_canonical=True,
        ),
    ]
    old_msgs = [
        Message(role=MessageRole.USER, content="old q"),
        Message(role=MessageRole.ASSISTANT, content="old a"),
    ]
    recent_msgs = [
        Message(role=MessageRole.USER, content="recent q"),
        Message(role=MessageRole.ASSISTANT, content="recent a"),
    ]
    messages = [SYSTEM, *old_msgs, *recent_msgs, CURRENT]

    async def build_messages(**_kwargs):
        return messages, set(), _meta(messages, rows)

    summarize_calls = 0
    summarized_contents = {}

    async def summarize(**_kwargs):
        nonlocal summarize_calls
        summarize_calls += 1
        summarized_contents["text"] = [
            getattr(m, "content", "") for m in _kwargs["messages_to_summarize"]
        ]
        return "old summary"

    def estimate(messages_, *, model_id, provider):
        del model_id, provider
        # old round oversized (44k each -> 88k) triggers the 85k reserve
        # trigger; the protected active round stays small (8k each) so the
        # post-summary payload fits the 98k input budget.
        return sum(
            100
            if getattr(m, "content", "") in ("system", "current request")
            else 8_000
            if getattr(m, "content", "") in ("recent q", "recent a")
            else 44_000
            for m in messages_
        )

    _install(
        monkeypatch,
        build=build_messages,
        estimate=estimate,
        summarize=summarize,
    )
    plan = await chat_context.build_context_plan(
        agent=agent,
        conversation=conversation,
        user_message="current request",
        model_id="model",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        include_current_user_message=True,
    )
    prepared = await plan.finalize()

    assert plan.will_summarize is True
    assert summarized_contents["text"] == ["old q", "old a"]
    tail_contents = [m.content for m in prepared.messages]
    assert "recent q" in tail_contents
    assert "recent a" in tail_contents
    assert "old q" not in tail_contents
    assert "old a" not in tail_contents
    assert summarize_calls == 1


@pytest.mark.anyio
async def test_incomplete_tool_protocol_never_cut_or_summarized(monkeypatch):
    """An assistant step whose tool call has no tool result is protected."""
    agent = _agent()
    conversation = _conversation()
    old_round_id = uuid4()
    active_round_id = uuid4()
    rows = [
        _row(ConversationMessageRole.USER, "old q", round_id=old_round_id),
        _row(
            ConversationMessageRole.ASSISTANT,
            "old a",
            round_id=old_round_id,
            is_canonical=True,
        ),
        _row(ConversationMessageRole.USER, "active q", round_id=active_round_id),
        _row(
            ConversationMessageRole.ASSISTANT,
            "pending tool",
            round_id=active_round_id,
            tool_calls=[_tool_call("call_x")],
        ),
    ]
    old_msgs = [
        Message(role=MessageRole.USER, content="old q"),
        Message(role=MessageRole.ASSISTANT, content="old a"),
    ]
    active_msgs = [
        Message(role=MessageRole.USER, content="active q"),
        Message(
            role=MessageRole.ASSISTANT,
            content="pending tool",
            tool_calls=[_tool_call("call_x")],
        ),
    ]
    messages = [SYSTEM, *old_msgs, *active_msgs, CURRENT]

    async def build_messages(**_kwargs):
        return messages, set(), _meta(messages, rows)

    summarize_calls = 0
    summarized_contents = {}

    async def summarize(**_kwargs):
        nonlocal summarize_calls
        summarize_calls += 1
        summarized_contents["text"] = [
            getattr(m, "content", "") for m in _kwargs["messages_to_summarize"]
        ]
        return "old summary"

    def estimate(messages_, *, model_id, provider):
        del model_id, provider
        # old round oversized (44k each -> 88k) triggers the 85k reserve
        # trigger; the protected active round stays small (8k each) so the
        # post-summary payload fits the 98k input budget.
        return sum(
            100
            if getattr(m, "content", "") in ("system", "current request")
            else 8_000
            if getattr(m, "content", "") in ("active q", "pending tool")
            else 44_000
            for m in messages_
        )

    _install(
        monkeypatch,
        build=build_messages,
        estimate=estimate,
        summarize=summarize,
    )
    plan = await chat_context.build_context_plan(
        agent=agent,
        conversation=conversation,
        user_message="current request",
        model_id="model",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        include_current_user_message=True,
    )
    prepared = await plan.finalize()

    assert plan.will_summarize is True
    assert summarized_contents["text"] == ["old q", "old a"]
    tail_contents = [m.content for m in prepared.messages]
    assert "pending tool" in tail_contents
    assert "active q" in tail_contents


# ---------- Incremental summary + watermark ----------


@pytest.mark.anyio
async def test_incremental_summary_keeps_previous_and_moves_watermark(monkeypatch):
    """Previous summary carried into the summarizer; watermark advances to the
    last newly covered message; recent newly covered round stays raw."""
    agent = _agent()
    conversation = _conversation()
    conversation.context_summary_text = "previous summary"
    conversation.context_summary_watermark_id = uuid4()
    sum_round_id = uuid4()
    tail_round_id = uuid4()
    rows = [
        _row(ConversationMessageRole.USER, "to summarize q", round_id=sum_round_id),
        _row(
            ConversationMessageRole.ASSISTANT,
            "to summarize a",
            round_id=sum_round_id,
            is_canonical=True,
        ),
        _row(ConversationMessageRole.USER, "tail q", round_id=tail_round_id),
        _row(
            ConversationMessageRole.ASSISTANT,
            "tail a",
            round_id=tail_round_id,
            is_canonical=True,
        ),
    ]
    latest_sum_row_id = rows[1].id
    sys = Message(role=MessageRole.SYSTEM, content="system")
    summary_msg = Message(
        role=MessageRole.USER,
        content=f"{chat_context.CONTEXT_SUMMARY_PREFIX}\n\nprevious summary",
    )
    sum_msgs = [
        Message(role=MessageRole.USER, content="to summarize q"),
        Message(role=MessageRole.ASSISTANT, content="to summarize a"),
    ]
    tail_msgs = [
        Message(role=MessageRole.USER, content="tail q"),
        Message(role=MessageRole.ASSISTANT, content="tail a"),
    ]
    messages = [sys, summary_msg, *sum_msgs, *tail_msgs, CURRENT]

    def build_meta():
        meta = [{"role": "system", "round_id": None, "source_message_id": None}]
        meta.append(
            {
                "role": "user",
                "round_id": None,
                "source_role": "summary",
                "source_message_id": None,
            }
        )
        meta.extend(
            {
                "role": "user" if i % 2 == 0 else "assistant",
                "round_id": rows[i].round_id,
                "round_role": "user_input" if i % 2 == 0 else "assistant_final",
                "is_round_canonical": rows[i].is_round_canonical,
                "tool_calls": [],
                "source_role": "user" if i % 2 == 0 else "assistant",
                "source_message_id": rows[i].id,
            }
            for i in range(len(rows))
        )
        return meta

    async def build_messages(**_kwargs):
        return messages, set(), build_meta()

    captured_previous = {}

    async def summarize(**_kwargs):
        captured_previous["previous_summary"] = _kwargs.get("previous_summary")
        return "extended summary"

    persisted = {}

    class UpdateQuery:
        async def update(self, **values):
            persisted.update(values)

    def estimate(messages_, *, model_id, provider):
        del model_id, provider
        # to-summarize round oversized (40k each -> 80k); tail round small
        # (8k each -> 16k) so it fits the ~20k tail budget and stays raw.
        return sum(
            100
            if getattr(m, "content", "") in ("system", "current request")
            else 1000
            if isinstance(getattr(m, "content", ""), str)
            and getattr(m, "content", "").startswith(
                chat_context.CONTEXT_SUMMARY_PREFIX
            )
            else 40_000
            if "to summarize" in str(getattr(m, "content", "") or "")
            else 8_000
            for m in messages_
        )

    _install(
        monkeypatch,
        build=build_messages,
        estimate=estimate,
        summarize=summarize,
    )
    monkeypatch.setattr(
        chat_context.Conversation,
        "filter",
        lambda *_args, **_kwargs: UpdateQuery(),
    )
    monkeypatch.setattr(chat_context, "is_message_on_active_branch", async_lambda_true)

    plan = await chat_context.build_context_plan(
        agent=agent,
        conversation=conversation,
        user_message="current request",
        model_id="model",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        include_current_user_message=True,
        current_user_message_id=uuid4(),
    )
    prepared = await plan.finalize()

    assert plan.will_summarize is True
    assert captured_previous["previous_summary"] == "previous summary"
    assert persisted["context_summary_watermark_id"] == latest_sum_row_id
    summary_msg_out = next(
        m
        for m in prepared.messages
        if isinstance(m.content, str)
        and m.content.startswith(chat_context.CONTEXT_SUMMARY_PREFIX)
    )
    assert "extended summary" in summary_msg_out.content
    tail_contents = [m.content for m in prepared.messages]
    assert "tail q" in tail_contents
    assert "tail a" in tail_contents
    assert "to summarize q" not in tail_contents


# ---------- Fail fast: protected payload alone over budget ----------


@pytest.mark.anyio
async def test_protected_payload_over_budget_fails_fast(monkeypatch):
    """Protected payload over budget raises before the summarizer runs."""
    agent = _agent()
    conversation = _conversation()
    summarize_calls = 0
    old_round = uuid4()
    rows = [
        _row(ConversationMessageRole.USER, "old q", round_id=old_round),
        _row(
            ConversationMessageRole.ASSISTANT,
            "old a",
            round_id=old_round,
            is_canonical=True,
        ),
    ]
    old_msgs = [
        Message(role=MessageRole.USER, content="old q"),
        Message(role=MessageRole.ASSISTANT, content="old a"),
    ]
    messages = [SYSTEM, *old_msgs, CURRENT]

    async def build_messages(**_kwargs):
        return messages, set(), _meta(messages, rows)

    async def summarize(**_kwargs):
        nonlocal summarize_calls
        summarize_calls += 1
        return "summary"

    def estimate(messages_, *, model_id, provider):
        del model_id, provider
        return 2_000_000

    _install(
        monkeypatch,
        build=build_messages,
        estimate=estimate,
        summarize=summarize,
    )
    plan = await chat_context.build_context_plan(
        agent=agent,
        conversation=conversation,
        user_message="current request",
        model_id="model",
        model_context_limit=10_000,
        model_max_output_tokens=512,
        include_current_user_message=True,
    )
    with pytest.raises(ContextLengthError) as exc_info:
        await plan.finalize()
    assert exc_info.value.details["reason"] == "protected_payload_over_budget"
    assert summarize_calls == 0


# ---------- Source tokens measure newly covered only ----------


@pytest.mark.anyio
async def test_summary_source_tokens_cover_only_newly_summarized(monkeypatch):
    """summary_source_tokens reflects only the newly summarized old turns."""
    agent = _agent()
    conversation = _conversation()
    conversation.context_summary_text = "previous summary"
    conversation.context_summary_watermark_id = uuid4()
    sum_round_id = uuid4()
    rows = [
        _row(ConversationMessageRole.USER, "new q", round_id=sum_round_id),
        _row(
            ConversationMessageRole.ASSISTANT,
            "new a",
            round_id=sum_round_id,
            is_canonical=True,
        ),
    ]
    sys = Message(role=MessageRole.SYSTEM, content="system")
    summary_msg = Message(
        role=MessageRole.USER,
        content=f"{chat_context.CONTEXT_SUMMARY_PREFIX}\n\nprevious summary",
    )
    sum_msgs = [
        Message(role=MessageRole.USER, content="new q"),
        Message(role=MessageRole.ASSISTANT, content="new a"),
    ]
    messages = [sys, summary_msg, *sum_msgs, CURRENT]

    def build_meta():
        meta = [{"role": "system", "round_id": None, "source_message_id": None}]
        meta.append(
            {
                "role": "user",
                "round_id": None,
                "source_role": "summary",
                "source_message_id": None,
            }
        )
        meta.extend(
            {
                "role": "user" if i == 0 else "assistant",
                "round_id": sum_round_id,
                "round_role": "user_input" if i == 0 else "assistant_final",
                "is_round_canonical": True,
                "tool_calls": [],
                "source_role": "user" if i == 0 else "assistant",
                "source_message_id": rows[i].id,
            }
            for i in range(len(rows))
        )
        return meta

    async def build_messages(**_kwargs):
        return messages, set(), build_meta()

    async def summarize(**_kwargs):
        return "extended summary"

    def estimate(messages_, *, model_id, provider):
        del model_id, provider
        # new messages oversized (44k each) to cross the 85k reserve trigger;
        # the previous summary stays small and is never counted as source.
        return sum(
            100
            if getattr(m, "content", "") in ("system", "current request")
            else 1000
            if isinstance(getattr(m, "content", ""), str)
            and getattr(m, "content", "").startswith(
                chat_context.CONTEXT_SUMMARY_PREFIX
            )
            else 44_000
            for m in messages_
        )

    _install(
        monkeypatch,
        build=build_messages,
        estimate=estimate,
        summarize=summarize,
    )
    monkeypatch.setattr(chat_context, "is_message_on_active_branch", async_lambda_true)
    plan = await chat_context.build_context_plan(
        agent=agent,
        conversation=conversation,
        user_message="current request",
        model_id="model",
        model_context_limit=100_000,
        model_max_output_tokens=1000,
        include_current_user_message=True,
        current_user_message_id=uuid4(),
    )
    prepared = await plan.finalize()

    assert prepared.compression.stage == "macro"
    # Both new messages (44k each) are counted; the previous summary is not.
    assert prepared.compression.summary_source_tokens == 88_000
