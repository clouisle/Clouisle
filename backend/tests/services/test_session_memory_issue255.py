import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models.agent import ConversationSessionMemoryStatus, MessageRole
from app.services import session_memory


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [asyncio.TimeoutError(), RuntimeError("database down")]
)
async def test_get_ready_session_memory_handles_database_failures(monkeypatch, failure):
    query = MagicMock()
    query.first = MagicMock()
    monkeypatch.setattr(
        session_memory.ConversationSessionMemory,
        "filter",
        MagicMock(return_value=query),
    )

    async def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(asyncio, "wait_for", fail)

    assert await session_memory.get_ready_session_memory(uuid4()) is None


def test_snapshot_helpers_normalize_render_and_truncate_tool_content(monkeypatch):
    payload = session_memory._normalize_snapshot_payload(
        {
            "overview": "  Current\nfocus  ",
            "constraints": [" Keep scope ", "keep scope", 1],
            "latest_focus": [],
        },
        previous_payload={"latest_focus": ["Previous focus"]},
    )
    assert payload["overview"] == "Current focus"
    assert payload["constraints"] == ["Keep scope"]
    assert payload["latest_focus"] == ["Previous focus"]
    assert "Constraints:\n- Keep scope" in session_memory._render_summary_text(payload)

    summarize = MagicMock(return_value="x" * 1_300)
    monkeypatch.setattr(
        "app.services.chat_context.summarize_tool_result_for_llm", summarize
    )
    transcript = session_memory._render_transcript(
        [
            [
                SimpleNamespace(
                    role=MessageRole.USER,
                    content="Question",
                    tool_calls=None,
                ),
                SimpleNamespace(
                    role=MessageRole.ASSISTANT,
                    content="Answer",
                    tool_calls=[{"name": "search"}, {"ignored": True}],
                ),
                SimpleNamespace(
                    role=MessageRole.TOOL,
                    content="raw tool output",
                    tool_name="search",
                    tool_calls=None,
                ),
            ]
        ]
    )

    assert "ASSISTANT_TOOL_CALLS: search" in transcript
    assert "TOOL: " + ("x" * 1_197) + "..." in transcript
    summarize.assert_called_once_with("search", "raw tool output")


def test_parse_json_rejects_non_object_and_extract_messages_include_context():
    with pytest.raises(ValueError, match="JSON object"):
        session_memory._parse_json_object("[]")

    messages = session_memory._build_extraction_messages(
        previous_payload={"overview": "Earlier"},
        previous_summary="Earlier summary",
        transcript="## Turn 1\nUSER: Hello",
    )

    assert messages[1].content is not None
    assert "Earlier summary" in messages[1].content
    assert "USER: Hello" in messages[1].content
    assert (
        session_memory._should_skip_already_extracted_snapshot(
            SimpleNamespace(
                source_message_id=uuid4(),
                status=ConversationSessionMemoryStatus.READY,
                snapshot_payload=None,
            ),
            uuid4(),
        )
        is False
    )
