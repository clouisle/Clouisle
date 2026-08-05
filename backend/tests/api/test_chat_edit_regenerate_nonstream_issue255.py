from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_module
from app.llm.errors import LLMError
from app.models.agent import MessageRole, RAGMode
from app.schemas.agent import ChatRequest, EditMessageRequest, RegenerateRequest
from app.schemas.response import BusinessError, ResponseCode


class StopHere(Exception):
    pass


def _query(first=None):
    query = MagicMock()
    query.first = AsyncMock(return_value=first)
    query.prefetch_related.return_value = query
    return query


def _message(role=MessageRole.USER, content="original", **overrides):
    values = {
        "id": uuid4(),
        "conversation_id": uuid4(),
        "role": role,
        "content": content,
        "branch_parent_id": uuid4(),
        "parent_id": None,
        "created_at": SimpleNamespace(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _user(active=True):
    return SimpleNamespace(id=uuid4(), is_active=active, locale="en")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "content", "conversation", "agent", "expected"),
    [
        (None, "changed", None, None, "message_not_found"),
        (
            _message(role=MessageRole.ASSISTANT),
            "changed",
            None,
            None,
            "can_only_edit_user_message",
        ),
        (_message(), "   ", None, None, "message_content_required"),
        (_message(content="same"), " same ", None, None, "message_content_unchanged"),
        (_message(), "changed", None, None, "access_denied"),
        (_message(), "changed", SimpleNamespace(id=uuid4()), None, "agent_not_found"),
    ],
)
async def test_edit_user_message_preflight_failures(
    message, content, conversation, agent, expected
):
    message_query = _query(message)
    conversation_query = _query(conversation)
    agent_query = _query(agent)

    with (
        patch.object(chat_module.Message, "filter", return_value=message_query),
        patch.object(
            chat_module.Conversation, "filter", return_value=conversation_query
        ),
        patch.object(chat_module.Agent, "filter", return_value=agent_query),
        pytest.raises(BusinessError) as exc_info,
    ):
        await chat_module.edit_user_message_stream(
            uuid4(), uuid4(), EditMessageRequest(content=content), MagicMock(), _user()
        )

    assert exc_info.value.msg_key == expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "conversation", "agent", "prefix", "expected"),
    [
        (None, None, None, [], "message_not_found"),
        (_message(), None, None, [], "can_only_regenerate_assistant"),
        (_message(role=MessageRole.ASSISTANT), None, None, [], "access_denied"),
        (
            _message(role=MessageRole.ASSISTANT),
            SimpleNamespace(id=uuid4(), agent_id=uuid4()),
            None,
            [],
            "agent_not_found",
        ),
        (
            _message(role=MessageRole.ASSISTANT),
            SimpleNamespace(id=uuid4(), agent_id=uuid4()),
            SimpleNamespace(id=uuid4()),
            [],
            "no_user_message_found",
        ),
    ],
)
async def test_regenerate_message_preflight_failures(
    message, conversation, agent, prefix, expected
):
    with (
        patch.object(chat_module.Message, "filter", return_value=_query(message)),
        patch.object(
            chat_module.Conversation, "filter", return_value=_query(conversation)
        ),
        patch.object(chat_module.Agent, "filter", return_value=_query(agent)),
        patch.object(
            chat_module, "get_prefix_path_before", new=AsyncMock(return_value=prefix)
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await chat_module.regenerate_message(
            uuid4(), uuid4(), RegenerateRequest(), MagicMock(), _user()
        )

    assert exc_info.value.msg_key == expected


@pytest.mark.anyio
async def test_regenerate_selects_latest_user_from_prefix():
    assistant = _message(role=MessageRole.ASSISTANT)
    older_user = _message(content="older")
    latest_user = _message(content="latest")
    conversation = SimpleNamespace(id=uuid4(), agent_id=uuid4())
    agent = SimpleNamespace(id=uuid4())

    with (
        patch.object(chat_module.Message, "filter", return_value=_query(assistant)),
        patch.object(
            chat_module.Conversation, "filter", return_value=_query(conversation)
        ),
        patch.object(chat_module.Agent, "filter", return_value=_query(agent)),
        patch.object(
            chat_module,
            "get_prefix_path_before",
            new=AsyncMock(return_value=[older_user, assistant, latest_user]),
        ),
    ):
        response = await chat_module.regenerate_message(
            uuid4(), assistant.id, RegenerateRequest(), MagicMock(), _user()
        )

    assert response.media_type == "text/event-stream"


@pytest.mark.anyio
async def test_edit_accepts_valid_request_and_captures_existing_branch():
    message = _message()
    conversation = SimpleNamespace(id=message.conversation_id)
    agent = SimpleNamespace(id=uuid4())
    prefix = [_message()]
    descendants = [_message(role=MessageRole.ASSISTANT)]

    with (
        patch.object(chat_module.Message, "filter", return_value=_query(message)),
        patch.object(
            chat_module.Conversation, "filter", return_value=_query(conversation)
        ),
        patch.object(chat_module.Agent, "filter", return_value=_query(agent)),
        patch.object(
            chat_module, "get_prefix_path_before", new=AsyncMock(return_value=prefix)
        ) as get_prefix,
        patch.object(
            chat_module,
            "find_descendant_branch_from",
            new=AsyncMock(return_value=descendants),
        ) as find_descendants,
    ):
        response = await chat_module.edit_user_message_stream(
            agent.id,
            message.id,
            EditMessageRequest(content=" changed "),
            MagicMock(),
            _user(),
        )

    assert response.media_type == "text/event-stream"
    get_prefix.assert_awaited_once_with(message)
    find_descendants.assert_awaited_once_with(message)


@pytest.mark.anyio
async def test_nonstream_rejects_inactive_user_before_boundaries():
    access = AsyncMock()

    with (
        patch.object(chat_module.deps, "check_api_key_agent_access", access),
        pytest.raises(BusinessError) as exc_info,
    ):
        await chat_module.chat(
            uuid4(), ChatRequest(message="hello"), (_user(False), None)
        )

    assert exc_info.value.code == ResponseCode.INACTIVE_USER
    access.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("rag_mode", "images", "file_urls", "rag_result", "expected_content"),
    [
        (RAGMode.OFF, [], [], [], "hello"),
        (RAGMode.AUTO, [], [], [], "rag prompt"),
        (
            RAGMode.AUTO,
            [{"url": "data:image/png;base64,eA=="}],
            [],
            [{"id": "a"}],
            "rag prompt",
        ),
        (
            RAGMode.OFF,
            [],
            [
                {
                    "filename": "a.txt",
                    "url": "https://example.com/a.txt",
                    "size": 1,
                    "mime_type": "text/plain",
                }
            ],
            [],
            "hello",
        ),
    ],
)
async def test_nonstream_builds_user_message_variants(
    rag_mode, images, file_urls, rag_result, expected_content
):
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4(), rag_mode=rag_mode)
    conversation = SimpleNamespace(id=uuid4())
    created = AsyncMock(side_effect=StopHere)

    with (
        patch.object(chat_module.deps, "check_api_key_agent_access", new=AsyncMock()),
        patch.object(
            chat_module, "check_agent_chat_access", new=AsyncMock(return_value=agent)
        ),
        patch.object(
            chat_module,
            "get_or_create_conversation",
            new=AsyncMock(return_value=conversation),
        ),
        patch.object(
            chat_module,
            "perform_rag_retrieval",
            new=AsyncMock(return_value=rag_result),
        ) as retrieve,
        patch.object(chat_module, "aggregate_rag_contexts", return_value=rag_result),
        patch.object(chat_module, "build_rag_prompt", return_value="rag prompt"),
        patch.object(
            chat_module,
            "get_visible_conversation_messages",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(
            chat_module,
            "get_next_user_branch_parent_id",
            new=AsyncMock(return_value=None),
        ),
        patch.object(chat_module.Message, "create", new=created),
        pytest.raises(StopHere),
    ):
        await chat_module.chat(
            agent.id,
            ChatRequest(message="hello", images=images, file_urls=file_urls),
            (_user(), None),
        )

    kwargs = created.await_args.kwargs
    assert kwargs["content"] == "hello"
    expected_images = [
        {"type": "image_url", "asset_id": None, "asset_ref": None, **image}
        for image in images
    ]
    assert kwargs["images"] == expected_images or (
        not images and kwargs["images"] is None
    )
    expected_file_urls = [{"asset_id": None, **item} for item in file_urls]
    assert kwargs["file_urls"] == expected_file_urls or (
        not file_urls and kwargs["file_urls"] is None
    )
    assert (kwargs["rag_context"] or []) == rag_result
    assert (retrieve.await_count == 1) is (rag_mode == RAGMode.AUTO)
    assert expected_content in {"hello", "rag prompt"}


@pytest.mark.anyio
@pytest.mark.parametrize("has_team_model", [False, True])
async def test_nonstream_model_selection_reaches_sandbox_boundary(has_team_model):
    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        rag_mode=RAGMode.OFF,
        enable_attachments=True,
    )
    conversation = SimpleNamespace(id=uuid4())
    user_message = SimpleNamespace(id=uuid4(), file_urls=None)
    model = SimpleNamespace(
        id=uuid4(),
        is_enabled=True,
        provider="provider",
        model_id="model",
        capabilities={"vision": True},
        context_length=4096,
        max_output_tokens=512,
    )
    team_model = SimpleNamespace(model=model) if has_team_model else None
    chat_resolution = SimpleNamespace(
        model=model,
        team_model=team_model,
        model_id=str(model.id),
        tokenizer_model_id="model",
        provider="provider",
        context_length=4096,
        max_output_tokens=512,
        supports_vision=True,
    )

    with (
        patch.object(chat_module.deps, "check_api_key_agent_access", new=AsyncMock()),
        patch.object(
            chat_module, "check_agent_chat_access", new=AsyncMock(return_value=agent)
        ),
        patch.object(
            chat_module,
            "get_or_create_conversation",
            new=AsyncMock(return_value=conversation),
        ),
        patch.object(
            chat_module,
            "get_next_user_branch_parent_id",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            chat_module.Message, "create", new=AsyncMock(return_value=user_message)
        ),
        patch.object(chat_module, "update_message_stats", new=AsyncMock()),
        patch.object(
            chat_module,
            "resolve_agent_chat_model",
            new=AsyncMock(return_value=chat_resolution),
        ),
        patch.object(
            chat_module, "get_streaming_config", return_value={"tool_timeouts": {}}
        ),
        patch(
            "app.services.sandbox.gateway.sandbox_gateway.create_session",
            new=AsyncMock(side_effect=StopHere),
        ),
        pytest.raises(StopHere),
    ):
        await chat_module.chat(
            agent.id,
            ChatRequest(
                message="hello", images=[{"url": "data:image/png;base64,eA=="}]
            ),
            (_user(), None),
        )


@pytest.mark.anyio
async def test_nonstream_converts_llm_error_to_business_error():
    agent_id = uuid4()

    with (
        patch.object(chat_module.deps, "check_api_key_agent_access", new=AsyncMock()),
        patch.object(
            chat_module,
            "check_agent_chat_access",
            new=AsyncMock(side_effect=LLMError("provider failed")),
        ),
        pytest.raises(LLMError, match="provider failed"),
    ):
        await chat_module.chat(agent_id, ChatRequest(message="hello"), (_user(), None))
