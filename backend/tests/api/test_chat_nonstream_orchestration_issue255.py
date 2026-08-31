from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent_run import AgentRunMode, AgentRunStatus
from app.schemas.agent import ChatRequest, FileUrl, ImageContent, RunStartOut
from app.schemas.response import BusinessError, ResponseCode


def _started() -> dict:
    return {
        "data": RunStartOut(
            run_id=uuid4(),
            conversation_id=uuid4(),
            user_message_id=uuid4(),
            status="queued",
            stream_url="/agents/run/chat/runs/run/stream",
        )
    }


@pytest.mark.anyio
async def test_chat_nonstream_queues_rag_and_attachment_request(monkeypatch):
    """The route queues the complete request; the worker owns execution."""
    started = _started()
    run = SimpleNamespace(id=started["data"].run_id, status=AgentRunStatus.COMPLETED)
    enqueue = AsyncMock(return_value=started)
    wait = AsyncMock(return_value=run)
    response = {"data": {"message": {"content": "answer"}}}
    build_response = AsyncMock(return_value=response)
    monkeypatch.setattr(chat, "_enqueue_durable_chat_run", enqueue)
    monkeypatch.setattr(chat, "_wait_for_agent_run", wait)
    monkeypatch.setattr(chat, "_build_non_stream_run_response", build_response)

    agent_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    request = ChatRequest(
        message="explain the notes",
        images=[ImageContent(url="current.png")],
        file_urls=[
            FileUrl(
                filename="notes.txt",
                url="https://files.test/notes.txt",
                size=10,
                mime_type="text/plain",
            )
        ],
    )

    result = await chat.chat(agent_id, request, (user, None))

    assert result is response
    assert enqueue.await_args.args[:3] == (agent_id, request, (user, None))
    assert enqueue.await_args.kwargs["mode"] == AgentRunMode.NON_STREAM
    wait.assert_awaited_once_with(started["data"].run_id)
    build_response.assert_awaited_once_with(run)


@pytest.mark.anyio
@pytest.mark.parametrize("field", ["asset_id", "asset_ref"])
async def test_chat_rejects_invalid_attachment_before_durable_run(monkeypatch, field):
    """Asset resolution errors are propagated before a run is queued."""
    agent_id = uuid4()
    user = SimpleNamespace(id=uuid4(), is_active=True, locale="en")
    agent = SimpleNamespace(id=agent_id, rag_mode="off")
    conversation = SimpleNamespace(id=uuid4())
    error = BusinessError(
        code=ResponseCode.NOT_FOUND,
        msg_key="file_not_found",
        status_code=404,
    )
    resolve_assets = AsyncMock(side_effect=error)
    monkeypatch.setattr(chat, "_resolve_message_assets", resolve_assets)
    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(chat, "check_agent_chat_access", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        chat, "get_or_create_conversation", AsyncMock(return_value=conversation)
    )
    message_create = AsyncMock()
    monkeypatch.setattr(chat.Message, "create", message_create)

    attachment = ImageContent(
        url="current.png",
        **{field: uuid4() if field == "asset_id" else "a1b2"},
    )
    with pytest.raises(BusinessError) as exc_info:
        await chat.chat(
            agent_id,
            ChatRequest(message="invalid attachment", images=[attachment]),
            (user, None),
        )

    assert exc_info.value.code == ResponseCode.NOT_FOUND
    resolve_assets.assert_awaited_once()
    message_create.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error_code", "expected_code", "expected_status", "expected_msg_key"),
    [
        (
            "model_quota_exceeded",
            ResponseCode.MODEL_QUOTA_EXCEEDED,
            429,
            "model_quota_exceeded",
        ),
        ("provider_error", ResponseCode.UNKNOWN_ERROR, 500, "llm_processing_failed"),
    ],
)
async def test_chat_maps_durable_run_failure_without_final_persistence(
    monkeypatch, error_code, expected_code, expected_status, expected_msg_key
):
    """The legacy response adapter maps worker terminal failures."""
    started = _started()
    run = SimpleNamespace(
        id=started["data"].run_id,
        status=AgentRunStatus.FAILED,
        error_code=error_code,
        canonical_message_id=None,
    )
    enqueue = AsyncMock(return_value=started)
    wait = AsyncMock(return_value=run)
    monkeypatch.setattr(chat, "_enqueue_durable_chat_run", enqueue)
    monkeypatch.setattr(chat, "_wait_for_agent_run", wait)

    with pytest.raises(BusinessError) as exc_info:
        await chat.chat(
            uuid4(),
            ChatRequest(message="hello"),
            (SimpleNamespace(id=uuid4(), is_active=True), None),
        )

    assert exc_info.value.code == expected_code
    assert exc_info.value.msg_key == expected_msg_key
    assert exc_info.value.status_code == expected_status
    wait.assert_awaited_once_with(started["data"].run_id)


@pytest.mark.asyncio
async def test_append_asset_manifest_formats_when_connection_available(monkeypatch):
    from app.models.asset import MessageAsset

    monkeypatch.setattr(MessageAsset._meta, "default_connection", object())
    build_manifest = AsyncMock(return_value=[])
    format_manifest = Mock(return_value="")
    monkeypatch.setattr(
        chat.asset_service, "build_conversation_manifest", build_manifest
    )
    monkeypatch.setattr(chat.asset_service, "format_manifest", format_manifest)
    agent = SimpleNamespace(id=uuid4(), team_id=None)
    user = SimpleNamespace(id=uuid4())

    result = await chat._append_asset_manifest(
        "original message",
        conversation_id=uuid4(),
        agent=agent,
        user=user,
    )

    assert result == "original message"
    build_manifest.assert_awaited_once()

    format_manifest.return_value = "<available_assets>...</available_assets>"
    result = await chat._append_asset_manifest(
        "original message",
        conversation_id=uuid4(),
        agent=agent,
        user=user,
    )

    assert result == "original message\n\n<available_assets>...</available_assets>"


@pytest.mark.asyncio
async def test_message_asset_transaction_uses_db_transaction(monkeypatch):
    from app.models.asset import MessageAsset

    monkeypatch.setattr(MessageAsset._meta, "default_connection", object())
    transaction_cm = AsyncMock()
    in_transaction = Mock(return_value=transaction_cm)
    monkeypatch.setattr("app.api.v1.endpoints.chat.in_transaction", in_transaction)

    async with chat._message_asset_transaction(True):
        pass

    in_transaction.assert_called_once_with()
    transaction_cm.__aenter__.assert_awaited_once()


@pytest.mark.asyncio
async def test_attach_message_assets_persists_links(monkeypatch):
    attach = AsyncMock()
    monkeypatch.setattr(chat.asset_service, "attach_to_message", attach)
    asset = SimpleNamespace(id=uuid4())

    await chat._attach_message_assets(
        message_id=uuid4(),
        assets=[(asset, "attachment", 0)],
    )

    attach.assert_awaited_once()
    assert attach.await_args.kwargs["asset"] is asset
    assert attach.await_args.kwargs["role"] == "attachment"
    assert attach.await_args.kwargs["position"] == 0
