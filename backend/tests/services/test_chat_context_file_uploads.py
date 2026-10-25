import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.llm.types import ContentType, MessageRole
from app.services import chat_context
from app.services.chat_context import (
    _build_messages_with_file_content,
    _build_system_prompt,
)


def _agent():
    return SimpleNamespace(
        id=uuid4(),
        system_prompt="Base {{fileContent}} prompt",
        enable_memory=False,
        tools_config=[],
        enable_attachments=True,
        attachment_config={
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
async def test_current_text_file_content_is_appended_to_current_user_message():
    messages, _, _ = await _build_messages_with_file_content(
        agent=_agent(),
        conversation=_conversation(),
        user_message="Please summarize this.",
        file_content="Report content",
        user_locale="en",
        history_override=[],
        current_images=None,
        input_capabilities=SimpleNamespace(modalities=frozenset({ContentType.TEXT})),
        model_config=None,
        current_user_message_id=None,
        include_current_user_message=True,
        exclude_message_ids=None,
        history_before_message_created_at=None,
    )
    assert messages[-1].role == MessageRole.USER
    assert messages[-1].content == (
        "Please summarize this.\n\n<uploaded_files>\nReport content\n</uploaded_files>"
    )


@pytest.mark.asyncio
async def test_prepare_context_with_model_configuration_keeps_user_input():
    from app.llm.capabilities import get_effective_input_capabilities
    from app.models.model import ModelProvider, ModelType

    model = SimpleNamespace(
        provider=ModelProvider.OPENAI,
        model_type=ModelType.CHAT,
        base_url=None,
        capabilities={"input_modalities": ["text"]},
    )
    agent = _agent()
    agent.context_compression_config = {"enabled": False}
    context = await chat_context.prepare_model_context(
        agent=agent,
        conversation=_conversation(),
        user_message="Summarize the report",
        model_id="configured-model",
        model_config=model,
        input_capabilities=get_effective_input_capabilities(model),
        model_context_limit=8192,
        model_max_output_tokens=1024,
        history_override=[],
    )
    assert context.messages[-1].role == MessageRole.USER
    assert context.messages[-1].content == "Summarize the report"


@pytest.mark.asyncio
async def test_rehydrate_view_asset_preserves_extracted_text_representation(
    monkeypatch,
):
    from app.llm.types import ContentPart, ContentType

    conversation = _conversation()
    user = SimpleNamespace(id=uuid4())
    agent = _agent()
    asset_id = uuid4()
    marker = {
        "version": 1,
        "kind": "asset.view",
        "ref": "scoped-ref",
        "asset_id": str(asset_id),
        "scope_type": "conversation",
        "scope_id": str(conversation.id),
        "checksum": "abc",
        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "wire_mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "modality": "text",
        "extracted_text": True,
        "selection": None,
        "representation": {"kind": "extracted_text", "truncated": False},
    }
    asset = SimpleNamespace(
        id=asset_id,
        checksum="abc",
        content_type=marker["mime_type"],
        display_filename="report.docx",
    )
    part = ContentPart(type=ContentType.TEXT, text="Extracted document body")
    resolve = AsyncMock(
        return_value=(
            asset,
            part,
            json.dumps(
                {
                    **marker,
                    "asset_id": str(uuid4()),
                    "scope_type": "conversation",
                    "scope_id": str(conversation.id),
                }
            ),
        )
    )
    monkeypatch.setattr("app.services.asset_view.resolve_view_content", resolve)

    replayed = await chat_context._rehydrate_asset_view_marker(
        json.dumps(marker),
        tool_name="view_asset",
        user=user,
        conversation=conversation,
        agent=agent,
        model_config=SimpleNamespace(),
    )

    assert replayed[-1] == part
    assert resolve.await_args.kwargs["extracted_text"] is True
    assert resolve.await_args.kwargs["selection"] is None
