"""Focused regression tests for the context-loop fix.

Covers the 53272312 failure shape: few USER turns with a very long in-round
tool loop must never collapse the request context to [system, current].
"""

import asyncio
import hashlib
from types import SimpleNamespace

from app.llm.types import Message, MessageRole, ToolCall, FunctionCall
from app.services import chat_context as cc
from app.services.tool_step_compaction import (
    TOOL_PROGRESS_SUMMARY_PREFIX,
    compact_round_tool_steps,
)


def _agent():
    return SimpleNamespace(
        id="a-1",
        team_id="t-1",
        name="agent",
        context_compression_config={},
    )


def _conversation(persisted=None):
    conv = SimpleNamespace(id="c-1")
    if persisted is not None:
        conv.context_summary_text = persisted
        conv.context_summary_watermark_id = "wm-1"
    return conv


def _call(name, args, call_id):
    return ToolCall(
        id=call_id, type="function", function=FunctionCall(name=name, arguments=args)
    )


def _pair(i, blob_repeats=1):
    call_id = f"call-{i}"
    blob = hashlib.md5(str(i).encode()).hexdigest() * blob_repeats
    assistant = Message(
        role=MessageRole.ASSISTANT,
        content="",
        tool_calls=[_call("inspect_asset", f'{{"ref": "r{i}"}}', call_id)],
    )
    tool = Message(
        role=MessageRole.TOOL,
        content=f'{{"ref": "r{i}", "blob": "{blob}"}}',
        tool_call_id=call_id,
    )
    return assistant, tool


# ---------------------------------------------------------------------------
# compact_round_tool_steps
# ---------------------------------------------------------------------------


def test_compaction_replaces_old_pairs_and_keeps_tail():
    steps = []
    for i in range(6):
        a, t = _pair(i)
        steps.extend([a, t])
    result = compact_round_tool_steps(steps, keep_recent_steps=4)
    assert result.changed
    summary = result.messages[result.summary_rel]
    assert summary.role == MessageRole.ASSISTANT
    assert summary.content.startswith(TOOL_PROGRESS_SUMMARY_PREFIX)
    assert "inspect_asset" in summary.content
    tail = result.messages[result.tail_start_rel :]
    assert tail == steps[-4:]
    roles = [m.role for m in result.messages[: result.summary_rel]]
    assert MessageRole.TOOL not in roles


def test_compaction_keeps_incomplete_tail_intact():
    a1, t1 = _pair(1)
    pending = Message(
        role=MessageRole.ASSISTANT,
        content="",
        tool_calls=[_call("bash", "{}", "call-pending")],
    )
    steps = [a1, t1, pending]
    result = compact_round_tool_steps(steps, keep_recent_steps=4)
    assert not result.changed
    assert result.messages == steps


def test_compaction_idempotent():
    steps = []
    for i in range(8):
        a, t = _pair(i)
        steps.extend([a, t])
    first = compact_round_tool_steps(steps, keep_recent_steps=4)
    second = compact_round_tool_steps(first.messages, keep_recent_steps=4)
    assert not second.changed


# ---------------------------------------------------------------------------
# build_context_plan / finalize
# ---------------------------------------------------------------------------


def _patch_builder(monkeypatch, messages, protected):
    async def fake_builder(**kwargs):
        return list(messages), set(protected)

    monkeypatch.setattr(cc, "_build_messages_with_file_content", fake_builder)


def _patch_summarizer(monkeypatch, text):
    calls = {"n": 0}

    async def fake_summarize(**kwargs):
        calls["n"] += 1
        return text

    async def fake_persist(**kwargs):
        return None

    monkeypatch.setattr(cc, "_summarize_context", fake_summarize)
    monkeypatch.setattr(cc, "_persist_context_summary", fake_persist)
    return calls


def _plan_kwargs(**overrides):
    kwargs = dict(
        agent=_agent(),
        conversation=_conversation(),
        user_message="继续",
        model_id="test-model",
        model_context_limit=100000,
        model_max_output_tokens=100000,
        provider="custom",
        protected_round_id="round-1",
        tool_definition_tokens=0,
    )
    kwargs.update(overrides)
    return kwargs


def test_retention_budget_advances_keep_start(monkeypatch):
    huge = hashlib.md5(b"turn").hexdigest() * 800
    filler = [Message(role=MessageRole.ASSISTANT, content=huge) for _ in range(5)]
    messages = [Message(role=MessageRole.SYSTEM, content="sys")]
    for _turn in range(3):
        messages.append(Message(role=MessageRole.USER, content=huge))
        messages.extend(filler)
    messages.append(Message(role=MessageRole.USER, content="当前请求"))
    _patch_builder(monkeypatch, messages, set())
    calls = _patch_summarizer(monkeypatch, "摘要内容")
    plan = asyncio.run(cc.build_context_plan(**_plan_kwargs()))
    # 3 轮全部保留会远超 30% 预算 → keep_start 前移，最老轮进入摘要区
    assert plan.keep_start > 1
    assert plan.will_summarize
    assert len(plan.summarized) >= 2

    prepared = asyncio.run(plan.finalize())
    assert prepared.messages[1].content.startswith(cc.CONTEXT_SUMMARY_PREFIX)
    assert "摘要内容" in prepared.messages[1].content
    assert prepared.compression.stage == "macro"
    assert calls["n"] == 1


def test_long_tool_loop_never_collapses_to_blank(monkeypatch):
    """复现 53272312 形态：少轮次 + 超长当前轮工具循环。

    旧实现下该形态会触发 emergency_fallback 把上下文砍到
    [system, 当前请求]，模型每轮迭代都失忆重启。
    """
    messages = [
        Message(role=MessageRole.SYSTEM, content="sys"),
        Message(role=MessageRole.USER, content="修改文件里的图"),
        Message(role=MessageRole.ASSISTANT, content="好的"),
        Message(role=MessageRole.USER, content="继续"),
    ]
    protected = {3}
    for i in range(150):
        a, t = _pair(i, blob_repeats=80)
        messages.extend([a, t])
        protected.update({len(messages) - 2, len(messages) - 1})

    _patch_builder(monkeypatch, messages, protected)
    _patch_summarizer(monkeypatch, "不应被调用")

    plan = asyncio.run(cc.build_context_plan(**_plan_kwargs()))
    assert not plan.will_summarize  # 轮次不足，无可摘要内容
    assert plan.compression.after_tokens > plan.trigger_budget

    prepared = asyncio.run(plan.finalize())
    # 确定性步骤压缩生效：上下文被压回预算内，且保留进度摘要与当前请求
    assert "compact_round_steps" in (prepared.compression.actions or [])
    assert prepared.compression.after_tokens <= prepared.token_budget.input_budget
    joined = "\n".join(
        m.content if isinstance(m.content, str) else "" for m in prepared.messages
    )
    assert TOOL_PROGRESS_SUMMARY_PREFIX in joined
    assert "继续" in joined
    assert prepared.compression.pressure_level != "over_budget"


def test_emergency_fallback_keeps_persisted_summary(monkeypatch):
    messages = [
        Message(role=MessageRole.SYSTEM, content="sys"),
        Message(role=MessageRole.USER, content="x" * 400000),
        Message(role=MessageRole.ASSISTANT, content="x" * 400000),
        Message(role=MessageRole.USER, content="继续"),
    ]
    _patch_builder(monkeypatch, messages, {1, 2, 3})
    _patch_summarizer(monkeypatch, None)

    async def active_branch(*args, **kwargs):
        return True

    monkeypatch.setattr(cc, "is_message_on_active_branch", active_branch)
    plan = asyncio.run(
        cc.build_context_plan(
            **_plan_kwargs(conversation=_conversation(persisted="历史摘要"))
        )
    )
    assert not plan.will_summarize

    prepared = asyncio.run(plan.finalize())
    # emergency 兜底必须带上持久化摘要，模型不得从零重启
    assert "emergency_fallback" in (prepared.compression.actions or [])
    assert len(prepared.messages) == 3
    assert "历史摘要" in prepared.messages[1].content
    assert prepared.messages[-1].content == "继续"


def test_normal_small_conversation_untouched(monkeypatch):
    messages = [
        Message(role=MessageRole.SYSTEM, content="sys"),
        Message(role=MessageRole.USER, content="你好"),
        Message(role=MessageRole.ASSISTANT, content="你好！"),
        Message(role=MessageRole.USER, content="继续"),
    ]
    _patch_builder(monkeypatch, messages, {3})
    calls = _patch_summarizer(monkeypatch, "不应被调用")

    plan = asyncio.run(cc.build_context_plan(**_plan_kwargs()))
    assert not plan.will_summarize
    assert plan.compression.stage == "none"

    prepared = asyncio.run(plan.finalize())
    assert [m.content for m in prepared.messages] == [
        "sys",
        "你好",
        "你好！",
        "继续",
    ]
    assert prepared.compression.stage == "none"
    assert calls["n"] == 0
