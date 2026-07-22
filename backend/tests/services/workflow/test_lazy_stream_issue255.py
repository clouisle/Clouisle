from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm import model_manager
from app.services.workflow.lazy_stream import LazyStreamResult


def result() -> LazyStreamResult:
    return LazyStreamResult(
        model_id="model-1",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.2,
        max_tokens=20,
        top_p=0.8,
        response_format={"type": "text"},
        context=SimpleNamespace(run_id="run-1"),
        source_node_id="llm-1",
    )


@pytest.mark.asyncio
async def test_execute_streams_content_collects_metadata_and_caches(monkeypatch):
    usage = SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5)

    async def chunks():
        yield SimpleNamespace(
            delta=SimpleNamespace(content="Hi", reasoning_content="Think"), usage=None
        )
        yield SimpleNamespace(delta=None, usage=usage)
        yield SimpleNamespace(
            delta=SimpleNamespace(content=" there", reasoning_content=""), usage=None
        )

    chat_stream = MagicMock(return_value=chunks())
    stream = SimpleNamespace(publish_token=AsyncMock())
    monkeypatch.setattr(model_manager, "chat_stream", chat_stream)

    lazy = result()
    assert repr(lazy) == "<LazyStreamResult(llm-1, pending)>"

    with patch(
        "app.services.workflow.stream.StreamManager", return_value=stream
    ) as stream_manager:
        assert await lazy.execute("answer-1") == "Hi there"
        assert await lazy.execute("ignored") == "Hi there"

    stream_manager.assert_called_once_with("run-1")
    assert [call.args for call in stream.publish_token.await_args_list] == [
        ("answer-1", "Hi"),
        ("answer-1", " there"),
    ]
    chat_stream.assert_called_once_with(
        messages=lazy.messages,
        model_id="model-1",
        temperature=0.2,
        max_tokens=20,
        top_p=0.8,
        response_format={"type": "text"},
    )
    assert lazy.reasoning == "Think"
    assert lazy.usage == {
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 5,
    }
    assert repr(lazy) == "<LazyStreamResult(llm-1, executed)>"


@pytest.mark.asyncio
async def test_execute_without_stream_or_metadata_uses_empty_defaults(monkeypatch):
    async def chunks():
        yield SimpleNamespace(
            delta=SimpleNamespace(content=None, reasoning_content=None), usage=None
        )

    monkeypatch.setattr(model_manager, "chat_stream", MagicMock(return_value=chunks()))
    lazy = result()

    with patch("app.services.workflow.stream.StreamManager") as stream_manager:
        assert await lazy.execute() == ""

    stream_manager.assert_not_called()
    assert lazy.reasoning is None
    assert lazy.usage == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
