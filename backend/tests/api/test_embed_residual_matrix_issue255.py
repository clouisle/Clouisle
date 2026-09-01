from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from starlette.datastructures import Headers
from starlette.requests import Request

from app.api.v1.endpoints import embed
from app.models.agent import AgentStatus
from app.models.workflow import WorkflowStatus
from app.schemas.response import BusinessError, ResponseCode


class Query:
    def __init__(self, result):
        self.result = result

    def prefetch_related(self, *_args):
        return self

    async def first(self):
        return self.result


def request(*, origin: str | None = None, body: bytes = b"") -> Request:
    headers = Headers({"origin": origin}).raw if origin else []
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/embed",
            "headers": headers,
            "query_string": b"",
        },
        receive,
    )


def assert_error(exc_info, code: ResponseCode, status_code: int) -> None:
    assert exc_info.value.code == code
    assert exc_info.value.status_code == status_code


@pytest.mark.anyio
async def test_embed_auth_rejects_invalid_credentials_and_prefers_query_key(
    monkeypatch,
):
    authenticate = AsyncMock(return_value=(object(), object()))
    monkeypatch.setattr(embed, "_authenticate_api_key", authenticate)

    for token, authorization in [
        (None, None),
        ("wrong", None),
        (None, "Basic clou_key"),
        (None, "Bearer wrong"),
    ]:
        with pytest.raises(BusinessError) as denied:
            await embed.get_embed_auth(token, authorization)
        assert_error(denied, ResponseCode.UNAUTHORIZED, 401)

    result = await embed.get_embed_auth("clou_query", "Bearer clou_header")
    assert result == authenticate.return_value
    authenticate.assert_awaited_once_with("clou_query")

    await embed.get_embed_auth(None, "Bearer clou_header")
    authenticate.assert_awaited_with("clou_header")


def test_embed_configuration_guards_cover_disabled_and_missing_origin():
    with pytest.raises(BusinessError) as disabled:
        embed._check_embed_enabled(SimpleNamespace(embed_config=None))
    assert_error(disabled, ResponseCode.PERMISSION_DENIED, 403)

    embed._check_embed_enabled(SimpleNamespace(embed_config={"enabled": True}))
    embed._check_embed_domain(
        request(),
        SimpleNamespace(embed_config={"allowed_domains": ["example.com", "bad:port"]}),
    )


@pytest.mark.anyio
async def test_get_embed_agent_authorization_and_state_matrix(monkeypatch):
    agent_id = uuid4()
    api_key = object()
    access = AsyncMock()
    published = SimpleNamespace(
        status=AgentStatus.PUBLISHED,
        embed_config={"enabled": True, "allowed_domains": ["example.com"]},
    )
    monkeypatch.setattr(embed.deps, "check_api_key_agent_access", access)
    monkeypatch.setattr(
        embed.Agent,
        "filter",
        MagicMock(
            side_effect=[
                Query(None),
                Query(SimpleNamespace(status=AgentStatus.DRAFT)),
                Query(SimpleNamespace(status=AgentStatus.PUBLISHED, embed_config={})),
                Query(published),
            ]
        ),
    )

    with pytest.raises(BusinessError) as missing:
        await embed._get_embed_agent(agent_id, api_key, request())
    assert_error(missing, ResponseCode.AGENT_NOT_FOUND, 404)

    with pytest.raises(BusinessError) as unpublished:
        await embed._get_embed_agent(agent_id, api_key, request())
    assert_error(unpublished, ResponseCode.AGENT_NOT_FOUND, 404)

    with pytest.raises(BusinessError) as disabled:
        await embed._get_embed_agent(agent_id, api_key, request())
    assert_error(disabled, ResponseCode.PERMISSION_DENIED, 403)

    assert (
        await embed._get_embed_agent(
            agent_id, api_key, request(origin="https://example.com")
        )
        is published
    )
    assert access.await_count == 4


@pytest.mark.anyio
async def test_get_embed_workflow_authorization_and_state_matrix(monkeypatch):
    workflow_id = uuid4()
    api_key = object()
    access = AsyncMock()
    published = SimpleNamespace(
        status=WorkflowStatus.PUBLISHED,
        embed_config={"enabled": True, "allowed_domains": ["*.example.com"]},
    )
    monkeypatch.setattr(embed.deps, "check_api_key_workflow_access", access)
    monkeypatch.setattr(
        embed.Workflow,
        "filter",
        MagicMock(
            side_effect=[
                Query(None),
                Query(SimpleNamespace(status=WorkflowStatus.DRAFT)),
                Query(
                    SimpleNamespace(status=WorkflowStatus.PUBLISHED, embed_config=None)
                ),
                Query(published),
            ]
        ),
    )

    for expected_code in [
        ResponseCode.NOT_FOUND,
        ResponseCode.NOT_FOUND,
        ResponseCode.PERMISSION_DENIED,
    ]:
        with pytest.raises(BusinessError) as denied:
            await embed._get_embed_workflow(workflow_id, api_key, request())
        assert denied.value.code == expected_code

    assert (
        await embed._get_embed_workflow(
            workflow_id, api_key, request(origin="https://docs.example.com")
        )
        is published
    )
    assert access.await_count == 4


@pytest.mark.anyio
async def test_embed_conversation_messages_missing_and_success(monkeypatch):
    agent = SimpleNamespace(id=uuid4())
    user, api_key = SimpleNamespace(id=uuid4()), object()
    conversation = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(embed, "_get_embed_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        embed.Conversation,
        "filter",
        MagicMock(side_effect=[Query(None), Query(conversation)]),
    )
    visible = AsyncMock(return_value=[object()])
    payloads = AsyncMock(return_value=[{"message": "hello"}])
    monkeypatch.setattr(embed, "get_visible_conversation_messages", visible)
    monkeypatch.setattr(embed, "build_message_round_payloads", payloads)

    with pytest.raises(BusinessError) as missing:
        await embed.get_embed_conversation_messages(
            agent.id, uuid4(), request(), (user, api_key)
        )
    assert_error(missing, ResponseCode.CONVERSATION_NOT_FOUND, 404)

    response = await embed.get_embed_conversation_messages(
        agent.id, conversation.id, request(), (user, api_key)
    )
    assert response["data"] == [{"message": "hello"}]
    visible.assert_awaited_once_with(conversation.id)


@pytest.mark.anyio
async def test_embed_upload_file_delegates_request_and_auth_user(monkeypatch):
    from app.api.v1.endpoints import upload

    agent_id = uuid4()
    user, api_key = SimpleNamespace(id=uuid4()), object()
    upload_file = AsyncMock(return_value={"data": {"url": "/uploads/file.txt"}})
    monkeypatch.setattr(embed, "_get_embed_agent", AsyncMock())
    monkeypatch.setattr(upload, "upload_file", upload_file)
    upload_request = request()
    file = object()

    response = await embed.embed_upload_file(
        agent_id,
        upload_request,
        file=file,
        category="documents",
        auth_result=(user, api_key),
    )

    assert response == {"data": {"url": "/uploads/file.txt"}}
    embed._get_embed_agent.assert_awaited_once_with(agent_id, api_key, upload_request)
    upload_file.assert_awaited_once_with(
        request=upload_request,
        file=file,
        category="documents",
        current_user=user,
    )


@pytest.mark.anyio
async def test_embed_workflow_run_stream_rejects_missing_and_wrong_owner(monkeypatch):
    from app.models.workflow import WorkflowRun

    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        WorkflowRun,
        "filter",
        MagicMock(
            side_effect=[
                Query(None),
                Query(SimpleNamespace(triggered_by_id=uuid4())),
            ]
        ),
    )

    for _ in range(2):
        with pytest.raises(BusinessError) as missing:
            await embed.embed_stream_workflow_run(uuid4(), auth_result=(user, object()))
        assert_error(missing, ResponseCode.NOT_FOUND, 404)


@pytest.mark.anyio
async def test_embed_workflow_run_stream_yields_events(monkeypatch):
    from app.models.workflow import WorkflowRun
    from app.services.workflow import stream as stream_module

    run_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        WorkflowRun,
        "filter",
        MagicMock(return_value=Query(SimpleNamespace(triggered_by_id=user.id))),
    )

    async def stream_to_sse(actual_run_id, sequence):
        assert actual_run_id == str(run_id)
        assert sequence == 7
        yield "data: done\n\n"

    monkeypatch.setattr(stream_module, "stream_to_sse", stream_to_sse)
    response = await embed.embed_stream_workflow_run(
        run_id, from_sequence=7, auth_result=(user, object())
    )

    assert response.media_type == "text/event-stream"
    assert response.headers["x-accel-buffering"] == "no"
    assert [chunk async for chunk in response.body_iterator] == ["data: done\n\n"]


@pytest.mark.anyio
async def test_embed_durable_run_routes_validate_embed_access_and_delegate(monkeypatch):
    from app.api.v1.endpoints import chat
    from app.schemas.agent import ChatRequest, RunInputCreate

    agent_id, run_id = uuid4(), uuid4()
    user, api_key = SimpleNamespace(id=uuid4()), object()
    embed_agent = SimpleNamespace(id=agent_id)
    embed_access = AsyncMock(return_value=embed_agent)
    monkeypatch.setattr(embed, "_get_embed_agent", embed_access)

    start = AsyncMock(
        return_value={
            "data": {
                "run_id": run_id,
                "conversation_id": uuid4(),
                "user_message_id": uuid4(),
                "status": "queued",
                "stream_url": "/chat/runs/ignored/stream",
            }
        }
    )
    stream_result = object()
    stream = AsyncMock(return_value=stream_result)
    status_result = {"data": {"status": "running"}}
    status = AsyncMock(return_value=status_result)
    events_result = {"data": [{"sequence": 4}]}
    events = AsyncMock(return_value=events_result)
    input_result = {"data": {"status": "running"}}
    post_input = AsyncMock(return_value=input_result)
    stop_result = {"data": {"status": "stopping"}}
    stop = AsyncMock(return_value=stop_result)
    monkeypatch.setattr(chat, "start_chat_run", start)
    monkeypatch.setattr(chat, "stream_chat_run", stream)
    monkeypatch.setattr(chat, "get_run_status", status)
    monkeypatch.setattr(chat, "get_run_events", events)
    monkeypatch.setattr(chat, "post_run_input", post_input)
    monkeypatch.setattr(chat, "stop_run", stop)

    chat_request = ChatRequest(message="hello")
    request_value = request()
    started = await embed.embed_start_chat_run(
        agent_id, chat_request, request_value, (user, api_key)
    )
    assert started["data"].run_id == run_id
    assert (
        started["data"].stream_url
        == f"/embed/agents/{agent_id}/chat/runs/{run_id}/stream"
    )
    start.assert_awaited_once_with(agent_id, chat_request, (user, api_key))

    assert (
        await embed.embed_stream_chat_run(
            agent_id,
            run_id,
            request_value,
            after_sequence=-3,
            auth_result=(user, api_key),
        )
        is stream_result
    )
    stream.assert_awaited_once_with(
        agent_id=agent_id, run_id=run_id, after_sequence=0, auth_result=(user, api_key)
    )

    assert (
        await embed.embed_get_run_status(
            agent_id, run_id, request_value, (user, api_key)
        )
        is status_result
    )
    status.assert_awaited_once_with(agent_id, run_id, (user, api_key))

    assert (
        await embed.embed_get_run_events(
            agent_id,
            run_id,
            request_value,
            after_sequence=-2,
            auth_result=(user, api_key),
        )
        is events_result
    )
    events.assert_awaited_once_with(agent_id, run_id, 0, (user, api_key))

    input_body = RunInputCreate(delivery="steer", content="focus")
    assert (
        await embed.embed_post_run_input(
            agent_id, run_id, input_body, request_value, (user, api_key)
        )
        is input_result
    )
    post_input.assert_awaited_once_with(agent_id, run_id, input_body, (user, api_key))

    assert (
        await embed.embed_stop_run(agent_id, run_id, request_value, (user, api_key))
        is stop_result
    )
    stop.assert_awaited_once_with(agent_id, run_id, (user, api_key))
    assert embed_access.await_count == 6
