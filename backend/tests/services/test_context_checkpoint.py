"""Active-round semantic compaction checkpoint behaviour.

Covered guarantees: complete tool groups only, a real LLM summary of exactly
the covered results (never a truncated prefix), explicit readback fallback when
summarizing is impossible, per-result outcome and ref, durable-run scoping,
branch/version validation, and fail-safe persistence that never edits records
or advances the summary watermark.
"""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.errors import ContextLengthError
from app.llm.types import FunctionCall, Message, MessageRole, ToolCall
from app.schemas.response import BusinessError
from app.services import chat_context, context_checkpoint
from app.services.context_checkpoint import (
    LoadedCheckpoint,
    ToolResultSource,
    content_version_hash,
    valid_entry,
)

ROUND = uuid4()
SUMMARY = "Goal: finish the task. Done: edit a.py succeeded; bash failed with permission denied."
SOURCE_HASH = content_version_hash("user goal + assistant calls + tool results")


def _call(call_id: str, name: str = "bash") -> ToolCall:
    return ToolCall(id=call_id, function=FunctionCall(name=name, arguments="{}"))


def _large_result(marker: str, *, success: bool | None = None) -> str:
    payload: dict[str, object] = {"detail": f"{marker}-" + ("x" * 2000)}
    if success is not None:
        payload["success"] = success
    return json.dumps(payload)


def _exchange(
    call_id: str,
    content: str,
    *,
    round_id=ROUND,
    tool_name: str = "bash",
) -> tuple[list[Message], list[dict]]:
    return (
        [
            Message(
                role=MessageRole.ASSISTANT,
                content="",
                tool_calls=[_call(call_id, tool_name)],
            ),
            Message(
                role=MessageRole.TOOL,
                name=tool_name,
                content=content,
                tool_call_id=call_id,
            ),
        ],
        [
            {
                "role": "assistant",
                "round_id": round_id,
                "tool_calls": [{"id": call_id}],
            },
            {"role": "tool", "round_id": round_id, "tool_call_id": call_id},
        ],
    )


def _build_view(exchanges):
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="start the task"),
    ]
    meta: list[dict] = [
        {"role": "system", "round_id": None},
        {"role": "user", "round_id": ROUND, "source_message_id": uuid4()},
    ]
    contents: dict[str, str] = {}
    for call_id, content in exchanges:
        chunk, chunk_meta = _exchange(call_id, content)
        messages.extend(chunk)
        meta.extend(chunk_meta)
        contents[call_id] = content
    return messages, meta, contents


@pytest.mark.anyio
async def test_plan_reuses_checkpoint_before_deciding_pressure(monkeypatch):
    messages, meta, contents = _build_view(
        [(f"c{i}", _large_result(f"r{i}")) for i in range(4)]
    )
    entries = {
        call_id: context_checkpoint.build_entry(
            ToolResultSource(
                tool_call_id=call_id,
                tool_name="bash",
                content=contents[call_id],
                round_id=ROUND,
            )
        )
        for call_id in ("c0", "c1")
    }
    loaded = LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries=entries)
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    saved = _patch_checkpoint_io(monkeypatch, loaded=loaded, versions=versions)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)

    async def build(**kwargs):
        return list(messages), set(), list(meta)

    monkeypatch.setattr(chat_context, "_build_messages_with_file_content", build)
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4(), context_compression_config={})
    conversation = SimpleNamespace(
        id=uuid4(), context_summary_text=None, context_summary_watermark_id=None
    )

    async def prepare():
        plan = await chat_context.build_context_plan(
            agent=agent,
            conversation=conversation,
            user_message="start the task",
            model_id="test",
            model_context_limit=1800,
            model_max_output_tokens=100,
            protected_round_id=ROUND,
            history_override=[],
        )
        return await plan.finalize()

    first = await prepare()
    second = await prepare()
    assert [m.model_dump() for m in first.messages] == [
        m.model_dump() for m in second.messages
    ]
    assert first.messages[3].content == context_checkpoint.omission_marker(
        entries["c0"]["ref"]
    )
    assert first.compression.stage == second.compression.stage == "none"
    assert saved == []
    assert messages[3].content == contents["c0"]


@pytest.mark.anyio
async def test_extension_keeps_previously_applied_markers_identical(monkeypatch):
    messages, meta, contents = _build_view(
        [(f"c{i}", _large_result(f"r{i}")) for i in range(6)]
    )
    entries = {
        call_id: context_checkpoint.build_entry(
            ToolResultSource(
                tool_call_id=call_id,
                tool_name="bash",
                content=contents[call_id],
                round_id=ROUND,
            )
        )
        for call_id in ("c0", "c1")
    }
    loaded = LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries=entries)
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    calls = _patch_summarizer(monkeypatch)
    _patch_checkpoint_io(monkeypatch, loaded=loaded, versions=versions)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    plan = _plan(messages, meta)

    restored = await chat_context._restore_round_checkpoint(
        list(messages), list(meta), uuid4(), ROUND, 1
    )
    compacted = await chat_context._compact_active_round(
        list(messages),
        list(meta),
        agent=plan.agent,
        conversation=plan.conversation,
        conversation_id=plan.conversation.id,
        current_user_index=1,
        active_round_id=ROUND,
        budget=plan.trigger_budget,
        hard_budget=100_000,
        tool_definition_tokens=0,
        model_id="test",
        tokenizer_model_id="test",
        provider=None,
    )

    view = [message.content for message in compacted.messages]
    assert len(calls) == 1
    assert view[3] == restored[3].content
    assert view[5] == restored[5].content
    # The semantic marker goes to a newly covered result so the earlier prefix
    # (already compacted results) stays byte-identical and cacheable.
    assert view[7].startswith("[Active-round semantic checkpoint")


def _estimate(messages, **_kwargs) -> int:
    return sum(
        len(message.content) // 10 + 1
        for message in messages
        if isinstance(message.content, str)
    )


def _plan(
    messages,
    meta,
    *,
    current_user_index: int = 1,
    active_round=ROUND,
    trigger_budget: int = 100,
    input_budget: int = 100_000,
):
    return chat_context.ContextPlan(
        agent=SimpleNamespace(id=uuid4(), team_id=uuid4()),
        conversation=SimpleNamespace(
            id=uuid4(),
            context_summary_text=None,
            context_summary_watermark_id=None,
        ),
        messages=list(messages),
        protected_indexes=set(),
        token_budget=chat_context.TokenBudget(
            context_limit=input_budget + 5_000,
            output_reserve=4_000,
            safety_margin=1_000,
            input_budget=input_budget,
        ),
        compression=chat_context.CompressionMeta(
            stage="none",
            before_tokens=10_000,
            after_tokens=10_000,
            input_budget=input_budget,
        ),
        compression_config={"enabled": True, "summary_max_tokens": 1000},
        compression_enabled=True,
        trigger_budget=trigger_budget,
        current_user_index=current_user_index,
        tail_start_index=current_user_index,
        summarized=[],
        previous_summary_text=None,
        meta=list(meta),
        will_summarize=False,
        model_id="model",
        tokenizer_model_id=None,
        provider=None,
        tool_definition_tokens=0,
        history_override_is_none=True,
        current_user_message_id=None,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        protected_round_id=active_round,
    )


def _patch_summarizer(monkeypatch, *, summary: str | None = SUMMARY, fail=False):
    calls: list[dict] = []

    async def summarize(**kwargs):
        calls.append(kwargs)
        if fail:
            raise BusinessError(msg_key="context_summarization_failed")
        return summary

    monkeypatch.setattr(chat_context, "_summarize_context", summarize)
    return calls


def _patch_checkpoint_io(
    monkeypatch,
    *,
    loaded: LoadedCheckpoint | None,
    versions: dict[str, str | None] | None,
    save_error: Exception | None = None,
):
    saved: list[dict] = []

    async def load(**kwargs):
        assert kwargs["round_id"] == ROUND
        return loaded

    async def version_hashes(**kwargs):
        return versions

    async def save(**kwargs):
        if save_error is not None:
            raise save_error
        saved.append(kwargs)
        return "updated"

    monkeypatch.setattr(context_checkpoint, "load_round_checkpoint", load)
    monkeypatch.setattr(
        context_checkpoint, "active_branch_version_hashes", version_hashes
    )
    monkeypatch.setattr(context_checkpoint, "save_round_checkpoint", save)
    return saved


# ---------------------------------------------------------------------------
# Pure entry / marker semantics
# ---------------------------------------------------------------------------


def test_entry_reports_real_outcome_and_requires_readback():
    failed = context_checkpoint.build_entry(
        ToolResultSource(
            tool_call_id="call-1",
            tool_name="bash",
            content='{"success": false, "error": "permission denied"}',
            round_id=ROUND,
        )
    )
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["ref"].startswith(f"tr1:{ROUND}:call-1")
    assert failed["content_sha256"] == content_version_hash(
        '{"success": false, "error": "permission denied"}'
    )

    succeeded = context_checkpoint.build_entry(
        ToolResultSource(
            tool_call_id="call-2",
            tool_name="edit",
            content='{"success": true, "path": "a.py"}',
            round_id=ROUND,
        )
    )
    assert succeeded is not None and succeeded["status"] == "succeeded"

    unconfirmed = context_checkpoint.build_entry(
        ToolResultSource(
            tool_call_id="call-3",
            tool_name="custom",
            content='{"rows": [1, 2, 3]}',
            round_id=ROUND,
        )
    )
    assert unconfirmed is not None and unconfirmed["status"] == "unconfirmed"

    assert (
        context_checkpoint.build_entry(
            ToolResultSource(
                tool_call_id="view-1",
                tool_name="view_asset",
                content="asset",
                round_id=ROUND,
            )
        )
        is None
    )
    assert (
        context_checkpoint.build_entry(
            ToolResultSource(
                tool_call_id="call-4",
                tool_name="bash",
                content="result",
                round_id="",
            )
        )
        is None
    )


def test_semantic_marker_is_explicit_and_lists_outcomes_and_refs():
    entries = [
        {
            "tool_call_id": "call-1",
            "tool_name": "bash",
            "status": "failed",
            "ref": f"tr1:{ROUND}:call-1",
        },
        {
            "tool_call_id": "call-2",
            "tool_name": "edit",
            "status": "succeeded",
            "ref": f"tr1:{ROUND}:call-2",
        },
    ]
    marker = context_checkpoint.semantic_marker(SUMMARY, entries)
    assert marker.startswith("[Active-round semantic checkpoint")
    assert SUMMARY in marker
    assert "outcome=failed" in marker
    assert "outcome=succeeded" in marker
    assert f"ref=tr1:{ROUND}:call-1" in marker
    assert f"ref=tr1:{ROUND}:call-2" in marker
    assert "may omit detail" in marker

    omitted = context_checkpoint.omission_marker(f"tr1:{ROUND}:call-1")
    assert "Do not assume its contents" in omitted
    assert SUMMARY not in omitted


def test_valid_entry_binds_round_call_and_content_hash():
    entry = context_checkpoint.build_entry(
        ToolResultSource(
            tool_call_id="call-5",
            tool_name="bash",
            content='{"success": true}',
            round_id=ROUND,
        )
    )
    assert entry is not None
    assert valid_entry(entry, round_id=ROUND)
    assert valid_entry(entry, round_id=ROUND, expected_tool_call_id="call-5")
    assert not valid_entry(entry, round_id=ROUND, expected_tool_call_id="other")
    assert not valid_entry(entry, round_id=uuid4())
    assert not valid_entry({**entry, "content_sha256": "short"}, round_id=ROUND)


# ---------------------------------------------------------------------------
# Group boundaries
# ---------------------------------------------------------------------------


def test_parallel_group_needs_every_result_and_stays_in_one_round():
    calls = [_call("p1"), _call("p2")]
    messages = [
        Message(role=MessageRole.ASSISTANT, content="", tool_calls=calls),
        Message(role=MessageRole.TOOL, content="r1", tool_call_id="p1"),
    ]
    meta = [
        {"role": "assistant", "round_id": ROUND},
        {"role": "tool", "round_id": ROUND},
    ]
    assert (
        chat_context._complete_tool_groups(
            messages, meta, current_user_index=0, active_round_id=ROUND
        )
        == []
    )
    messages.append(Message(role=MessageRole.TOOL, content="r2", tool_call_id="p2"))
    meta.append({"role": "tool", "round_id": ROUND})
    groups = chat_context._complete_tool_groups(
        messages, meta, current_user_index=0, active_round_id=ROUND
    )
    assert groups[0]["result_indexes"] == [1, 2]
    assert groups[0]["call_ids"] == ["p1", "p2"]

    broken = [dict(entry) for entry in meta]
    broken[2]["round_id"] = uuid4()
    assert (
        chat_context._complete_tool_groups(
            messages, broken, current_user_index=0, active_round_id=ROUND
        )
        == []
    )
    # Both results in a different (but internally consistent) round still do
    # not belong to this assistant call.
    other_round = uuid4()
    foreign = [dict(entry) for entry in meta]
    foreign[1]["round_id"] = foreign[2]["round_id"] = other_round
    assert (
        chat_context._complete_tool_groups(
            messages, foreign, current_user_index=0, active_round_id=ROUND
        )
        == []
    )


def test_multimodal_ask_user_and_incomplete_groups_are_never_candidates():
    for tool_name, call_id in (
        ("view_asset", "v1"),
        ("ask_user", "a1"),
    ):
        chunk, chunk_meta = _exchange(call_id, "payload", tool_name=tool_name)
        assert (
            chat_context._complete_tool_groups(
                chunk, chunk_meta, current_user_index=0, active_round_id=ROUND
            )
            == []
        )
    pending = [
        Message(
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=[_call("approval-1", "ask_user")],
        )
    ]
    assert (
        chat_context._complete_tool_groups(
            pending,
            [{"role": "assistant", "round_id": ROUND}],
            current_user_index=0,
            active_round_id=ROUND,
        )
        == []
    )


def test_steering_keeps_same_round_groups_but_not_previous_rounds():
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="old round"),
    ]
    meta = [
        {"role": "system", "round_id": None},
        {"role": "user", "round_id": "old"},
    ]
    for call_id, round_id in (("old-1", "old"), ("new-1", ROUND), ("new-2", ROUND)):
        chunk, chunk_meta = _exchange(call_id, "result", round_id=round_id)
        messages.extend(chunk)
        meta.extend(chunk_meta)
    messages.append(Message(role=MessageRole.USER, content="steer"))
    meta.append({"role": "user", "round_id": ROUND, "round_role": "user_input"})
    groups = chat_context._complete_tool_groups(
        messages,
        meta,
        current_user_index=len(messages) - 1,
        active_round_id=ROUND,
    )
    assert [group["call_ids"] for group in groups] == [["new-1"], ["new-2"]]


def test_compaction_keeps_latest_two_groups_and_pending_untouched():
    exchanges = [(f"c{i}", _large_result(f"r{i}")) for i in range(4)]
    messages, meta, contents = _build_view(exchanges)
    messages.append(
        Message(
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=[_call("pending-1", "ask_user")],
        )
    )
    meta.append({"role": "assistant", "round_id": ROUND})
    original = list(messages)
    replacements = {
        call_id: context_checkpoint.omission_marker(f"tr1:{ROUND}:{call_id}")
        for call_id in contents
    }
    reduced, changed, covered = chat_context._compact_tool_groups(
        messages,
        meta,
        budget=10,
        hard_budget=100_000,
        tool_definition_tokens=0,
        current_user_index=1,
        model_id=None,
        provider=None,
        replacements=replacements,
        active_round_id=ROUND,
    )
    assert changed
    assert [reduced[index].tool_call_id for index in covered] == ["c0", "c1"]
    assert reduced[1].content == "start the task"
    assert [m.tool_call_id for m in reduced if m.role == MessageRole.TOOL] == [
        "c0",
        "c1",
        "c2",
        "c3",
    ]
    assert reduced[-1].content == original[-1].content


# ---------------------------------------------------------------------------
# ContextPlan integration: real summary, fallback, reuse, versions, failure
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_finalize_creates_semantic_checkpoint_for_covered_groups(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}", success=False)) for i in range(4)]
    messages, meta, contents = _build_view(exchanges)
    original = [m.content for m in messages]
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    summaries = _patch_summarizer(monkeypatch)
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    saved = _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries={}),
        versions=versions,
    )
    prepared = await _plan(messages, meta).finalize()

    assert len(summaries) == 1  # one real summary call for the covered set
    transcript = summaries[0]["messages_to_summarize"]
    assert transcript[0].role == MessageRole.USER
    assert "start the task" in transcript[0].content
    assistant_calls = [
        call.id
        for message in transcript
        if message.role == MessageRole.ASSISTANT
        for call in (message.tool_calls or ())
    ]
    # The summarizer sees the covered complete calls, never c2/c3.
    assert assistant_calls == ["c0", "c1"]
    tool_names = [
        message.name for message in transcript if message.role == MessageRole.TOOL
    ]
    assert any("call=c0" in name and "outcome=failed" in name for name in tool_names)
    assert any(f"ref=tr1:{ROUND}:c1" in name for name in tool_names)
    assert [m.content for m in messages] == original
    view = {
        message.tool_call_id: message.content
        for message in prepared.messages
        if message.role == MessageRole.TOOL
    }
    assert view["c0"].startswith("[Active-round semantic checkpoint")
    assert SUMMARY in view["c0"]
    assert "outcome=failed" in view["c0"]
    assert f"ref=tr1:{ROUND}:c0" in view["c0"]
    assert f"ref=tr1:{ROUND}:c1" in view["c0"]
    assert view["c1"].startswith("[Earlier tool result omitted")
    assert view["c2"] == contents["c2"]
    assert view["c3"] == contents["c3"]

    assert len(saved) == 1
    assert saved[0]["mode"] == "semantic"
    assert saved[0]["summary_text"] == SUMMARY
    assert saved[0]["source_sha256"] == content_version_hash(
        chat_context._render_summary_transcript(transcript)
    )
    assert [entry["tool_call_id"] for entry in saved[0]["entries"]] == ["c0", "c1"]
    assert prepared.compression.active_round_checkpoint["mode"] == "semantic"
    assert prepared.compression.active_round_checkpoint["persisted"] == "updated"
    assert "round_checkpoint_summary" in prepared.compression.actions


@pytest.mark.anyio
async def test_restored_semantic_checkpoint_requires_current_source_and_branch(
    monkeypatch,
):
    messages, meta, contents = _build_view(
        [(f"c{i}", _large_result(f"r{i}")) for i in range(3)]
    )
    entries = {
        name: context_checkpoint.build_entry(
            ToolResultSource(
                tool_call_id=name,
                tool_name="bash",
                content=contents[name],
                round_id=ROUND,
            )
        )
        for name in ("c0", "c1")
    }
    sources = {
        name: ToolResultSource(
            tool_call_id=name, tool_name="bash", content=contents[name], round_id=ROUND
        )
        for name in entries
    }
    groups = chat_context._complete_tool_groups(
        messages, meta, current_user_index=1, active_round_id=ROUND
    )
    transcript = chat_context._checkpoint_transcript(
        messages, groups, 1, entries, sources
    )
    loaded = LoadedCheckpoint(
        run_id=uuid4(),
        round_id=str(ROUND),
        entries=entries,
        mode="semantic",
        summary_text=SUMMARY,
        source_sha256=content_version_hash(
            chat_context._render_summary_transcript(transcript)
        ),
    )
    versions = {
        name: content_version_hash(content) for name, content in contents.items()
    }
    _patch_checkpoint_io(monkeypatch, loaded=loaded, versions=versions)
    restored = await chat_context._restore_round_checkpoint(
        messages, meta, uuid4(), ROUND, 1
    )
    assert SUMMARY in restored[3].content
    assert restored[5].content.startswith("[Earlier tool result omitted")
    changed_goal = list(messages)
    changed_goal[1] = messages[1].model_copy(update={"content": "different task"})
    assert (
        await chat_context._restore_round_checkpoint(
            changed_goal, meta, uuid4(), ROUND, 1
        )
        == changed_goal
    )
    versions["c0"] = content_version_hash("different result")
    assert (
        await chat_context._restore_round_checkpoint(messages, meta, uuid4(), ROUND, 1)
        == messages
    )


@pytest.mark.anyio
async def test_recovery_reuses_semantic_checkpoint_without_llm(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}", success=True)) for i in range(4)]
    messages, meta, contents = _build_view(exchanges)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    summary_calls = _patch_summarizer(monkeypatch)
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    first = await _plan(messages, meta).finalize()
    first_view = [m.content for m in first.messages]
    source_hash = content_version_hash(
        chat_context._render_summary_transcript(
            summary_calls[0]["messages_to_summarize"]
        )
    )

    entries = {
        f"c{i}": context_checkpoint.build_entry(
            ToolResultSource(
                tool_call_id=f"c{i}",
                tool_name="bash",
                content=contents[f"c{i}"],
                round_id=ROUND,
            )
        )
        for i in range(2)
    }
    loaded = LoadedCheckpoint(
        run_id=uuid4(),
        round_id=str(ROUND),
        entries=entries,
        summary_text=SUMMARY,
        mode="semantic",
        source_sha256=source_hash,
    )
    _patch_checkpoint_io(monkeypatch, loaded=loaded, versions=versions)
    forbidden = _patch_summarizer(monkeypatch, summary=None, fail=True)
    second = await _plan(messages, meta).finalize()
    assert forbidden == []  # reuse must not call the summarizer
    assert [m.content for m in second.messages] == first_view
    assert second.compression.active_round_checkpoint["summary_reused"] is True
    assert second.compression.active_round_checkpoint["mode"] == "semantic"


@pytest.mark.anyio
async def test_changed_user_goal_invalidates_summary_reuse(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}", success=True)) for i in range(4)]
    messages, meta, contents = _build_view(exchanges)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    calls = _patch_summarizer(monkeypatch, summary="summary for old goal")
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries={}),
        versions=versions,
    )
    first = await _plan(messages, meta).finalize()
    source_hash = content_version_hash(
        chat_context._render_summary_transcript(calls[0]["messages_to_summarize"])
    )
    entries = {
        f"c{i}": context_checkpoint.build_entry(
            ToolResultSource(
                tool_call_id=f"c{i}",
                tool_name="bash",
                content=contents[f"c{i}"],
                round_id=ROUND,
            )
        )
        for i in range(2)
    }
    # Same results and coverage, but the user's instruction changed.
    messages[1] = Message(role=MessageRole.USER, content="a different goal")
    fresh_calls = _patch_summarizer(monkeypatch, summary="summary for new goal")
    _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(
            run_id=uuid4(),
            round_id=str(ROUND),
            entries=entries,
            summary_text="summary for old goal",
            mode="semantic",
            source_sha256=source_hash,
        ),
        versions=versions,
    )
    second = await _plan(messages, meta).finalize()
    assert len(fresh_calls) == 1
    assert "summary for new goal" in second.messages[3].content
    assert "summary for old goal" not in second.messages[3].content
    assert first.messages is not second.messages


@pytest.mark.anyio
async def test_changed_assistant_arguments_invalidate_summary_reuse(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}", success=True)) for i in range(4)]
    messages, meta, contents = _build_view(exchanges)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    calls = _patch_summarizer(monkeypatch)
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries={}),
        versions=versions,
    )
    await _plan(messages, meta).finalize()
    source_hash = content_version_hash(
        chat_context._render_summary_transcript(calls[0]["messages_to_summarize"])
    )
    entries = {
        f"c{i}": context_checkpoint.build_entry(
            ToolResultSource(
                tool_call_id=f"c{i}",
                tool_name="bash",
                content=contents[f"c{i}"],
                round_id=ROUND,
            )
        )
        for i in range(2)
    }
    # Results are unchanged; only the recorded call arguments differ.
    messages[2] = Message(
        role=MessageRole.ASSISTANT,
        content="",
        tool_calls=[
            ToolCall(
                id="c0",
                function=FunctionCall(name="bash", arguments='{"cmd": "changed"}'),
            )
        ],
    )
    fresh_calls = _patch_summarizer(monkeypatch, summary="summary for changed call")
    _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(
            run_id=uuid4(),
            round_id=str(ROUND),
            entries=entries,
            summary_text=SUMMARY,
            mode="semantic",
            source_sha256=source_hash,
        ),
        versions=versions,
    )
    second = await _plan(messages, meta).finalize()
    assert len(fresh_calls) == 1
    assert "summary for changed call" in second.messages[3].content


@pytest.mark.anyio
async def test_semantic_marker_uses_longer_parallel_result_as_host(monkeypatch):
    short = "short-" + ("s" * 240)  # longer than a readback marker, shorter
    long = "long-" + ("x" * 8000)  # than the semantic marker
    messages, meta, contents = _build_view(
        [("c0", short), ("c1", long), ("c2", long), ("c3", long)]
    )
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    monkeypatch.setattr(chat_context, "ACTIVE_ROUND_SUMMARY_MAX_TOKENS", 50)
    calls = _patch_summarizer(monkeypatch)
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    saved = _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries={}),
        versions=versions,
    )
    prepared = await _plan(messages, meta, input_budget=20_000).finalize()
    assert len(calls) == 1
    view = {
        message.tool_call_id: message.content
        for message in prepared.messages
        if message.role == MessageRole.TOOL
    }
    # c0 is covered but too short to host the summary; c1 hosts it.
    assert view["c0"].startswith("[Earlier tool result omitted")
    assert view["c1"].startswith("[Active-round semantic checkpoint")
    assert SUMMARY in view["c1"]
    assert f"ref=tr1:{ROUND}:c0" in view["c1"]
    assert saved[0]["mode"] == "semantic"
    assert prepared.compression.active_round_checkpoint["mode"] == "semantic"


@pytest.mark.anyio
async def test_no_semantic_host_is_rechecked_each_iteration_without_cache(monkeypatch):
    # Long enough to be readback-compacted, too short for the semantic marker.
    content = "medium-" + ("m" * 280)
    messages, meta, contents = _build_view([(f"c{i}", content) for i in range(4)])
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    first_calls = _patch_summarizer(monkeypatch)
    versions = {
        call_id: content_version_hash(value) for call_id, value in contents.items()
    }
    saved = _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries={}),
        versions=versions,
    )
    first = await _plan(messages, meta, input_budget=100).finalize()
    assert first_calls == []  # no host: never call the LLM
    assert saved[0]["mode"] == "readback_only"
    assert "summary_skipped_reason" not in saved[0]
    diagnostics = first.compression.active_round_checkpoint
    assert diagnostics["reason"] == "no_semantic_host"
    assert "round_checkpoint_summary_skipped" not in first.compression.actions

    entries = {entry["tool_call_id"]: entry for entry in saved[0]["entries"]}
    loaded = LoadedCheckpoint(
        run_id=uuid4(),
        round_id=str(ROUND),
        entries=entries,
        mode="readback_only",
    )
    second_calls = _patch_summarizer(monkeypatch, fail=True)
    _patch_checkpoint_io(monkeypatch, loaded=loaded, versions=versions)
    second = await _plan(messages, meta, input_budget=100).finalize()
    assert second_calls == []  # cheap deterministic precheck, no negative cache
    assert second.compression.active_round_checkpoint["reason"] == "no_semantic_host"


@pytest.mark.anyio
async def test_budget_improvement_allows_summary_after_precheck_skip(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}")) for i in range(4)]
    messages, meta, contents = _build_view(exchanges)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    first_calls = _patch_summarizer(monkeypatch)
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    # Readback view fits, but the semantic marker cannot fit at this budget.
    saved = _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries={}),
        versions=versions,
    )
    first = await _plan(messages, meta, input_budget=200).finalize()
    assert first_calls == []
    diagnostics = first.compression.active_round_checkpoint
    assert diagnostics["reason"] == "semantic_view_over_budget"
    assert saved[0]["mode"] == "readback_only"

    # The next iteration has more room (e.g. less retained history): the same
    # source precheck now passes and the summary is attempted again.
    loaded = LoadedCheckpoint(
        run_id=uuid4(),
        round_id=str(ROUND),
        entries={entry["tool_call_id"]: entry for entry in saved[0]["entries"]},
        mode="readback_only",
    )
    second_calls = _patch_summarizer(monkeypatch, summary=SUMMARY)
    _patch_checkpoint_io(monkeypatch, loaded=loaded, versions=versions)
    second = await _plan(messages, meta, input_budget=100_000).finalize()
    assert len(second_calls) == 1
    assert second.compression.active_round_checkpoint["mode"] == "semantic"
    assert "semantic checkpoint" in second.messages[3].content


@pytest.mark.anyio
async def test_long_summary_failure_can_succeed_with_short_summary_next_time(
    monkeypatch,
):
    exchanges = [(f"c{i}", _large_result(f"r{i}")) for i in range(4)]
    messages, meta, contents = _build_view(exchanges)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    _patch_summarizer(monkeypatch, summary="long " * 6000)  # post-check host miss
    saved = _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries={}),
        versions=versions,
    )
    first = await _plan(messages, meta).finalize()
    assert first.compression.active_round_checkpoint["mode"] == "readback_only"
    assert first.compression.active_round_checkpoint["reason"] == "no_semantic_host"
    assert saved[0]["mode"] == "readback_only"

    # The failure was not cached: a later, shorter summary succeeds for the
    # unchanged source.
    loaded = LoadedCheckpoint(
        run_id=uuid4(),
        round_id=str(ROUND),
        entries={entry["tool_call_id"]: entry for entry in saved[0]["entries"]},
        mode="readback_only",
    )
    second_calls = _patch_summarizer(monkeypatch, summary=SUMMARY)
    _patch_checkpoint_io(monkeypatch, loaded=loaded, versions=versions)
    second = await _plan(messages, meta).finalize()
    assert len(second_calls) == 1
    assert second.compression.active_round_checkpoint["mode"] == "semantic"
    assert SUMMARY in second.messages[3].content


@pytest.mark.anyio
async def test_summary_failure_returns_explicit_readback_fallback(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}")) for i in range(4)]
    messages, meta, contents = _build_view(exchanges)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    _patch_summarizer(monkeypatch, fail=True)
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    saved = _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries={}),
        versions=versions,
    )
    prepared = await _plan(messages, meta).finalize()
    view = {
        message.tool_call_id: message.content
        for message in prepared.messages
        if message.role == MessageRole.TOOL
    }
    assert view["c0"].startswith("[Earlier tool result omitted")
    assert SUMMARY not in view["c0"]
    assert "semantic checkpoint" not in view["c0"]
    assert saved[0]["mode"] == "readback_only"
    assert saved[0]["summary_text"] is None
    diagnostics = prepared.compression.active_round_checkpoint
    assert diagnostics["mode"] == "readback_only"
    assert diagnostics["reason"] == "summary_failed"
    assert "round_checkpoint_readback_only" in prepared.compression.actions
    assert "round_checkpoint_summary_failed" in prepared.compression.actions


@pytest.mark.anyio
async def test_oversized_transcript_is_not_marked_covered(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}")) for i in range(4)]
    messages, meta, contents = _build_view(exchanges)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    monkeypatch.setattr(chat_context, "count_tokens", lambda *_a, **_k: 9000)
    calls = _patch_summarizer(monkeypatch)
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries={}),
        versions=versions,
    )
    prepared = await _plan(messages, meta).finalize()
    assert calls == []
    diagnostics = prepared.compression.active_round_checkpoint
    assert diagnostics["mode"] == "readback_only"
    assert diagnostics["reason"] == "summary_transcript_too_large"


@pytest.mark.anyio
async def test_changed_result_version_invalidates_stale_summary(monkeypatch):
    old_content = _large_result("old-version")
    new_content = _large_result("new-version")
    messages, meta, _contents = _build_view(
        [
            ("c0", new_content),
            ("c1", new_content),
            ("c2", new_content),
            ("c3", new_content),
        ]
    )
    stale = context_checkpoint.build_entry(
        ToolResultSource(
            tool_call_id="c0",
            tool_name="bash",
            content=old_content,
            round_id=ROUND,
        )
    )
    assert stale is not None
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    calls = _patch_summarizer(monkeypatch, summary="fresh summary")
    versions = {f"c{i}": content_version_hash(new_content) for i in range(4)}
    saved = _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(
            run_id=uuid4(),
            round_id=str(ROUND),
            entries={"c0": stale},
            summary_text="stale summary",
            mode="semantic",
        ),
        versions=versions,
    )
    prepared = await _plan(messages, meta).finalize()
    assert len(calls) == 1  # coverage/hash mismatch forces regeneration
    first = prepared.messages[3].content
    assert "fresh summary" in first
    assert "stale summary" not in first
    assert prepared.compression.active_round_checkpoint["invalidated_entries"] == 1
    assert saved[0]["summary_text"] == "fresh summary"


@pytest.mark.anyio
async def test_version_mismatch_downgrades_summary_to_readback(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}")) for i in range(4)]
    messages, meta, contents = _build_view(exchanges)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    _patch_summarizer(monkeypatch)
    versions = {
        call_id: content_version_hash("a newer concurrent result")
        for call_id in contents
    }
    saved = _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries={}),
        versions=versions,
    )
    prepared = await _plan(messages, meta).finalize()
    assert saved == []  # never persist a summary whose coverage is unverified
    diagnostics = prepared.compression.active_round_checkpoint
    # The live view keeps the honestly generated summary; nothing is stored.
    assert diagnostics["mode"] == "semantic"
    assert diagnostics["persisted"] == "not_persisted"
    assert diagnostics["reason"] == "semantic_coverage_unverified"
    assert "round_checkpoint_version_mismatch" in prepared.compression.actions


@pytest.mark.anyio
async def test_persist_failure_degrades_without_touching_records(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}")) for i in range(4)]
    messages, meta, contents = _build_view(exchanges)
    original = [m.content for m in messages]
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    _patch_summarizer(monkeypatch)
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    saved = _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries={}),
        versions=versions,
        save_error=RuntimeError("db down"),
    )
    plan = _plan(messages, meta)
    prepared = await plan.finalize()
    assert saved == []
    assert [m.content for m in messages] == original
    assert plan.conversation.context_summary_watermark_id is None
    assert prepared.compression.active_round_checkpoint["persisted"] == "failed"
    assert "round_checkpoint_persist_failed" in prepared.compression.actions
    assert prepared.messages[3].content.startswith("[Active-round semantic checkpoint")


@pytest.mark.anyio
async def test_irreducible_context_raises_without_persisting(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}")) for i in range(4)]
    messages, meta, contents = _build_view(exchanges)
    monkeypatch.setattr(
        chat_context, "_estimate_message_tokens", lambda *_args, **_kwargs: 50_000
    )
    _patch_summarizer(monkeypatch)
    versions = {
        call_id: content_version_hash(content) for call_id, content in contents.items()
    }
    saved = _patch_checkpoint_io(
        monkeypatch,
        loaded=LoadedCheckpoint(run_id=uuid4(), round_id=str(ROUND), entries={}),
        versions=versions,
    )
    with pytest.raises(ContextLengthError, match="protected payload"):
        await _plan(messages, meta, input_budget=1_000).finalize()
    assert saved == []


@pytest.mark.anyio
async def test_without_durable_run_stays_request_local(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}")) for i in range(4)]
    messages, meta, _contents = _build_view(exchanges)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    _patch_summarizer(monkeypatch)
    saved = _patch_checkpoint_io(monkeypatch, loaded=None, versions=None)
    prepared = await _plan(messages, meta).finalize()
    assert saved == []  # no run payload can be verified, so nothing is written
    diagnostics = prepared.compression.active_round_checkpoint
    assert diagnostics["persisted"] == "unverified"
    assert diagnostics["reason"] == "active_branch_version_unknown"
    assert diagnostics["mode"] == "semantic"
    assert "round_checkpoint_not_persisted" in prepared.compression.actions


@pytest.mark.anyio
async def test_no_durable_round_keeps_summary_request_local(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}")) for i in range(4)]
    messages, meta, _contents = _build_view(exchanges)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    _patch_summarizer(monkeypatch)

    async def forbidden(**_kwargs):
        raise AssertionError("no run payload may be touched without a durable round")

    monkeypatch.setattr(context_checkpoint, "load_round_checkpoint", forbidden)
    monkeypatch.setattr(context_checkpoint, "save_round_checkpoint", forbidden)
    prepared = await _plan(messages, meta, active_round=None).finalize()
    diagnostics = prepared.compression.active_round_checkpoint
    assert diagnostics["mode"] == "semantic"
    assert diagnostics["persisted"] == "not_persisted"
    assert diagnostics["reason"] == "no_durable_run"


@pytest.mark.anyio
async def test_disabled_compression_skips_summary_and_checkpoint(monkeypatch):
    exchanges = [(f"c{i}", _large_result(f"r{i}")) for i in range(4)]
    messages, meta, _contents = _build_view(exchanges)
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)

    async def forbidden(**_kwargs):
        raise AssertionError("no summarizer/checkpoint IO when compression is disabled")

    monkeypatch.setattr(chat_context, "_summarize_context", forbidden)
    monkeypatch.setattr(context_checkpoint, "load_round_checkpoint", forbidden)
    monkeypatch.setattr(context_checkpoint, "save_round_checkpoint", forbidden)
    plan = _plan(messages, meta)
    plan.compression_enabled = False
    prepared = await plan.finalize()
    assert [m.content for m in prepared.messages] == [m.content for m in messages]
    assert prepared.compression.active_round_checkpoint is None


@pytest.mark.anyio
async def test_pending_group_is_never_covered(monkeypatch):
    messages, meta, _contents = _build_view([("done", _large_result("x"))])
    messages.append(
        Message(
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=[_call("approval-1", "ask_user")],
        )
    )
    meta.append({"role": "assistant", "round_id": ROUND})
    monkeypatch.setattr(chat_context, "_estimate_message_tokens", _estimate)
    _patch_summarizer(monkeypatch)
    prepared = await _plan(messages, meta).finalize()
    assert prepared.messages[-1].role == MessageRole.ASSISTANT
    assert prepared.messages[-1].tool_calls[0].id == "approval-1"
    assert prepared.compression.active_round_checkpoint is None


# ---------------------------------------------------------------------------
# Durable payload merge/load (fake ORM; no DDL or real run writes)
# ---------------------------------------------------------------------------


class _FakeQuery:
    def __init__(self, run):
        self._run = run

    def filter(self, **_kwargs):
        return self

    def using_db(self, _conn):
        return self

    def select_for_update(self):
        return self

    def order_by(self, *_args):
        return self

    def only(self, *_args):
        return self

    async def first(self):
        return self._run


class _FakeRun:
    def __init__(self, *, payload, active_round_id=ROUND):
        self.id = uuid4()
        self.worker_payload = payload
        self.active_round_id = active_round_id
        self.updated_at = None
        self.saved = False
        self.update_fields = None

    async def save(self, *, using_db=None, update_fields=None):
        assert using_db is not None
        self.saved = True
        self.update_fields = update_fields


def _patch_agent_run(monkeypatch, run):
    from contextlib import asynccontextmanager

    import tortoise.transactions
    from app.models import agent_run as agent_run_module

    class FakeAgentRun:
        @classmethod
        def filter(cls, **_kwargs):
            return _FakeQuery(run)

    @asynccontextmanager
    async def fake_transaction():
        yield object()

    monkeypatch.setattr(agent_run_module, "AgentRun", FakeAgentRun)
    monkeypatch.setattr(tortoise.transactions, "in_transaction", fake_transaction)


def _entry(call_id: str = "call-1", content: str = '{"success": true}'):
    entry = context_checkpoint.build_entry(
        ToolResultSource(
            tool_call_id=call_id,
            tool_name="bash",
            content=content,
            round_id=ROUND,
        )
    )
    assert entry is not None
    return entry


@pytest.mark.anyio
async def test_save_merges_semantic_payload_under_lock(monkeypatch):
    entry = _entry()
    run = _FakeRun(
        payload={
            "history_override": [{"role": "user", "content": "keep me"}],
            "active_round_checkpoint": {
                "version": 3,
                "round_id": str(ROUND),
                "entries": [],
            },
        }
    )
    _patch_agent_run(monkeypatch, run)
    status = await context_checkpoint.save_round_checkpoint(
        conversation_id=uuid4(),
        round_id=ROUND,
        entries=[entry],
        summary_text=SUMMARY,
        mode="semantic",
        source_sha256=SOURCE_HASH,
    )
    assert status == "updated"
    assert run.saved
    assert run.update_fields == ["worker_payload", "updated_at"]
    assert run.worker_payload["history_override"] == [
        {"role": "user", "content": "keep me"}
    ]
    stored = run.worker_payload["active_round_checkpoint"]
    assert stored["mode"] == "semantic"
    assert stored["summary_text"] == SUMMARY
    assert stored["source_sha256"] == SOURCE_HASH
    assert stored["entries"][0]["tool_call_id"] == "call-1"


@pytest.mark.anyio
async def test_save_is_idempotent_for_identical_checkpoint(monkeypatch):
    entry = _entry()
    previous = context_checkpoint.build_payload(
        round_id=ROUND,
        entries=[entry],
        summary_text=SUMMARY,
        mode="semantic",
        source_sha256=SOURCE_HASH,
    )
    run = _FakeRun(payload={"active_round_checkpoint": previous})
    _patch_agent_run(monkeypatch, run)
    status = await context_checkpoint.save_round_checkpoint(
        conversation_id=uuid4(),
        round_id=ROUND,
        entries=[entry],
        summary_text=SUMMARY,
        mode="semantic",
        source_sha256=SOURCE_HASH,
        previous=previous,
    )
    assert status == "unchanged"
    assert not run.saved


@pytest.mark.anyio
async def test_save_refuses_when_run_round_moved(monkeypatch):
    run = _FakeRun(payload={}, active_round_id=uuid4())
    _patch_agent_run(monkeypatch, run)
    status = await context_checkpoint.save_round_checkpoint(
        conversation_id=uuid4(),
        round_id=ROUND,
        entries=[],
        summary_text=None,
        mode="readback_only",
    )
    assert status == "no_run"
    assert not run.saved


@pytest.mark.anyio
async def test_load_validates_round_and_payload_mode(monkeypatch):
    good = _entry()
    run = _FakeRun(
        payload={
            "active_round_checkpoint": {
                "version": 3,
                "round_id": str(ROUND),
                "mode": "semantic",
                "summary_text": SUMMARY,
                "source_sha256": SOURCE_HASH,
                "entries": [
                    good,
                    {"tool_call_id": "call-2", "ref": "not-a-ref", "status": "failed"},
                ],
            }
        }
    )
    _patch_agent_run(monkeypatch, run)
    loaded = await context_checkpoint.load_round_checkpoint(
        conversation_id=uuid4(), round_id=ROUND
    )
    assert loaded is not None
    assert set(loaded.entries) == {"call-1"}
    assert loaded.invalid_entries == 1
    assert loaded.mode == "semantic"
    assert loaded.summary_text == SUMMARY
    assert loaded.source_sha256 == SOURCE_HASH

    wrong_round = await context_checkpoint.load_round_checkpoint(
        conversation_id=uuid4(), round_id=uuid4()
    )
    assert wrong_round is not None and wrong_round.entries == {}


class _FakeMessageQuery:
    def __init__(self, rows):
        self._rows = rows

    def order_by(self, *_args):
        return self

    def only(self, *_args):
        return self

    def __await__(self):
        async def rows():
            return self._rows

        return rows().__await__()


@pytest.mark.anyio
async def test_active_branch_version_uses_newest_result_generation(monkeypatch):
    from app.models import agent as agent_module
    from app.services.tool_result_readback import model_visible_tool_result

    newest = '{"success": true, "version": 2}'
    rows = [
        SimpleNamespace(tool_call_id="call-1", tool_name="bash", content=newest),
        SimpleNamespace(
            tool_call_id="call-1",
            tool_name="bash",
            content='{"success": true, "version": 1}',
        ),
    ]

    class FakeMessage:
        @classmethod
        def filter(cls, **_kwargs):
            return _FakeMessageQuery(rows)

    monkeypatch.setattr(agent_module, "Message", FakeMessage)
    versions = await context_checkpoint.active_branch_version_hashes(
        conversation_id=uuid4(), round_id=ROUND, tool_call_ids=["call-1"]
    )
    assert versions == {
        "call-1": content_version_hash(model_visible_tool_result(newest, "bash"))
    }


# ---------------------------------------------------------------------------
# Historical summary boundary
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_history_summary_never_covers_the_live_active_round(monkeypatch):
    old = [
        Message(role=MessageRole.USER, content="old request"),
        Message(role=MessageRole.ASSISTANT, content="old answer"),
    ]
    active_messages, active_meta = _exchange("live", _large_result("live"))
    steer = Message(role=MessageRole.USER, content="steer")
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        *old,
        Message(role=MessageRole.USER, content="active request"),
        *active_messages,
        steer,
    ]
    meta = [
        {"role": "system", "round_id": None},
        {"role": "user", "round_id": "old", "source_message_id": uuid4()},
        {"role": "assistant", "round_id": "old", "source_message_id": uuid4()},
        {"role": "user", "round_id": ROUND, "source_message_id": uuid4()},
        *active_meta,
        {"role": "user", "round_id": ROUND, "round_role": "user_input"},
    ]

    async def build(**_kwargs):
        return messages, set(), meta

    monkeypatch.setattr(chat_context, "_build_messages_with_file_content", build)
    monkeypatch.setattr(
        chat_context, "_estimate_message_tokens", lambda *_a, **_k: 99_000
    )
    plan = await chat_context.build_context_plan(
        agent=SimpleNamespace(
            id=uuid4(),
            team_id=uuid4(),
            system_prompt="",
            enable_memory=False,
            tools_config=[],
            context_compression_config={},
        ),
        conversation=SimpleNamespace(
            id=uuid4(),
            variables={},
            context_summary_text=None,
            context_summary_watermark_id=None,
        ),
        user_message="steer",
        model_id="model",
        model_context_limit=10_000,
        model_max_output_tokens=1_000,
        include_current_user_message=True,
        protected_round_id=ROUND,
    )
    active_start = next(
        index for index, entry in enumerate(meta) if entry.get("round_id") == ROUND
    )
    assert plan.tail_start_index == active_start
    assert all(
        message.content in {"old request", "old answer"} for message in plan.summarized
    )
    assert all("live" not in message.content for message in plan.summarized)
