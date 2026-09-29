from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat
from app.models.agent_run import AgentRunMode, AgentRunStatus
from app.schemas.agent import (
    ChatRequest,
    FileUrl,
    ImageContent,
    RunStartOut,
    WorkflowAssetRef,
)
from app.schemas.response import BusinessError, ResponseCode


def test_chat_request_accepts_variable_asset_ids_without_url_values():
    asset_id = uuid4()
    request = ChatRequest(message="", variable_asset_ids=[asset_id])

    assert request.variable_asset_ids == [asset_id]
    assert request.variables == {}


def test_chat_request_accepts_workflow_asset_refs_without_text():
    reference = WorkflowAssetRef(workflow_run_id=uuid4(), ref="a1b2")

    request = ChatRequest(message="", workflow_asset_refs=[reference])

    assert request.workflow_asset_refs == [reference]


@pytest.mark.asyncio
async def test_workflow_asset_refs_are_authorized_and_bound_to_conversation(
    monkeypatch,
):
    from app.models.asset import AssetScopeType
    from app.services import asset_access

    workflow_run_id = uuid4()
    conversation_id = uuid4()
    team_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    api_key = object()
    agent = SimpleNamespace(team_id=team_id)
    image_asset = SimpleNamespace(
        id=uuid4(),
        storage_key="generated-images/2026/09/image.png",
        content_type="image/png",
        display_filename="image.png",
        size=12,
    )
    file_asset = SimpleNamespace(
        id=uuid4(),
        storage_key="sandbox-artifacts/2026/09/report.txt",
        content_type="text/plain",
        display_filename="report.txt",
        size=24,
    )
    resolve_ref = AsyncMock(side_effect=[image_asset, file_asset])
    authorize_scope = AsyncMock(side_effect=[image_asset, file_asset])
    bindings = [SimpleNamespace(ref="e5f6"), SimpleNamespace(ref="789a")]
    get_or_create_ref = AsyncMock(side_effect=bindings)
    monkeypatch.setattr(asset_access, "resolve_authorized_asset_ref", resolve_ref)
    monkeypatch.setattr(asset_access, "authorize_asset_for_scope", authorize_scope)
    monkeypatch.setattr(chat.asset_service, "get_or_create_ref", get_or_create_ref)

    assets = await chat._resolve_workflow_asset_refs(
        references=[
            WorkflowAssetRef(workflow_run_id=workflow_run_id, ref="a1b2"),
            WorkflowAssetRef(workflow_run_id=workflow_run_id, ref="c3d4"),
            WorkflowAssetRef(workflow_run_id=workflow_run_id, ref="a1b2"),
        ],
        agent=agent,
        user=user,
        api_key=api_key,
    )
    assert assets == [image_asset, file_asset]

    images, files, links = await chat._bind_workflow_assets_to_conversation(
        assets=assets,
        conversation_id=conversation_id,
        existing_asset_ids=set(),
        first_position=0,
        user=user,
        api_key=api_key,
        expected_team_id=team_id,
    )

    assert len(images) == len(files) == 1
    assert (images[0].asset_id, images[0].asset_ref, images[0].url) == (
        image_asset.id,
        "e5f6",
        "/api/v1/upload/files/generated-images/2026/09/image.png",
    )
    assert (files[0].asset_id, files[0].asset_ref, files[0].filename) == (
        file_asset.id,
        "789a",
        "report.txt",
    )
    assert files[0].url == "/api/v1/upload/files/sandbox-artifacts/2026/09/report.txt"
    assert links == [
        (image_asset, "selected_reference", 0),
        (file_asset, "selected_reference", 1),
    ]
    assert [call.args for call in resolve_ref.await_args_list] == [
        ("a1b2",),
        ("c3d4",),
    ]
    assert all(
        call.kwargs
        == {
            "scope_type": AssetScopeType.WORKFLOW_RUN,
            "scope_id": workflow_run_id,
            "user": user,
            "api_key": api_key,
            "expected_team_id": team_id,
        }
        for call in resolve_ref.await_args_list
    )
    assert [call.args for call in authorize_scope.await_args_list] == [
        (image_asset.id,),
        (file_asset.id,),
    ]
    assert all(
        call.kwargs
        == {
            "scope_type": AssetScopeType.CONVERSATION,
            "scope_id": conversation_id,
            "user": user,
            "api_key": api_key,
            "expected_team_id": team_id,
        }
        for call in authorize_scope.await_args_list
    )
    assert [call.kwargs for call in get_or_create_ref.await_args_list] == [
        {
            "scope_type": AssetScopeType.CONVERSATION,
            "scope_id": conversation_id,
            "asset": image_asset,
        },
        {
            "scope_type": AssetScopeType.CONVERSATION,
            "scope_id": conversation_id,
            "asset": file_asset,
        },
    ]


@pytest.mark.asyncio
async def test_workflow_asset_import_stops_when_source_access_is_denied(monkeypatch):
    from app.services import asset_access

    error = BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="access_denied",
        status_code=403,
    )
    resolve_ref = AsyncMock(side_effect=error)
    authorize_scope = AsyncMock()
    get_or_create_ref = AsyncMock()
    monkeypatch.setattr(asset_access, "resolve_authorized_asset_ref", resolve_ref)
    monkeypatch.setattr(asset_access, "authorize_asset_for_scope", authorize_scope)
    monkeypatch.setattr(chat.asset_service, "get_or_create_ref", get_or_create_ref)

    with pytest.raises(BusinessError) as error_info:
        await chat._resolve_workflow_asset_refs(
            references=[WorkflowAssetRef(workflow_run_id=uuid4(), ref="a1b2")],
            agent=SimpleNamespace(team_id=uuid4()),
            user=SimpleNamespace(id=uuid4()),
            api_key=object(),
        )

    assert error_info.value.status_code == 403
    authorize_scope.assert_not_awaited()
    get_or_create_ref.assert_not_awaited()


@pytest.mark.asyncio
async def test_workflow_asset_import_stops_when_destination_access_is_denied(
    monkeypatch,
):
    from app.services import asset_access

    asset = SimpleNamespace(id=uuid4())
    error = BusinessError(
        code=ResponseCode.PERMISSION_DENIED,
        msg_key="access_denied",
        status_code=403,
    )
    monkeypatch.setattr(
        asset_access, "resolve_authorized_asset_ref", AsyncMock(return_value=asset)
    )
    authorize_scope = AsyncMock(side_effect=error)
    get_or_create_ref = AsyncMock()
    monkeypatch.setattr(asset_access, "authorize_asset_for_scope", authorize_scope)
    monkeypatch.setattr(chat.asset_service, "get_or_create_ref", get_or_create_ref)

    with pytest.raises(BusinessError) as error_info:
        await chat._bind_workflow_assets_to_conversation(
            assets=[asset],
            conversation_id=uuid4(),
            existing_asset_ids=set(),
            first_position=0,
            user=SimpleNamespace(id=uuid4()),
            api_key=object(),
            expected_team_id=uuid4(),
        )

    assert error_info.value.status_code == 403
    get_or_create_ref.assert_not_awaited()


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
        assets=[(asset, "variable", 0)],
    )

    attach.assert_awaited_once()
    assert attach.await_args.kwargs["asset"] is asset
    assert attach.await_args.kwargs["role"] == "variable"
    assert attach.await_args.kwargs["position"] == 0


@pytest.mark.asyncio
async def test_resolve_variable_asset_uuid_authorizes_for_agent_team(monkeypatch):
    from app.models.asset import AssetScopeType
    from app.services import asset_access

    asset_id = uuid4()
    conversation_id = uuid4()
    asset = SimpleNamespace(id=asset_id)
    authorize = AsyncMock(return_value=asset)
    monkeypatch.setattr(asset_access, "authorize_asset_for_scope", authorize)
    binding = SimpleNamespace(ref="a1b2")
    get_or_create_ref = AsyncMock(return_value=binding)
    monkeypatch.setattr(chat.asset_service, "get_or_create_ref", get_or_create_ref)
    team_id = uuid4()
    agent = SimpleNamespace(team_id=team_id)
    user = SimpleNamespace(id=uuid4())

    resolved = await chat._resolve_message_assets(
        attachments=[asset_id],
        agent=agent,
        user=user,
        conversation_id=conversation_id,
    )

    authorize.assert_awaited_once_with(
        asset_id,
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation_id,
        user=user,
        api_key=None,
        expected_team_id=team_id,
    )
    get_or_create_ref.assert_awaited_once_with(
        scope_type=AssetScopeType.CONVERSATION,
        scope_id=conversation_id,
        asset=asset,
    )
    assert resolved == [(asset, "attachment", 0)]
