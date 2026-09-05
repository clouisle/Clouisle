from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat as chat_module
from app.llm.errors import LLMError
from app.models.agent import MessageRole, MessageRoundStatus, RAGMode
from app.models.agent_run import AgentRunMode
from app.schemas.agent import ChatRequest, EditMessageRequest, RegenerateRequest
from app.schemas.response import BusinessError, ResponseCode


class StopHere(Exception):
    pass


def _query(first=None, *, count=0):
    query = MagicMock()
    query.first = AsyncMock(return_value=first)
    query.count = AsyncMock(return_value=count)
    query.prefetch_related.return_value = query
    query.filter.return_value = query
    query.using_db.return_value = query
    query.select_for_update.return_value = query
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


class _Transaction:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return False


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
async def test_regenerate_selects_latest_user_from_prefix(monkeypatch):
    assistant = _message(
        role=MessageRole.ASSISTANT,
        round_status=MessageRoundStatus.COMPLETED,
    )
    older_user = _message(content="older", images=[], file_urls=[])
    latest_user = _message(content="latest", images=[], file_urls=[])
    conversation = SimpleNamespace(id=uuid4(), agent_id=uuid4())
    agent = SimpleNamespace(id=uuid4(), rag_mode=RAGMode.OFF)
    created = SimpleNamespace(id=uuid4())
    started = {"data": object()}
    stream_response = object()

    async def create_message(**values):
        for key, value in values.items():
            setattr(created, key, value)
        return created

    prefix = AsyncMock(return_value=[older_user, assistant, latest_user])
    enqueue = AsyncMock(return_value=started)
    monkeypatch.setattr(
        chat_module.Message, "filter", lambda **_kwargs: _query(assistant)
    )
    monkeypatch.setattr(
        chat_module.Conversation, "filter", lambda **_kwargs: _query(conversation)
    )
    monkeypatch.setattr(chat_module.Agent, "filter", lambda **_kwargs: _query(agent))
    monkeypatch.setattr(chat_module, "get_prefix_path_before", prefix)
    monkeypatch.setattr(
        chat_module, "get_version_root_id", lambda _message: assistant.id
    )
    monkeypatch.setattr(
        chat_module, "get_branch_version_count", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(chat_module.Message, "create", create_message)
    monkeypatch.setattr(chat_module, "_enqueue_existing_message_run", enqueue)
    monkeypatch.setattr(
        chat_module, "_stream_queued_run", lambda _started: stream_response
    )

    response = await chat_module.regenerate_message(
        agent.id, assistant.id, RegenerateRequest(), MagicMock(), _user()
    )

    assert response is stream_response
    prefix.assert_awaited_once_with(assistant, trimmed=False)
    assert enqueue.await_args.kwargs["mode"] == AgentRunMode.REGENERATE
    assert enqueue.await_args.kwargs["source_message_id"] == assistant.id
    assert enqueue.await_args.kwargs["user_message"] is latest_user
    assert enqueue.await_args.kwargs["message"] == "latest"
    assert enqueue.await_args.kwargs["include_current_user_message"] is False


@pytest.mark.anyio
async def test_edit_accepts_valid_request_and_captures_existing_branch(monkeypatch):
    message = _message(images=[], file_urls=[])
    conversation = SimpleNamespace(id=message.conversation_id)
    agent = SimpleNamespace(id=uuid4(), rag_mode=RAGMode.OFF)
    prefix = [_message(images=[], file_urls=[])]
    edited = SimpleNamespace(id=uuid4())
    assistant = SimpleNamespace(id=uuid4())
    created = iter([edited, assistant])
    started = {"data": object()}
    stream_response = object()
    activate = AsyncMock()
    enqueue = AsyncMock(return_value=started)

    async def create_message(**values):
        item = next(created)
        for key, value in values.items():
            setattr(item, key, value)
        return item

    monkeypatch.setattr(
        chat_module.Message,
        "filter",
        lambda *_args, **_kwargs: _query(message, count=2),
    )
    monkeypatch.setattr(
        chat_module.Conversation, "filter", lambda **_kwargs: _query(conversation)
    )
    monkeypatch.setattr(chat_module.Agent, "filter", lambda **_kwargs: _query(agent))
    get_prefix = AsyncMock(return_value=prefix)
    monkeypatch.setattr(chat_module, "get_prefix_path_before", get_prefix)
    monkeypatch.setattr(chat_module, "get_version_root_id", lambda _m: message.id)
    monkeypatch.setattr(chat_module.Message, "create", create_message)
    monkeypatch.setattr(chat_module, "in_transaction", lambda: _Transaction())
    monkeypatch.setattr(chat_module, "activate_conversation_branch", activate)
    monkeypatch.setattr(chat_module, "_enqueue_existing_message_run", enqueue)
    monkeypatch.setattr(
        chat_module, "_stream_queued_run", lambda _started: stream_response
    )
    monkeypatch.setattr(
        chat_module.MessageAsset._meta, "default_connection", None, raising=False
    )

    response = await chat_module.edit_user_message_stream(
        agent.id,
        message.id,
        EditMessageRequest(content=" changed "),
        MagicMock(),
        _user(),
    )

    assert response is stream_response
    get_prefix.assert_awaited_once_with(message, trimmed=False)
    assert enqueue.await_args.kwargs["mode"] == AgentRunMode.EDIT
    assert enqueue.await_args.kwargs["source_message_id"] == message.id
    assert enqueue.await_args.kwargs["user_message"] is edited
    assert edited.content == "changed"
    assert assistant.branch_parent_id == edited.id
    assert activate.await_count == 1
    assert activate.await_args.args[1][-1] is edited


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
