from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.llm.types import ContentType, MessageRole
from app.models.agent import MessageRole as ConversationMessageRole
from app.services import chat_context
from app.services.chat_context import (
    _build_file_content_for_user_message,
    _build_messages_with_file_content,
    _build_system_prompt,
)


def _agent():
    return SimpleNamespace(
        id=uuid4(),
        system_prompt="Base {{fileContent}} prompt",
        enable_memory=False,
        enable_user_input_request=False,
        tools_config=[],
        enable_file_upload=True,
        file_upload_config={
            "parser": {"type": "builtin", "name": "markitdown"},
            "max_content_length": 100000,
            "truncate_strategy": "end",
        },
    )


def _conversation():
    return SimpleNamespace(id=uuid4(), variables={})


def test_file_content_placeholder_is_not_injected_into_system_prompt():
    prompt = _build_system_prompt(
        agent=_agent(),
        conversation=_conversation(),
        user_message="question",
        user_locale="en",
    )

    assert "Base  prompt" in prompt
    assert "parsed file text" not in prompt
    assert "{{fileContent}}" not in prompt


@pytest.mark.anyio
async def test_current_upload_content_is_appended_to_current_user_message():
    messages, _ = await _build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="Please summarize this.",
        file_content="Report content",
        user_locale="en",
        history_override=[],
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
    )

    assert messages[-1].role == MessageRole.USER
    assert messages[-1].content == (
        "Please summarize this.\n\n"
        "<uploaded_files>\nReport content\n</uploaded_files>"
    )


@pytest.mark.anyio
async def test_vision_upload_content_preserves_image_parts():
    messages, _ = await _build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="Describe this.",
        file_content="Document content",
        user_locale="en",
        history_override=[],
        current_images=[{"url": "data:image/png;base64,abc"}],
        model_supports_vision=True,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
    )

    content = messages[-1].content
    assert isinstance(content, list)
    assert content[0].type == ContentType.TEXT
    assert content[0].text == "Describe this."
    assert content[1].type == ContentType.IMAGE
    assert content[2].type == ContentType.TEXT
    assert content[2].text == "<uploaded_files>\nDocument content\n</uploaded_files>"


@pytest.mark.anyio
async def test_history_override_file_urls_append_parsed_content(monkeypatch):
    calls = []

    async def fake_build_file_content_for_context(**kwargs):
        calls.append(kwargs)
        return "Historical document", [{"url": "/api/v1/upload/files/docs/a.txt"}]

    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context",
        fake_build_file_content_for_context,
    )

    messages, _ = await _build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="Follow up",
        file_content=None,
        user_locale="en",
        history_override=[
            {
                "role": "user",
                "content": "Earlier question",
                "file_urls": [{"url": "/api/v1/upload/files/docs/a.txt"}],
            }
        ],
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
        tool_timeouts={"download": 3},
        user=SimpleNamespace(id="user-1"),
    )

    assert messages[1].content == (
        "Earlier question\n\n"
        "<uploaded_files>\nHistorical document\n</uploaded_files>"
    )
    assert messages[2].content == "Follow up"
    assert calls[0]["tool_timeouts"] == {"download": 3}
    assert calls[0]["user"].id == "user-1"


@pytest.mark.anyio
async def test_historical_message_cache_metadata_is_saved(monkeypatch):
    updated_file_urls = [
        {
            "url": "/api/v1/upload/files/docs/a.txt",
            "parse_cache": {"status": "success", "key": "cache-key"},
        }
    ]

    async def fake_build_file_content_for_context(**kwargs):
        return "Cached historical document", updated_file_urls

    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context",
        fake_build_file_content_for_context,
    )

    class FakeMessage:
        def __init__(self):
            self.file_urls = [{"url": "/api/v1/upload/files/docs/a.txt"}]
            self.saved_update_fields = None

        async def save(self, update_fields=None):
            self.saved_update_fields = update_fields

    source_message = FakeMessage()

    content = await _build_file_content_for_user_message(
        agent=_agent(),
        file_urls=source_message.file_urls,
        user_locale="en",
        tool_timeouts=None,
        user=None,
        source_message=source_message,
    )

    assert content == "Cached historical document"
    assert source_message.file_urls == updated_file_urls
    assert source_message.saved_update_fields == ["file_urls"]


@pytest.mark.anyio
async def test_historical_db_message_file_urls_append_parsed_content(monkeypatch):
    async def fake_build_file_content_for_context(**kwargs):
        return "DB document", kwargs["file_urls"]

    monkeypatch.setattr(
        "app.api.v1.endpoints.chat_tools.build_file_content_for_context",
        fake_build_file_content_for_context,
    )

    async def _noop_save(update_fields=None):
        return None

    class FakeQuery:
        def filter(self, **kwargs):
            return self

        def exclude(self, **kwargs):
            return self

        async def order_by(self, *args):
            return [
                SimpleNamespace(
                    id=uuid4(),
                    role=ConversationMessageRole.USER,
                    content="Historical question",
                    file_urls=[{"url": "/api/v1/upload/files/docs/a.txt"}],
                    round_id=None,
                    save=_noop_save,
                )
            ]

    monkeypatch.setattr(chat_context.ConversationMessage, "filter", lambda **kwargs: FakeQuery())

    messages, _ = await _build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="Follow up",
        file_content=None,
        user_locale="en",
        history_override=None,
        current_images=None,
        model_supports_vision=False,
        current_user_message_id=None,
        include_current_user_message=False,
        exclude_message_ids=None,
        history_before_message_created_at=None,
    )

    assert messages[1].content == (
        "Historical question\n\n"
        "<uploaded_files>\nDB document\n</uploaded_files>"
    )
    assert messages[2].content == "Follow up"
