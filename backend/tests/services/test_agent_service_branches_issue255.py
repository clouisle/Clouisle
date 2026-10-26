import importlib
import json
import typing
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch
from uuid import uuid4

import pytest

from app.llm.types import FunctionDefinition, ToolDefinition
from app.models.agent import RAGMode

typing.TYPE_CHECKING = True
AgentService = importlib.import_module("app.services.agent").AgentService
typing.TYPE_CHECKING = False


def _agent(**overrides):
    values = {
        "id": uuid4(),
        "team_id": None,
        "model_id": None,
        "system_prompt": "",
        "tools_config": [],
        "enable_image_generation": False,
        "enable_video_generation": False,
        "rag_mode": RAGMode.OFF,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _tool(name: str) -> ToolDefinition:
    return ToolDefinition(
        type="function",
        function=FunctionDefinition(
            name=name,
            description=name,
            parameters={"type": "object", "properties": {}},
        ),
    )


@pytest.mark.anyio
async def test_agent_service_build_messages_covers_context_history_and_rag(monkeypatch):
    service = AgentService()
    monkeypatch.setattr(
        service,
        "_retrieve_rag_context",
        AsyncMock(return_value="retrieved text"),
    )

    messages = await service._build_messages(
        agent=_agent(system_prompt="Instructions", rag_mode=RAGMode.AUTO),
        message="current",
        context={"account": "demo"},
        conversation_history=[
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
            {"role": "system", "content": "override"},
            {"role": "ignored", "content": "skip"},
        ],
    )

    assert [message.role.value for message in messages] == [
        "system",
        "user",
        "assistant",
        "system",
        "system",
        "user",
    ]
    assert "- account: demo" in messages[0].content
    assert messages[-2].content == "Relevant context:\nretrieved text"


@pytest.mark.anyio
async def test_build_messages_describes_workflow_files_without_inlining_text():
    service = AgentService()

    messages = await service._build_messages(
        agent=_agent(enable_attachments=True),
        message="current",
        files=[
            {
                "filename": "report.txt",
                "url": "https://example.test/report.txt",
                "mime_type": "text/plain",
                "size": 11,
            }
        ],
    )

    user_content = messages[-1].content
    assert isinstance(user_content, list)
    payload = json.loads(user_content[-1].text)
    assert payload["documents"] == [
        {
            "filename": "report.txt",
            "mime_type": "text/plain",
            "size": 11,
            "reading": (
                "Use list_assets to discover a ref, then read_asset for bounded "
                "lines and search_asset to locate text; continue until eof."
            ),
        }
    ]
    assert "content" not in payload["documents"][0]


@pytest.mark.anyio
async def test_get_agent_tools_registers_shared_asset_tools():
    service = AgentService()

    tools = await service._get_agent_tools(_agent(enable_attachments=True))

    names = {tool.function.name for tool in tools}
    assert {
        "list_assets",
        "view_asset",
        "inspect_asset",
        "read_asset",
        "search_asset",
        "materialize_asset",
    } <= names
    assert "parse_asset" not in names


@pytest.mark.anyio
async def test_get_agent_tools_filters_document_readers_for_web_tools_only():
    service = AgentService()

    web_only = await service._get_agent_tools(
        _agent(
            enable_attachments=False,
            tools_config=[{"type": "builtin", "name": "fetch_webpage"}],
        )
    )
    names = {tool.function.name for tool in web_only}
    assert {"list_assets", "inspect_asset", "read_asset", "search_asset"} <= names
    assert "view_asset" not in names
    assert "materialize_asset" not in names

    bare = await service._get_agent_tools(
        _agent(enable_attachments=False, tools_config=[])
    )
    assert not {tool.function.name for tool in bare} & {
        "list_assets",
        "view_asset",
        "inspect_asset",
        "read_asset",
        "search_asset",
        "materialize_asset",
    }


@pytest.mark.anyio
async def test_bind_scoped_attachments_registers_upload_url():
    from app.models.asset import AssetScopeType
    from app.services.asset_url_import import InternalDocument

    team_id = uuid4()
    run_id = uuid4()
    user_id = uuid4()
    asset = SimpleNamespace(
        id=uuid4(),
        storage_key="general/2026/10/report.txt",
        content_type="text/plain",
        display_filename="report.txt",
        size=11,
    )
    user = SimpleNamespace(id=user_id)
    load = AsyncMock(
        return_value=InternalDocument(
            asset=asset,
            ref="a1b2",
            url="/api/v1/upload/files/general/2026/10/report.txt",
        )
    )
    service = AgentService()

    with (
        patch("app.services.asset_url_import.load_url_document", load),
        patch(
            "app.services.asset_access.authorize_asset_scope",
            AsyncMock(return_value=team_id),
        ),
        patch("app.models.user.User.get_or_none", AsyncMock(return_value=user)),
    ):
        _, files = await service._bind_scoped_attachments(
            agent=_agent(team_id=team_id, enable_attachments=True),
            images=[],
            files=["/api/v1/upload/files/general/2026/10/report.txt"],
            user_id=str(user_id),
            workflow_run_id=run_id,
        )

    assert files == [
        {
            "asset_ref": "a1b2",
            "asset_id": str(asset.id),
            "url": "/api/v1/upload/files/general/2026/10/report.txt",
            "filename": "report.txt",
            "mime_type": "text/plain",
            "size": 11,
        }
    ]
    load.assert_awaited_once()
    assert load.await_args.kwargs["scope_type"] == AssetScopeType.WORKFLOW_RUN
    assert load.await_args.kwargs["scope_id"] == run_id
    assert load.await_args.kwargs["user"] is user
    assert load.await_args.kwargs["max_bytes"] == 10 * 1024 * 1024


@pytest.mark.anyio
async def test_bind_scoped_attachments_resolves_private_asset_id():
    team_id = uuid4()
    run_id = uuid4()
    user_id = uuid4()
    asset_id = uuid4()
    asset = SimpleNamespace(
        id=asset_id,
        storage_key="general/2026/10/private.txt",
        content_type="text/plain",
        display_filename="private.txt",
        size=4,
    )
    user = SimpleNamespace(id=user_id)
    authorize = AsyncMock(return_value=asset)
    service = AgentService()

    with (
        patch("app.services.asset_access.authorize_asset_for_scope", authorize),
        patch(
            "app.services.asset_access.authorize_asset_scope",
            AsyncMock(return_value=team_id),
        ),
        patch(
            "app.services.asset.asset_service.get_or_create_ref",
            AsyncMock(return_value=SimpleNamespace(ref="c3d4")),
        ),
        patch("app.models.user.User.get_or_none", AsyncMock(return_value=user)),
    ):
        _, files = await service._bind_scoped_attachments(
            agent=_agent(team_id=team_id, enable_attachments=True),
            images=None,
            files=[{"asset_id": str(asset_id)}],
            user_id=str(user_id),
            workflow_run_id=run_id,
        )

    assert files[0]["asset_ref"] == "c3d4"
    assert authorize.await_args.args[0] == asset_id
    assert authorize.await_args.kwargs["user"] is user


@pytest.mark.anyio
async def test_bind_scoped_attachments_registers_external_url():
    from app.services.asset_url_import import ExternalDocument, ScopedDocument

    team_id = uuid4()
    run_id = uuid4()
    user_id = uuid4()
    asset = SimpleNamespace(
        id=uuid4(),
        storage_key="general/2026/10/report.txt",
        content_type="text/plain",
        display_filename="report.txt",
        size=5,
    )
    user = SimpleNamespace(id=user_id)
    load = AsyncMock(
        return_value=ExternalDocument(
            content=b"hello",
            content_type="text/plain",
            filename="report.txt",
            url="https://example.test/files/report.txt",
            final_url="https://cdn.example.test/report.txt",
        )
    )
    persist = AsyncMock(return_value=ScopedDocument(asset=asset, ref="a1b2"))

    with (
        patch("app.services.asset_url_import.load_url_document", load),
        patch("app.services.asset_url_import.persist_scoped_document", persist),
        patch(
            "app.services.asset_access.authorize_asset_scope",
            AsyncMock(return_value=team_id),
        ),
        patch("app.models.user.User.get_or_none", AsyncMock(return_value=user)),
    ):
        _, files = await AgentService()._bind_scoped_attachments(
            agent=_agent(team_id=team_id, enable_attachments=True),
            images=None,
            files=["https://example.test/files/report.txt"],
            user_id=str(user_id),
            workflow_run_id=run_id,
        )

    assert files[0]["asset_ref"] == "a1b2"
    assert files[0]["filename"] == "report.txt"
    persist.assert_awaited_once()
    assert persist.await_args.args[0] == b"hello"
    assert persist.await_args.kwargs["user"] is user
    assert persist.await_args.kwargs["provenance"] == {
        "origin": "external_url",
        "url": "https://example.test/files/report.txt",
        "final_url": "https://cdn.example.test/report.txt",
    }


@pytest.mark.anyio
async def test_bind_scoped_attachments_skips_empty_items_and_data_provenance():
    from app.services.asset_url_import import ExternalDocument, ScopedDocument

    team_id = uuid4()
    run_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    asset = SimpleNamespace(
        id=uuid4(),
        storage_key="general/2026/10/data.txt",
        content_type="text/plain",
        display_filename="data.txt",
        size=1,
    )
    load = AsyncMock(
        return_value=ExternalDocument(
            content=b"x",
            content_type="text/plain",
            filename="data.txt",
            url="data:text/plain;base64,eA==",
            final_url="data:text/plain;base64,eA==",
        )
    )
    persist = AsyncMock(return_value=ScopedDocument(asset=asset, ref="f1"))

    disabled_images, disabled_files = await AgentService()._bind_scoped_attachments(
        agent=_agent(enable_attachments=False),
        images=None,
        files=["https://example.test/x"],
        user_id=None,
    )
    assert disabled_images is None
    assert disabled_files == ["https://example.test/x"]

    empty_images, empty_files = await AgentService()._bind_scoped_attachments(
        agent=_agent(enable_attachments=True),
        images=None,
        files=None,
        user_id=None,
    )
    assert empty_images is None
    assert empty_files is None

    with (
        patch("app.services.asset_url_import.load_url_document", load),
        patch("app.services.asset_url_import.persist_scoped_document", persist),
        patch(
            "app.services.asset_access.authorize_asset_scope",
            AsyncMock(return_value=team_id),
        ),
        patch("app.models.user.User.get_or_none", AsyncMock(return_value=user)),
    ):
        images, files = await AgentService()._bind_scoped_attachments(
            agent=_agent(team_id=team_id, enable_attachments=True),
            images=[None, ""],
            files=["data:text/plain;base64,eA=="],
            user_id=str(user.id),
            workflow_run_id=run_id,
        )

    assert images == []
    assert files[0]["asset_ref"] == "f1"
    assert persist.await_args.kwargs["provenance"] == {
        "origin": "external_url",
        "url": None,
        "final_url": None,
    }


@pytest.mark.anyio
async def test_execute_builtin_tool_passes_resolved_user():
    service = AgentService()
    team_id = uuid4()
    user = SimpleNamespace(id=uuid4())
    tool_call = SimpleNamespace(
        id="call-time",
        function=SimpleNamespace(name="get_current_time", arguments="{}"),
    )
    execute = AsyncMock(return_value={"datetime": "now"})

    with (
        patch(
            "app.services.tool.ToolExecutor.execute_builtin_tool",
            new=execute,
        ),
        patch("app.models.user.User.get_or_none", AsyncMock(return_value=user)),
    ):
        result = await service._execute_tool(
            _agent(team_id=team_id),
            tool_call,
            user_id=str(user.id),
        )

    assert result == {"datetime": "now"}
    assert execute.await_args.kwargs["user"] is user
    assert execute.await_args.kwargs["team_id"] == team_id
    assert execute.await_args.kwargs["tool_name"] == "get_current_time"


@pytest.mark.anyio
async def test_bind_scoped_attachments_rejects_invalid_ids_and_missing_auth():
    from app.schemas.response import BusinessError

    service = AgentService()
    agent = _agent(team_id=uuid4(), enable_attachments=True)

    with (
        patch(
            "app.services.asset_access.authorize_asset_scope",
            AsyncMock(return_value=uuid4()),
        ),
        patch(
            "app.models.user.User.get_or_none",
            AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        ),
        pytest.raises(BusinessError),
    ):
        await service._bind_scoped_attachments(
            agent=agent,
            images=None,
            files=[{"asset_id": "not-a-uuid"}],
            user_id=str(uuid4()),
            workflow_run_id=uuid4(),
        )

    with pytest.raises(BusinessError):
        await service._bind_scoped_attachments(
            agent=agent,
            images=None,
            files=["https://example.test/file.txt"],
            user_id=None,
            conversation_id=uuid4(),
        )

    with pytest.raises(BusinessError):
        await service._bind_scoped_attachments(
            agent=agent,
            images=None,
            files=["https://example.test/file.txt"],
            user_id=None,
        )


@pytest.mark.anyio
async def test_bind_scoped_attachments_binds_image_without_file_metadata():
    from app.services.asset_url_import import InternalDocument

    team_id = uuid4()
    run_id = uuid4()
    user_id = uuid4()
    asset = SimpleNamespace(
        id=uuid4(),
        storage_key="general/2026/10/photo.png",
        content_type="image/png",
        display_filename="photo.png",
        size=9,
    )
    user = SimpleNamespace(id=user_id)
    load = AsyncMock(
        return_value=InternalDocument(
            asset=asset,
            ref="e5f6",
            url="/api/v1/upload/files/general/2026/10/photo.png",
        )
    )

    with (
        patch("app.services.asset_url_import.load_url_document", load),
        patch(
            "app.services.asset_access.authorize_asset_scope",
            AsyncMock(return_value=team_id),
        ),
        patch("app.models.user.User.get_or_none", AsyncMock(return_value=user)),
    ):
        images, _ = await AgentService()._bind_scoped_attachments(
            agent=_agent(team_id=team_id, enable_attachments=True),
            images=["/api/v1/upload/files/general/2026/10/photo.png"],
            files=None,
            user_id=str(user_id),
            workflow_run_id=run_id,
        )

    assert images == [
        {
            "asset_ref": "e5f6",
            "asset_id": str(asset.id),
            "url": "/api/v1/upload/files/general/2026/10/photo.png",
        }
    ]


@pytest.mark.anyio
async def test_bind_scoped_attachments_denies_scope_before_network_io():
    from app.schemas.response import BusinessError, ResponseCode

    validate = AsyncMock()
    denial = BusinessError(
        code=ResponseCode.PERMISSION_DENIED, msg_key="access_denied", status_code=403
    )
    with (
        patch(
            "app.services.asset_access.authorize_asset_scope",
            AsyncMock(side_effect=denial),
        ),
        patch("app.models.user.User.get_or_none", AsyncMock(return_value=object())),
        patch("app.core.network_security.ensure_external_http_url_allowed", validate),
        pytest.raises(BusinessError) as error,
    ):
        await AgentService()._bind_scoped_attachments(
            agent=_agent(team_id=uuid4(), enable_attachments=True),
            images=None,
            files=["https://example.test/file.txt"],
            user_id=str(uuid4()),
            workflow_run_id=uuid4(),
        )

    assert error.value.status_code == 403
    validate.assert_not_awaited()


@pytest.mark.anyio
async def test_bind_scoped_attachments_surfaces_shared_import_errors():
    from app.schemas.response import BusinessError

    for msg_key in ("file_download_failed", "file_too_large"):
        load = AsyncMock(side_effect=BusinessError(msg_key=msg_key))
        persist = AsyncMock()
        with (
            patch("app.services.asset_url_import.load_url_document", load),
            patch("app.services.asset_url_import.persist_scoped_document", persist),
            patch(
                "app.services.asset_access.authorize_asset_scope",
                AsyncMock(return_value=uuid4()),
            ),
            patch("app.models.user.User.get_or_none", AsyncMock(return_value=object())),
            pytest.raises(BusinessError) as error,
        ):
            await AgentService()._bind_scoped_attachments(
                agent=_agent(
                    team_id=uuid4(),
                    enable_attachments=True,
                    attachment_config={"max_file_size": 1024},
                ),
                images=None,
                files=["https://example.test/file.txt"],
                user_id=str(uuid4()),
                workflow_run_id=uuid4(),
            )
        assert error.value.msg_key == msg_key
        persist.assert_not_awaited()
        assert load.await_args.kwargs["max_bytes"] == 1024


@pytest.mark.anyio
async def test_execute_tool_loads_caller_for_conversation_asset_scope():
    user = SimpleNamespace(id=uuid4())
    execute = AsyncMock(return_value="asset result")
    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="read_asset", arguments={"ref": "abcd"}),
    )

    with (
        patch("app.api.v1.endpoints.chat_tools.execute_tool_call", new=execute),
        patch("app.models.user.User.get_or_none", AsyncMock(return_value=user)),
    ):
        result = await AgentService()._execute_tool(
            _agent(enable_attachments=True),
            tool_call,
            conversation_id="conversation-1",
            user_id=str(user.id),
        )

    assert result == "asset result"
    assert execute.await_args.kwargs["user"] is user
    assert execute.await_args.kwargs["conversation_id"] == "conversation-1"


@pytest.mark.anyio
async def test_execute_tool_routes_shared_asset_handler():
    service = AgentService()
    execute = AsyncMock(return_value="asset result")
    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="search_asset", arguments={"ref": "abcd"}),
    )

    with patch("app.api.v1.endpoints.chat_tools.execute_tool_call", new=execute):
        result = await service._execute_tool(
            _agent(enable_attachments=True),
            tool_call,
            conversation_id="conversation-1",
            workflow_run_id="run-1",
        )

    assert result == "asset result"
    execute.assert_awaited_once_with(
        "search_asset",
        {"ref": "abcd"},
        agent=ANY,
        conversation_id="conversation-1",
        workflow_run_id="run-1",
    )


@pytest.mark.anyio
async def test_agent_service_get_tools_skips_missing_and_failed_tools(monkeypatch):
    service = AgentService()
    monkeypatch.setattr(
        service,
        "_get_builtin_tool",
        lambda name: None if name in {"missing", "generate_image"} else _tool(name),
    )

    from app.services.skill import SkillService

    monkeypatch.setattr(
        SkillService,
        "get_skill_for_team",
        AsyncMock(side_effect=RuntimeError("unavailable")),
    )
    tools = await service._get_agent_tools(
        _agent(
            tools_config=[
                {"type": "builtin", "name": "missing"},
                {"type": "skill", "skill_id": "skill-id"},
                {"type": "skill"},
                {"type": "mcp"},
            ],
            enable_image_generation=True,
            enable_video_generation=True,
            rag_mode=RAGMode.AGENTIC,
        )
    )

    assert [tool.function.name for tool in tools] == [
        "generate_video",
        "search_knowledge_base",
    ]


@pytest.mark.anyio
async def test_agent_service_retrieve_rag_context_sorts_and_skips_empty_kb(
    monkeypatch,
):
    service = AgentService()
    knowledge_base = SimpleNamespace(
        id=uuid4(),
        name="Docs",
        embedding_model_id=None,
        rerank_model_id=None,
        team_id=uuid4(),
        status="active",
        settings=None,
    )
    links = [
        SimpleNamespace(knowledge_base=None),
        SimpleNamespace(
            knowledge_base=knowledge_base,
            search_mode="hybrid",
            retrieval_top_k=3,
            score_threshold=0.2,
        ),
    ]

    class Query:
        def prefetch_related(self, *_args):
            return self

        def __await__(self):
            async def resolve():
                return links

            return resolve().__await__()

    monkeypatch.setattr(
        "app.services.agent.AgentKnowledgeBase.filter", lambda **_kwargs: Query()
    )

    retrieve = AsyncMock(
        return_value=SimpleNamespace(
            results=(
                {"kb_name": "Docs", "content": "high", "score": 0.9},
                {"kb_name": "Docs", "content": "low", "score": 0.1},
            )
        )
    )
    monkeypatch.setattr("app.services.retrieval.retrieve", retrieve)

    result = await service._retrieve_rag_context(_agent(), "query")

    assert result == "[Docs] high\n\n[Docs] low"
    request = retrieve.await_args.args[0]
    assert request.query == "query"
    assert request.top_k == 10
    assert request.targets[0].kb_id == knowledge_base.id
    assert request.targets[0].score_threshold == 0.2


@pytest.mark.anyio
async def test_agent_service_retrieve_rag_context_handles_empty_and_failure(
    monkeypatch,
):
    service = AgentService()

    class Query:
        def prefetch_related(self, *_args):
            return self

        def __await__(self):
            async def resolve():
                return []

            return resolve().__await__()

    monkeypatch.setattr(
        "app.services.agent.AgentKnowledgeBase.filter", lambda **_kwargs: Query()
    )
    assert await service._retrieve_rag_context(_agent(), "query") is None

    monkeypatch.setattr(
        "app.services.agent.AgentKnowledgeBase.filter",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    assert await service._retrieve_rag_context(_agent(), "query") is None
