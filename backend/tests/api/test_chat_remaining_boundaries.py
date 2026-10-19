import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from urllib.parse import quote
from uuid import uuid4

import pytest

from app.api.v1.endpoints import chat, chat_tools
from app.models.agent import AgentVisibility
from app.schemas.response import BusinessError, ResponseCode


class _Query:
    def __init__(self, value=None):
        self.value = value

    def prefetch_related(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def using_db(self, *_args):
        return self

    def select_for_update(self, *_args):
        return self

    async def first(self):
        return self.value

    async def exists(self):
        return self.value

    async def count(self):
        return 0


class _Members:
    result = False
    calls = []

    @classmethod
    def filter(cls, **kwargs):
        cls.calls.append(kwargs)
        return _Query(cls.result)


@pytest.fixture(autouse=True)
def _reset_members():
    _Members.result = False
    _Members.calls = []


@pytest.mark.anyio
async def test_public_agent_requires_login_and_rejects_missing_agent(monkeypatch):
    with pytest.raises(BusinessError) as unauthenticated:
        await chat.get_public_agent(uuid4())
    assert unauthenticated.value.status_code == 401
    assert unauthenticated.value.msg_key == "not_authenticated"

    monkeypatch.setattr(chat.Agent, "filter", lambda **_kwargs: _Query(None))
    with pytest.raises(BusinessError) as missing:
        await chat.get_public_agent(uuid4(), SimpleNamespace(id=uuid4()))
    assert missing.value.status_code == 404
    assert missing.value.msg_key == "agent_not_found"


@pytest.mark.anyio
async def test_public_agent_private_legacy_visibility_requires_team_membership(
    monkeypatch,
):
    user = SimpleNamespace(id=uuid4(), is_superuser=False)
    agent = SimpleNamespace(
        visibility=AgentVisibility.PRIVATE,
        created_by=None,
        team_id=uuid4(),
    )
    monkeypatch.setattr(chat.Agent, "filter", lambda *_args, **_kwargs: _Query(agent))
    monkeypatch.setattr(chat, "TeamMember", _Members)

    with pytest.raises(BusinessError) as denied:
        await chat.get_public_agent(uuid4(), user)
    assert denied.value.status_code == 403
    assert denied.value.msg_key == "agent_access_denied"
    assert _Members.calls == [{"team_id": agent.team_id, "user_id": user.id}]

    _Members.result = True
    assert await chat.get_public_agent(uuid4(), user) is agent


@pytest.mark.anyio
async def test_message_asset_resolution_ignores_empty_entries_and_requires_conversation(
    monkeypatch,
):
    assert (
        await chat._resolve_message_assets(
            attachments=[{}, SimpleNamespace(asset_id=None, asset_ref=None)],
            agent=SimpleNamespace(team_id=None),
            user=SimpleNamespace(id=uuid4()),
        )
        == []
    )

    with pytest.raises(BusinessError) as denied:
        await chat._resolve_message_assets(
            attachments=[{"asset_id": uuid4()}],
            agent=SimpleNamespace(team_id=None),
            user=SimpleNamespace(id=uuid4()),
        )
    assert denied.value.code == ResponseCode.PERMISSION_DENIED


@pytest.mark.anyio
async def test_message_asset_binding_preserves_uuid_and_updates_object_attachment(
    monkeypatch,
):
    asset_id = uuid4()
    asset = SimpleNamespace(id=asset_id)
    authorize = AsyncMock(return_value=asset)
    binding = SimpleNamespace(ref="a1b2")
    bind_ref = AsyncMock(return_value=binding)
    monkeypatch.setattr(
        "app.services.asset_access.authorize_asset_for_scope", authorize
    )
    monkeypatch.setattr(chat.asset_service, "get_or_create_ref", bind_ref)
    user = SimpleNamespace(id=uuid4())
    conversation_id = uuid4()
    attachment = SimpleNamespace(asset_id=asset_id, asset_ref=None)

    results = await chat._resolve_message_assets(
        attachments=[asset_id, attachment],
        agent=SimpleNamespace(team_id=None),
        user=user,
        conversation_id=conversation_id,
    )

    assert results == [(asset, "attachment", 0), (asset, "attachment", 1)]
    assert attachment.asset_ref == "a1b2"
    assert authorize.await_count == 2
    assert bind_ref.await_count == 2


@pytest.mark.anyio
async def test_message_asset_reference_must_match_supplied_asset_id(monkeypatch):
    resolved = SimpleNamespace(id=uuid4())
    resolve = AsyncMock(return_value=resolved)
    monkeypatch.setattr(
        "app.services.asset_access.resolve_authorized_asset_ref", resolve
    )
    with pytest.raises(BusinessError) as denied:
        await chat._resolve_message_assets(
            attachments=[{"asset_id": uuid4(), "asset_ref": "abcd"}],
            agent=SimpleNamespace(team_id=None),
            user=SimpleNamespace(id=uuid4()),
            conversation_id=uuid4(),
        )
    assert denied.value.code == ResponseCode.PERMISSION_DENIED
    resolve.assert_awaited_once()


@pytest.mark.anyio
async def test_public_agent_private_creator_access_is_owner_scoped(monkeypatch):
    owner_id = uuid4()
    agent = SimpleNamespace(
        visibility=AgentVisibility.PRIVATE,
        created_by=SimpleNamespace(id=owner_id),
        team_id=uuid4(),
    )
    monkeypatch.setattr(chat.Agent, "filter", lambda *_args, **_kwargs: _Query(agent))
    monkeypatch.setattr(chat, "TeamMember", _Members)

    owner = SimpleNamespace(id=owner_id, is_superuser=False)
    assert await chat.get_public_agent(uuid4(), owner) is agent
    with pytest.raises(BusinessError) as denied:
        await chat.get_public_agent(
            uuid4(), SimpleNamespace(id=uuid4(), is_superuser=False)
        )
    assert denied.value.status_code == 403
    assert _Members.calls == []


@pytest.mark.anyio
async def test_builtin_tool_config_selects_agent_credentials_and_web_engine(
    monkeypatch,
):
    from app.llm.tools import tool_registry

    executed = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(
        tool_registry,
        "get_tool",
        lambda _name: SimpleNamespace(handler=lambda credentials=None: credentials),
    )
    monkeypatch.setattr(tool_registry, "get_sandbox_tool_class", lambda _name: None)
    monkeypatch.setattr(tool_registry, "execute", executed)
    credential_lookup = AsyncMock(return_value={"BOCHA_API_KEY": "agent-key"})
    monkeypatch.setattr(chat_tools, "_get_builtin_tool_credentials", credential_lookup)

    agent = SimpleNamespace(
        tools_config=[
            {"type": "builtin", "name": "web_search", "config": {"engine": "bocha"}}
        ]
    )
    await chat_tools.execute_tool_call("web_search", {}, agent=agent)

    assert credential_lookup.await_args.args == (
        "web_search",
        agent,
        {"engine": "bocha"},
    )
    assert executed.await_args.args[1]["search_engine"] == "bocha"
    assert executed.await_args.kwargs["credentials"] == {"BOCHA_API_KEY": "agent-key"}


@pytest.mark.anyio
async def test_memory_subgraph_normalizes_invalid_filter_and_depth(monkeypatch):
    from app.services.memory import MemoryService

    get_subgraph = AsyncMock(return_value={"entities": [], "relations": []})
    monkeypatch.setattr(MemoryService, "handle_get_memory_subgraph", get_subgraph)
    result = await chat_tools.execute_tool_call(
        "get_memory_subgraph",
        {
            "entity_ids": "not-a-list",
            "relation_types": "not-a-list",
            "max_depth": "bad",
        },
        user=SimpleNamespace(id=uuid4()),
    )

    assert json.loads(result) == {"entities": [], "relations": []}
    assert get_subgraph.await_args.kwargs["entity_ids"] == []
    assert get_subgraph.await_args.kwargs["relation_types"] is None
    assert get_subgraph.await_args.kwargs["max_depth"] == 1


@pytest.mark.anyio
async def test_append_asset_manifest_returns_manifest_only_for_empty_message(
    monkeypatch,
):
    from app.models.asset import MessageAsset

    monkeypatch.setattr(MessageAsset._meta, "default_connection", object())
    monkeypatch.setattr(
        chat.asset_service, "build_conversation_manifest", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        chat.asset_service,
        "format_manifest",
        Mock(return_value="<assets>docs</assets>"),
    )
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4())
    user = SimpleNamespace(id=uuid4())

    assert (
        await chat._append_asset_manifest(
            "",
            conversation_id=uuid4(),
            agent=agent,
            user=user,
        )
        == "<assets>docs</assets>"
    )


@pytest.mark.anyio
async def test_resolve_message_assets_skips_duplicate_workflow_run_reference(
    monkeypatch,
):
    from app.schemas.agent import WorkflowAssetRef

    run_id = uuid4()
    asset = SimpleNamespace(id=uuid4())
    resolve = AsyncMock(return_value=asset)
    monkeypatch.setattr(
        "app.services.asset_access.resolve_authorized_asset_ref", resolve
    )

    assets = await chat._resolve_workflow_asset_refs(
        references=[
            WorkflowAssetRef(workflow_run_id=run_id, ref="abcd"),
            WorkflowAssetRef(workflow_run_id=run_id, ref="abcd"),
        ],
        agent=SimpleNamespace(team_id=None),
        user=SimpleNamespace(id=uuid4()),
        api_key=None,
    )

    assert assets == [asset]
    resolve.assert_awaited_once()


@pytest.mark.anyio
async def test_resolve_message_assets_uses_reference_binding_without_rewrite(
    monkeypatch,
):
    asset_id = uuid4()
    asset = SimpleNamespace(id=asset_id)
    resolve = AsyncMock(return_value=asset)
    authorize = AsyncMock()
    monkeypatch.setattr(
        "app.services.asset_access.resolve_authorized_asset_ref", resolve
    )
    monkeypatch.setattr(
        "app.services.asset_access.authorize_asset_for_scope", authorize
    )
    attachment = {"asset_id": asset_id, "asset_ref": "b2c3"}

    results = await chat._resolve_message_assets(
        attachments=[attachment],
        agent=SimpleNamespace(team_id=None),
        user=SimpleNamespace(id=uuid4()),
        conversation_id=uuid4(),
    )

    assert results == [(asset, "selected_reference", 0)]
    assert attachment["asset_ref"] == "b2c3"
    authorize.assert_not_awaited()
    resolve.assert_awaited_once()


@pytest.mark.anyio
async def test_bind_workflow_assets_deduplicates_and_splits_images_and_files(
    monkeypatch,
):
    image_asset = SimpleNamespace(
        id=uuid4(),
        storage_key="team/2026/pic.png",
        content_type="IMAGE/PNG",
        display_filename="pic.png",
    )
    file_asset = SimpleNamespace(
        id=uuid4(),
        storage_key="team/2026/report.bin",
        content_type="application/octet-stream",
        display_filename="report.bin",
        size=2048,
    )
    assets_by_id = {image_asset.id: image_asset, file_asset.id: file_asset}
    authorize = AsyncMock(
        side_effect=lambda asset_id, **_kwargs: assets_by_id[asset_id]
    )
    binding = SimpleNamespace(ref="d4e5")
    monkeypatch.setattr(
        "app.services.asset_access.authorize_asset_for_scope", authorize
    )
    monkeypatch.setattr(
        chat.asset_service, "get_or_create_ref", AsyncMock(return_value=binding)
    )

    images, files, links = await chat._bind_workflow_assets_to_conversation(
        assets=[image_asset, image_asset, file_asset],
        conversation_id=uuid4(),
        existing_asset_ids=set(),
        first_position=3,
        user=SimpleNamespace(id=uuid4()),
        api_key=None,
        expected_team_id=None,
    )

    assert [image.asset_id for image in images] == [image_asset.id]
    assert (
        images[0].url
        == f"/api/v1/upload/files/{quote(image_asset.storage_key, safe='/')}"
    )
    assert [file.asset_id for file in files] == [file_asset.id]
    assert links == [
        (image_asset, "selected_reference", 3),
        (file_asset, "selected_reference", 4),
    ]


@pytest.mark.anyio
async def test_build_tool_call_start_sse_events_skips_calls_without_tool_name():
    named = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="web_search"),
    )
    unnamed = SimpleNamespace(id="call-2", function=SimpleNamespace(name=""))

    events = chat._build_tool_call_start_sse_events(
        [named, unnamed], {"web_search": "Web Search"}
    )

    assert len(events) == 1
    assert "tool_name" in events[0]
    assert "web_search" in events[0]


@pytest.mark.anyio
async def test_calculate_model_usage_counts_tool_calls_without_provider_totals(
    monkeypatch,
):
    monkeypatch.setattr(chat, "count_message_tokens", lambda *_a, **_k: 11)
    monkeypatch.setattr(chat, "count_tool_definition_tokens", lambda *_a, **_k: 0)
    monkeypatch.setattr(chat, "count_tokens", lambda text, *_a: len(text))
    monkeypatch.setattr(
        chat,
        "serialize_tool_calls",
        lambda tool_calls: f"[{len(tool_calls)} calls]",
    )

    prompt, completion, cache_read, cache_creation, total_input = (
        chat._calculate_model_usage(
            messages=[{"role": "user", "content": "question"}],
            content="answer",
            reasoning_content=None,
            tool_calls=[{"id": "call-1"}],
            tools=None,
            usage=None,
            model_id="unit-model",
            provider="stub",
        )
    )

    assert (prompt, completion, cache_read, cache_creation, total_input) == (
        11,
        len("answer") + len("[1 calls]"),
        0,
        0,
        11,
    )


@pytest.mark.anyio
async def test_append_round_history_entry_includes_only_provided_fields():
    round_id = uuid4()
    history: list[dict] = []

    chat.append_round_history_entry(
        history,
        role="assistant",
        content="",
        round_id=round_id,
        round_index=0,
        round_role="assistant_final",
        is_round_canonical=True,
    )

    assert history == [
        {
            "role": "assistant",
            "content": "",
            "round_id": str(round_id),
            "round_index": 0,
            "round_role": "assistant_final",
            "is_round_canonical": True,
        }
    ]


@pytest.mark.anyio
async def test_get_agent_tools_appends_attachment_tools_for_deduped_names(
    monkeypatch,
):
    from app.models.agent import RAGMode

    agent = SimpleNamespace(
        id=uuid4(),
        team_id=uuid4(),
        tools_config=[],
        enable_memory=False,
        enable_user_input_request=False,
        rag_mode=RAGMode.OFF,
        enable_attachments=True,
        enable_image_generation=False,
        enable_video_generation=False,
    )

    tools = await chat.get_agent_tools(agent)

    names = [tool["function"]["name"] for tool in tools]
    assert names == [
        "inspect_asset",
        "read_asset",
        "parse_asset",
        "materialize_asset",
    ]
    assert all(
        tool["function"]["parameters"]["properties"].get("ref", {}).get("pattern")
        == "^[0-9a-f]{4}$"
        for tool in tools
    )


@pytest.mark.anyio
async def test_run_usage_defaults_missing_and_invalid_token_values():
    from app.schemas.response import success

    message = SimpleNamespace(token_usage={"prompt": None, "completion": 4})

    assert chat._run_usage(message) == {
        "prompt_tokens": 0,
        "completion_tokens": 4,
        "total_tokens": 4,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "total_input_tokens": 0,
    }
    assert success()["msg"]


@pytest.mark.anyio
async def test_wait_for_agent_run_returns_terminal_status_and_raises_for_missing(
    monkeypatch,
):
    from app.models.agent_run import AgentRunStatus

    run_id = uuid4()
    terminal = SimpleNamespace(id=run_id, status=AgentRunStatus.COMPLETED)
    monkeypatch.setattr(
        chat._AgentRunModel, "get_or_none", AsyncMock(return_value=terminal)
    )

    assert await chat._wait_for_agent_run(run_id) is terminal

    monkeypatch.setattr(
        chat._AgentRunModel, "get_or_none", AsyncMock(return_value=None)
    )
    with pytest.raises(BusinessError) as missing:
        await chat._wait_for_agent_run(run_id)
    assert missing.value.status_code == 404
    assert missing.value.msg_key == "run_not_found"


@pytest.mark.anyio
async def test_build_non_stream_run_response_requires_canonical_message(
    monkeypatch,
):
    from app.models.agent_run import AgentRunStatus

    run = SimpleNamespace(
        id=uuid4(),
        status=AgentRunStatus.COMPLETED,
        canonical_message_id=None,
    )

    with pytest.raises(BusinessError) as missing:
        await chat._build_non_stream_run_response(run)
    assert missing.value.status_code == 500
    assert missing.value.msg_key == "llm_processing_failed"

    run.canonical_message_id = uuid4()
    monkeypatch.setattr(chat.Message, "get_or_none", AsyncMock(return_value=None))
    with pytest.raises(BusinessError) as deleted:
        await chat._build_non_stream_run_response(run)
    assert deleted.value.status_code == 404
    assert deleted.value.msg_key == "message_not_found"


@pytest.mark.anyio
async def test_build_non_stream_run_response_serializes_canonical_message(monkeypatch):
    from datetime import datetime, timezone

    from app.models.agent_run import AgentRunStatus
    from app.schemas.response import ResponseCode

    run_id = uuid4()
    conversation_id = uuid4()
    canonical_id = uuid4()
    assistant = SimpleNamespace(
        id=canonical_id,
        conversation_id=conversation_id,
        role="assistant",
        content="final answer",
        images=None,
        file_urls=None,
        tool_calls=None,
        tool_call_id=None,
        tool_name=None,
        reasoning_content=None,
        model_used=None,
        token_usage={"prompt": 9, "completion": 5, "cache_read": 2},
        duration_ms=12,
        first_token_ms=4,
        is_manually_stopped=False,
        rag_context=None,
        created_at=datetime(2026, 10, 19, tzinfo=timezone.utc),
        round_id=None,
        round_index=0,
        round_role=None,
        is_round_canonical=True,
        iteration_index=None,
        round_status=None,
        parent_id=None,
        branch_parent_id=None,
        is_active=True,
        version_number=1,
        version_count=1,
    )
    run = SimpleNamespace(
        id=run_id,
        conversation_id=conversation_id,
        status=AgentRunStatus.COMPLETED,
        canonical_message_id=canonical_id,
    )
    monkeypatch.setattr(chat.Message, "get_or_none", AsyncMock(return_value=assistant))

    result = await chat._build_non_stream_run_response(run)

    assert result["code"] == ResponseCode.SUCCESS
    assert result["data"].conversation_id == conversation_id
    assert result["data"].message.content == "final answer"
    assert result["data"].usage == {
        "prompt_tokens": 9,
        "completion_tokens": 5,
        "total_tokens": 14,
        "cache_read_tokens": 2,
        "cache_creation_tokens": 0,
        "total_input_tokens": 0,
    }


def _run_route_stubs(monkeypatch, run):
    """Stub the shared auth/owner guards used by the durable run routes."""
    current_user = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(chat.deps, "check_api_key_agent_access", AsyncMock())
    monkeypatch.setattr(chat, "_load_owned_run", AsyncMock(return_value=run))
    return current_user


@pytest.mark.anyio
async def test_get_run_status_serializes_run_without_timestamps(monkeypatch):
    from app.models.agent_run import AgentRunMode, AgentRunStatus

    run_id = uuid4()
    agent_id = uuid4()
    conversation_id = uuid4()
    run = SimpleNamespace(
        id=run_id,
        agent_id=agent_id,
        conversation_id=conversation_id,
        mode=AgentRunMode.REGENERATE,
        status=AgentRunStatus.FAILED,
        source_message_id=None,
        canonical_message_id=None,
        active_round_id=None,
        error_code="enqueue_failed",
        error_message="broker down",
        started_at=None,
        finished_at=None,
        pending_tool_call_id=None,
        pending_tool_name=None,
        pending_tool_input=None,
    )
    current_user = _run_route_stubs(monkeypatch, run)

    result = await chat.get_run_status(
        agent_id, run_id, auth_result=(current_user, None)
    )

    data = result["data"]
    assert data.id == run_id
    assert data.mode == "regenerate"
    assert data.status == "failed"
    assert data.error_code == "enqueue_failed"
    assert data.started_at is None
    assert data.finished_at is None


@pytest.mark.anyio
async def test_stream_chat_run_requires_owner_scoped_run(monkeypatch):
    from fastapi.responses import StreamingResponse

    run_id = uuid4()
    agent_id = uuid4()
    current_user = _run_route_stubs(monkeypatch, SimpleNamespace(id=run_id))

    response = await chat.stream_chat_run(
        agent_id,
        run_id,
        after_sequence=-5,
        auth_result=(current_user, None),
    )

    assert isinstance(response, StreamingResponse)
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"


@pytest.mark.anyio
async def test_get_run_events_filters_by_after_sequence(monkeypatch):
    from app.schemas.response import ResponseCode

    run_id = uuid4()
    agent_id = uuid4()
    current_user = _run_route_stubs(monkeypatch, SimpleNamespace(id=run_id))

    class _Stream:
        async def get_all_events(self):
            return [
                {
                    "run_id": str(run_id),
                    "sequence": 1,
                    "timestamp": "2026-10-19T00:00:00Z",
                    "type": "run_start",
                    "payload": {},
                },
                {
                    "run_id": str(run_id),
                    "sequence": 2,
                    "timestamp": "2026-10-19T00:00:01Z",
                    "type": "content_delta",
                    "payload": {"delta": "hello"},
                },
            ]

    monkeypatch.setattr(
        "app.services.agent_run_stream.AgentRunStream", lambda _id: _Stream()
    )

    result = await chat.get_run_events(
        agent_id, run_id, after_sequence=1, auth_result=(current_user, None)
    )

    assert result["code"] == ResponseCode.SUCCESS
    assert [event.type for event in result["data"]] == ["content_delta"]
    assert result["data"][0].sequence == 2


@pytest.mark.anyio
async def test_post_run_input_maps_delivery_kinds_and_attachments(monkeypatch):
    from app.models.agent_run import AgentRunInputKind
    from app.schemas.agent import RunInputCreate

    run_id = uuid4()
    agent_id = uuid4()
    run = SimpleNamespace(
        id=run_id,
        agent_id=agent_id,
        conversation_id=uuid4(),
        status="running",
        mode=SimpleNamespace(value="send"),
        source_message_id=None,
        canonical_message_id=None,
        active_round_id=None,
        error_code=None,
        error_message=None,
        started_at=None,
        finished_at=None,
        pending_tool_call_id=None,
        pending_tool_name=None,
        pending_tool_input=None,
    )
    current_user = _run_route_stubs(monkeypatch, run)
    enqueue = AsyncMock()
    monkeypatch.setattr("app.services.agent_run_store.enqueue_input", enqueue)

    for delivery, expected_kind in (
        ("steer", AgentRunInputKind.STEER),
        ("follow_up", AgentRunInputKind.FOLLOW_UP),
        ("stop", AgentRunInputKind.STOP),
        ("auto", AgentRunInputKind.STEER),
    ):
        enqueue.reset_mock()
        result = await chat.post_run_input(
            agent_id,
            run_id,
            RunInputCreate(
                delivery=delivery,
                content="keep going",
                attachments=[{"asset_id": "abcd"}],
                request_id="req-1",
            ),
            auth_result=(current_user, None),
        )

        assert result["data"].id == run_id
        assert enqueue.await_args.kwargs["kind"] == expected_kind
        assert enqueue.await_args.kwargs["content"] == "keep going"
        assert enqueue.await_args.kwargs["attachment_meta"] == {
            "attachments": [{"asset_id": "abcd"}]
        }
        assert enqueue.await_args.kwargs["request_id"] == "req-1"


@pytest.mark.anyio
async def test_load_owned_run_rejects_run_from_other_agent(monkeypatch):
    from app.models.agent_run import AgentRun

    run_id = uuid4()
    agent_id = uuid4()
    monkeypatch.setattr(AgentRun, "get_or_none", AsyncMock(return_value=None))

    with pytest.raises(BusinessError) as missing:
        await chat._load_owned_run(
            agent_id, run_id, SimpleNamespace(id=uuid4(), is_superuser=False)
        )

    assert missing.value.status_code == 404
    assert missing.value.msg_key == "run_not_found"


@pytest.mark.anyio
async def test_load_owned_run_rejects_foreign_conversation(monkeypatch):
    from app.models.agent_run import AgentRun
    from app.models.agent import Conversation as _Conv

    agent_id = uuid4()
    run_id = uuid4()
    conversation_id = uuid4()
    run = SimpleNamespace(id=run_id, agent_id=agent_id, conversation_id=conversation_id)
    monkeypatch.setattr(AgentRun, "get_or_none", AsyncMock(return_value=run))
    monkeypatch.setattr(_Conv, "get_or_none", AsyncMock(return_value=None))

    with pytest.raises(BusinessError) as denied:
        await chat._load_owned_run(
            agent_id, run_id, SimpleNamespace(id=uuid4(), is_superuser=False)
        )

    assert denied.value.status_code == 403
    assert denied.value.msg_key == "access_denied"


@pytest.mark.anyio
async def test_stop_run_terminal_status_is_idempotent_noop(monkeypatch):
    from app.models.agent_run import AgentRunMode, AgentRunStatus

    run = SimpleNamespace(
        id=uuid4(),
        agent_id=uuid4(),
        conversation_id=uuid4(),
        mode=AgentRunMode.SEND,
        status=AgentRunStatus.COMPLETED,
        source_message_id=None,
        canonical_message_id=None,
        active_round_id=None,
        error_code=None,
        error_message=None,
        started_at=None,
        finished_at=None,
        pending_tool_call_id=None,
        pending_tool_name=None,
        pending_tool_input=None,
    )
    current_user = _run_route_stubs(monkeypatch, run)

    result = await chat.stop_run(uuid4(), run.id, auth_result=(current_user, None))

    assert result["data"].status == "completed"


@pytest.mark.anyio
async def test_stop_run_queued_revokes_celery_task_and_swallows_revoke_failures(
    monkeypatch,
):
    from app.models.agent_run import AgentRunStatus
    from app.services import agent_run_stream, agent_run_store

    run_id = uuid4()
    stopped = SimpleNamespace(
        id=run_id,
        agent_id=uuid4(),
        conversation_id=uuid4(),
        mode=SimpleNamespace(value="send"),
        status=AgentRunStatus.STOPPED,
        source_message_id=None,
        canonical_message_id=None,
        active_round_id=None,
        error_code=None,
        error_message=None,
        started_at=None,
        finished_at=None,
        pending_tool_call_id=None,
        pending_tool_name=None,
        pending_tool_input=None,
        celery_task_id="task-1",
    )
    current_user = _run_route_stubs(
        monkeypatch, SimpleNamespace(id=run_id, status=AgentRunStatus.QUEUED)
    )
    monkeypatch.setattr(
        agent_run_store, "stop_queued_run", AsyncMock(return_value=stopped)
    )
    stream = SimpleNamespace(seed_sequence=AsyncMock(), publish=AsyncMock())
    monkeypatch.setattr(agent_run_stream, "AgentRunStream", lambda _id: stream)

    revoke = Mock(side_effect=RuntimeError("broker unreachable"))
    control = SimpleNamespace(revoke=revoke)
    monkeypatch.setattr("app.core.celery.celery_app", SimpleNamespace(control=control))

    result = await chat.stop_run(uuid4(), run_id, auth_result=(current_user, None))

    assert result["data"].id == stopped.id
    assert result["data"].status == "stopped"
    revoke.assert_called_once_with("task-1", terminate=True)
    stream.publish.assert_awaited_once_with("run_end", {"status": "stopped"})


@pytest.mark.anyio
async def test_stop_run_running_transitions_and_queues_stop(monkeypatch):
    from app.models.agent_run import AgentRunStatus
    from app.services import agent_run_store

    run_id = uuid4()
    stopping = SimpleNamespace(
        id=run_id,
        agent_id=uuid4(),
        conversation_id=uuid4(),
        mode=SimpleNamespace(value="send"),
        status=AgentRunStatus.STOPPING,
        source_message_id=None,
        canonical_message_id=None,
        active_round_id=None,
        error_code=None,
        error_message=None,
        started_at=None,
        finished_at=None,
        pending_tool_call_id=None,
        pending_tool_name=None,
        pending_tool_input=None,
    )
    current_user = _run_route_stubs(
        monkeypatch, SimpleNamespace(id=run_id, status=AgentRunStatus.RUNNING)
    )
    transition = AsyncMock(return_value=stopping)
    enqueue = AsyncMock()
    monkeypatch.setattr(agent_run_store, "transition_run_if_status", transition)
    monkeypatch.setattr(agent_run_store, "enqueue_input", enqueue)

    result = await chat.stop_run(uuid4(), run_id, auth_result=(current_user, None))

    assert result["data"].id == run_id
    assert result["data"].status == "stopping"
    assert transition.await_args.args[1:] == (
        AgentRunStatus.RUNNING,
        AgentRunStatus.STOPPING,
    )
    assert transition.await_args.args[0].status == AgentRunStatus.RUNNING
    enqueue.assert_awaited_once_with(run_id=run_id, kind="stop")


@pytest.mark.anyio
async def test_post_run_answer_records_celery_task_id_on_successful_enqueue(
    monkeypatch,
):
    from app.models.agent_run import AgentRunStatus
    from app.schemas.agent import RunAnswerCreate
    from app.tasks.agent import run_agent_task

    agent_id = uuid4()
    run_id = uuid4()
    original = SimpleNamespace(id=run_id, status=AgentRunStatus.WAITING)
    resumed = SimpleNamespace(
        worker_payload={"run_id": str(run_id)},
        save=AsyncMock(),
    )
    current_user = _run_route_stubs(monkeypatch, original)
    monkeypatch.setattr(
        "app.services.agent_run_store.submit_user_answers",
        AsyncMock(return_value=resumed),
    )
    monkeypatch.setattr(
        run_agent_task,
        "apply_async",
        Mock(return_value=SimpleNamespace(id="task-9")),
    )
    monkeypatch.setattr(chat, "_run_to_out", lambda run: run)

    result = await chat.post_run_answer(
        agent_id,
        run_id,
        RunAnswerCreate(tool_call_id="call-1", answers={}),
        auth_result=(current_user, None),
    )

    assert result["data"] is resumed
    assert resumed.celery_task_id == "task-9"
    resumed.save.assert_awaited_once_with(update_fields=["celery_task_id"])


@pytest.mark.anyio
async def test_edit_user_message_stream_copies_attachments_when_enabled(monkeypatch):
    from app.models.asset import MessageAsset
    from app.schemas.agent import EditMessageRequest

    agent_id = uuid4()
    message_id = uuid4()
    user = SimpleNamespace(id=uuid4(), locale="en")
    message = SimpleNamespace(
        id=message_id,
        conversation_id=uuid4(),
        role="user",
        content="original",
        images=None,
        file_urls=None,
        version_number=1,
        branch_parent_id=None,
        round_status=None,
    )
    conversation = SimpleNamespace(
        id=message.conversation_id, agent_id=agent_id, user=user
    )
    agent = SimpleNamespace(id=agent_id, team_id=uuid4(), rag_mode="disabled")
    edited_user = SimpleNamespace(id=uuid4())
    assistant = SimpleNamespace(id=uuid4())

    monkeypatch.setattr(
        chat.Message, "filter", lambda *_args, **_kwargs: _Query(message)
    )
    monkeypatch.setattr(
        chat.Conversation, "filter", lambda *_args, **_kwargs: _Query(conversation)
    )
    monkeypatch.setattr(chat.Agent, "filter", lambda *_args, **_kwargs: _Query(agent))
    monkeypatch.setattr(
        chat, "get_prefix_path_before", AsyncMock(return_value=[message])
    )
    monkeypatch.setattr(chat, "get_version_root_id", lambda _message: message_id)
    monkeypatch.setattr(
        chat,
        "get_branch_version_count",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        chat.Message,
        "create",
        AsyncMock(side_effect=[edited_user, assistant]),
    )
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(chat, "in_transaction", MagicMock(return_value=transaction))
    monkeypatch.setattr(chat, "activate_conversation_branch", AsyncMock())
    monkeypatch.setattr(MessageAsset._meta, "default_connection", object())
    copy_attachments = AsyncMock()
    monkeypatch.setattr(
        chat.asset_service, "copy_message_attachments", copy_attachments
    )
    enqueue = AsyncMock(return_value={"data": {"run_id": uuid4()}})
    monkeypatch.setattr(chat, "_enqueue_existing_message_run", enqueue)
    monkeypatch.setattr(
        chat, "_stream_queued_run", lambda started: SimpleNamespace(started=started)
    )

    response = await chat.edit_user_message_stream(
        agent_id,
        message_id,
        EditMessageRequest(content="updated"),
        SimpleNamespace(),
        user,
    )

    copy_attachments.assert_awaited_once_with(
        source_message_id=message_id, target_message_id=edited_user.id
    )
    assert enqueue.await_args.kwargs["mode"].value == "edit"
    assert enqueue.await_args.kwargs["message_start"]["edited_version_count"] == 1
    assert response.started is enqueue.return_value


@pytest.mark.anyio
async def test_regenerate_message_auto_rag_prepends_retrieved_contexts(monkeypatch):
    from app.models.agent import RAGMode
    from app.schemas.agent import RegenerateRequest

    agent_id = uuid4()
    message_id = uuid4()
    user = SimpleNamespace(id=uuid4(), locale="en")
    user_message = SimpleNamespace(
        id=uuid4(),
        role="user",
        content="what changed?",
        images=None,
        file_urls=None,
        created_at=None,
    )
    assistant_message = SimpleNamespace(
        id=message_id,
        conversation_id=uuid4(),
        role="assistant",
        content="old answer",
        round_status="error",
        branch_parent_id=None,
        version_number=2,
        images=None,
        file_urls=None,
        save=AsyncMock(),
    )
    conversation = SimpleNamespace(
        id=assistant_message.conversation_id, agent_id=agent_id, user=user
    )
    agent = SimpleNamespace(id=agent_id, team_id=uuid4(), rag_mode=RAGMode.AUTO)
    retried = SimpleNamespace(id=message_id)

    monkeypatch.setattr(
        chat.Message, "filter", lambda *_args, **_kwargs: _Query(assistant_message)
    )
    monkeypatch.setattr(
        chat.Conversation, "filter", lambda *_args, **_kwargs: _Query(conversation)
    )
    monkeypatch.setattr(chat.Agent, "filter", lambda *_args, **_kwargs: _Query(agent))
    monkeypatch.setattr(
        chat, "get_prefix_path_before", AsyncMock(return_value=[user_message])
    )
    monkeypatch.setattr(chat, "get_version_root_id", lambda _message: message_id)
    monkeypatch.setattr(chat, "get_branch_version_count", AsyncMock(return_value=1))
    monkeypatch.setattr(chat.AgentKnowledgeBase, "exists", AsyncMock(return_value=True))
    retrieve = AsyncMock(return_value=[{"content": "release notes"}])
    monkeypatch.setattr(chat, "perform_rag_retrieval", retrieve)
    monkeypatch.setattr(
        chat,
        "aggregate_rag_contexts",
        lambda contexts: contexts,
    )
    monkeypatch.setattr(assistant_message, "save", AsyncMock())
    enqueue = AsyncMock(return_value={"data": {"run_id": uuid4()}})
    monkeypatch.setattr(chat, "_enqueue_existing_message_run", enqueue)
    monkeypatch.setattr(
        chat, "_stream_queued_run", lambda started: SimpleNamespace(started=started)
    )

    await chat.regenerate_message(
        agent_id,
        message_id,
        RegenerateRequest(),
        SimpleNamespace(),
        user,
    )

    retrieve.assert_awaited_once()
    assert retrieve.await_args.args[2] == "what changed?"
    assert enqueue.await_args.kwargs["in_place_retry"] is True
    assert enqueue.await_args.kwargs["created_message_count"] == 0
    assert enqueue.await_args.kwargs["message_start"]["version_count"] == 1
    assert "parent_id" not in enqueue.await_args.kwargs["message_start"]
    assert assistant_message.round_status is None
    assert assistant_message.content == ""
    assert retried.id == message_id


@pytest.mark.anyio
async def test_regenerate_message_creates_new_version_without_parent_id_when_prefixless(
    monkeypatch,
):
    from app.schemas.agent import RegenerateRequest

    agent_id = uuid4()
    message_id = uuid4()
    user = SimpleNamespace(id=uuid4(), locale="en")
    user_message = SimpleNamespace(
        id=uuid4(),
        role="user",
        content="ask again",
        images=None,
        file_urls=None,
        created_at=None,
    )
    assistant_message = SimpleNamespace(
        id=message_id,
        conversation_id=uuid4(),
        role="assistant",
        content="answer",
        round_status=None,
        branch_parent_id=uuid4(),
        version_number=1,
        images=None,
        file_urls=None,
    )
    conversation = SimpleNamespace(
        id=assistant_message.conversation_id, agent_id=agent_id, user=user
    )
    agent = SimpleNamespace(id=agent_id, team_id=uuid4(), rag_mode="disabled")
    created = SimpleNamespace(id=uuid4())

    monkeypatch.setattr(
        chat.Message, "filter", lambda *_args, **_kwargs: _Query(assistant_message)
    )
    monkeypatch.setattr(
        chat.Conversation, "filter", lambda *_args, **_kwargs: _Query(conversation)
    )
    monkeypatch.setattr(chat.Agent, "filter", lambda *_args, **_kwargs: _Query(agent))
    monkeypatch.setattr(
        chat, "get_prefix_path_before", AsyncMock(return_value=[user_message])
    )
    monkeypatch.setattr(chat, "get_version_root_id", lambda _message: message_id)
    monkeypatch.setattr(chat, "get_branch_version_count", AsyncMock(return_value=2))
    monkeypatch.setattr(
        chat.AgentKnowledgeBase, "exists", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(chat.Message, "create", AsyncMock(return_value=created))
    enqueue = AsyncMock(return_value={"data": {"run_id": uuid4()}})
    monkeypatch.setattr(chat, "_enqueue_existing_message_run", enqueue)
    monkeypatch.setattr(
        chat, "_stream_queued_run", lambda started: SimpleNamespace(started=started)
    )

    await chat.regenerate_message(
        agent_id,
        message_id,
        RegenerateRequest(),
        SimpleNamespace(),
        user,
    )

    create_kwargs = chat.Message.create.await_args.kwargs
    assert create_kwargs["branch_parent_id"] == assistant_message.branch_parent_id
    assert create_kwargs["version_number"] == 3
    assert enqueue.await_args.kwargs["created_message_count"] == 1
    assert enqueue.await_args.kwargs["message_start"] == {
        "version_number": 3,
        "version_count": 3,
        "parent_id": str(message_id),
    }


@pytest.mark.anyio
async def test_enqueue_existing_message_run_marks_failure_when_broker_rejects(
    monkeypatch,
):
    from app.models.agent_run import AgentRunStatus
    from app.tasks.agent import run_agent_task

    run_id = uuid4()
    conversation_id = uuid4()
    user_message_id = uuid4()
    agent = SimpleNamespace(id=uuid4(), team_id=None, name="Agent")
    conversation = SimpleNamespace(id=conversation_id)
    user = SimpleNamespace(id=uuid4())
    run = SimpleNamespace(
        id=run_id,
        status=AgentRunStatus.QUEUED,
        active_round_id=None,
        canonical_message_id=None,
        worker_payload=None,
        celery_task_id=None,
    )
    saves: list[list[str]] = []
    round_id = uuid4()

    async def _save(self, update_fields=None):
        saves.append(update_fields)

    run.save = _save.__get__(run, type(run))
    created = run
    monkeypatch.setattr(
        "app.services.agent_run_store.create_run", AsyncMock(return_value=created)
    )
    monkeypatch.setattr(
        "app.services.agent_run_worker.build_payload",
        Mock(return_value={"run_id": str(run_id)}),
    )
    monkeypatch.setattr(
        run_agent_task,
        "apply_async",
        Mock(side_effect=RuntimeError("broker down")),
    )
    transition = AsyncMock()
    monkeypatch.setattr(
        "app.services.agent_run_store.transition_run_if_status", transition
    )

    with pytest.raises(RuntimeError, match="broker down"):
        await chat._enqueue_existing_message_run(
            agent=agent,
            conversation=conversation,
            current_user=user,
            mode=SimpleNamespace(value="send"),
            user_message=SimpleNamespace(id=user_message_id),
            message="hello",
            round_id=round_id,
            source_message_id=user_message_id,
            canonical_message_id=user_message_id,
            branch_parent_id=None,
        )

    assert transition.await_args.args[0] is created
    assert transition.await_args.args[1:] == (
        AgentRunStatus.QUEUED,
        AgentRunStatus.FAILED,
    )
    assert transition.await_args.kwargs == {
        "error_code": "enqueue_failed",
        "error_message": "broker down",
    }
    assert run.worker_payload == {"run_id": str(run_id)}
    assert ["worker_payload"] in saves


@pytest.mark.anyio
async def test_enqueue_existing_message_run_records_celery_task_id(monkeypatch):
    from app.models.agent_run import AgentRunStatus
    from app.tasks.agent import run_agent_task

    run_id = uuid4()
    conversation_id = uuid4()
    user_message_id = uuid4()
    agent = SimpleNamespace(id=uuid4(), team_id=uuid4(), name="Agent")
    run = SimpleNamespace(
        id=run_id,
        status=AgentRunStatus.QUEUED,
        active_round_id=None,
        canonical_message_id=None,
        worker_payload=None,
        celery_task_id=None,
    )
    saves: list[list[str]] = []

    async def _save(self, update_fields=None):
        saves.append(update_fields)

    run.save = _save.__get__(run, type(run))
    monkeypatch.setattr(
        "app.services.agent_run_store.create_run", AsyncMock(return_value=run)
    )
    monkeypatch.setattr(
        "app.services.agent_run_worker.build_payload",
        Mock(return_value={"run_id": str(run_id)}),
    )
    monkeypatch.setattr(
        run_agent_task,
        "apply_async",
        Mock(return_value=SimpleNamespace(id="task-42")),
    )

    result = await chat._enqueue_existing_message_run(
        agent=agent,
        conversation=SimpleNamespace(id=conversation_id),
        current_user=SimpleNamespace(id=uuid4()),
        mode=SimpleNamespace(value="send"),
        user_message=SimpleNamespace(id=user_message_id),
        message="hello",
        round_id=uuid4(),
        source_message_id=user_message_id,
        canonical_message_id=user_message_id,
        branch_parent_id=None,
    )

    assert run.celery_task_id == "task-42"
    assert run.active_round_id is not None
    assert run.canonical_message_id == user_message_id
    assert ["celery_task_id"] in saves
    assert result["data"].run_id == run_id
    assert result["data"].status == AgentRunStatus.QUEUED.value
    assert result["data"].stream_url == f"/agents/{agent.id}/chat/runs/{run_id}/stream"
