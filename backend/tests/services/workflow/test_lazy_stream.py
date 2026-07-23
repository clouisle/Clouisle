"""Behavioral tests for deferred workflow LLM streams."""

from types import SimpleNamespace

import pytest

from app.llm import model_manager
from app.llm.types import ChatStreamChunk, ChatStreamDelta, Usage
from app.services.workflow.lazy_stream import LazyStreamResult
from app.services.workflow import stream as stream_module


def make_result() -> LazyStreamResult:
    return LazyStreamResult(
        model_id="provider/model",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.25,
        max_tokens=None,
        top_p=0.9,
        response_format={"type": "json_object"},
        context=SimpleNamespace(run_id="run-1"),
        source_node_id="llm-1",
    )


def chunk(
    *,
    content: str | None = None,
    reasoning: str | None = None,
    usage: Usage | None = None,
) -> ChatStreamChunk:
    return ChatStreamChunk(
        id="chunk-1",
        model="model",
        delta=ChatStreamDelta(content=content, reasoning_content=reasoning),
        usage=usage,
    )


@pytest.mark.asyncio
async def test_execution_is_delayed_until_awaited(monkeypatch):
    calls = 0

    async def chat_stream(**kwargs):
        nonlocal calls
        calls += 1
        yield chunk(content="answer")

    monkeypatch.setattr(model_manager, "chat_stream", chat_stream)
    result = make_result()

    assert calls == 0
    assert result.reasoning is None
    assert result.usage is None
    assert repr(result) == "<LazyStreamResult(llm-1, pending)>"

    assert await result.execute() == "answer"
    assert calls == 1
    assert repr(result) == "<LazyStreamResult(llm-1, executed)>"


@pytest.mark.asyncio
async def test_iterates_chunks_and_streams_content(monkeypatch):
    received_kwargs = None
    published = []

    async def chat_stream(**kwargs):
        nonlocal received_kwargs
        received_kwargs = kwargs
        yield chunk(content="Hello ", reasoning="think ")
        yield chunk(reasoning="more")
        yield chunk(
            content="world",
            usage=Usage(prompt_tokens=2, completion_tokens=3, total_tokens=5),
        )

    class FakeStreamManager:
        def __init__(self, run_id):
            assert run_id == "run-1"

        async def publish_token(self, node_id, token):
            published.append((node_id, token))

    monkeypatch.setattr(model_manager, "chat_stream", chat_stream)
    monkeypatch.setattr(stream_module, "StreamManager", FakeStreamManager)
    result = make_result()

    assert await result.execute("answer-1") == "Hello world"
    assert result.reasoning == "think more"
    assert result.usage == {
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 5,
    }
    assert published == [("answer-1", "Hello "), ("answer-1", "world")]
    assert received_kwargs == {
        "messages": result.messages,
        "model_id": "provider/model",
        "temperature": 0.25,
        "max_tokens": None,
        "top_p": 0.9,
        "response_format": {"type": "json_object"},
    }


@pytest.mark.asyncio
async def test_completed_stream_is_not_iterated_again(monkeypatch):
    iterations = 0

    async def chat_stream(**kwargs):
        nonlocal iterations
        iterations += 1
        yield chunk(content="done")

    monkeypatch.setattr(model_manager, "chat_stream", chat_stream)
    result = make_result()

    assert await result.execute() == "done"
    assert await result.execute("ignored-node") == "done"
    assert iterations == 1


@pytest.mark.asyncio
async def test_stream_is_closed_after_iteration(monkeypatch):
    closed = False

    async def chat_stream(**kwargs):
        nonlocal closed
        try:
            yield chunk(content="done")
        finally:
            closed = True

    monkeypatch.setattr(model_manager, "chat_stream", chat_stream)

    assert await make_result().execute() == "done"
    assert closed is True


@pytest.mark.asyncio
async def test_error_propagates_and_allows_retry(monkeypatch):
    attempts = 0

    async def chat_stream(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("provider failed")
        yield chunk(content="recovered")

    monkeypatch.setattr(model_manager, "chat_stream", chat_stream)
    result = make_result()

    with pytest.raises(RuntimeError, match="provider failed"):
        await result.execute()

    assert repr(result) == "<LazyStreamResult(llm-1, pending)>"
    assert result.reasoning is None
    assert result.usage is None
    assert await result.execute() == "recovered"
    assert attempts == 2


@pytest.mark.asyncio
async def test_empty_stream_returns_boundary_defaults(monkeypatch):
    async def chat_stream(**kwargs):
        if False:
            yield

    monkeypatch.setattr(model_manager, "chat_stream", chat_stream)
    result = make_result()
    result.context = None  # No context is required when token streaming is disabled.

    assert await result.execute() == ""
    assert result.reasoning is None
    assert result.usage == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
