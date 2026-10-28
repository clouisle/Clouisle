"""End-to-end Workflow Agent attachment contract with real scoped Assets."""

import base64
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.llm.types import (
    ContentType,
    FunctionCall,
    Message as LLMMessage,
    MessageRole,
    ToolCall,
)
from app.models.agent import RAGMode
from app.models.model import Model, ModelProvider, ModelType, TeamModel
from app.models.asset import (
    Asset,
    AssetScopeRef,
    AssetScopeType,
    AssetSource,
    AssetStatus,
)
from app.models.user import Permission, Role, Team, TeamMember, User
from app.models.workflow import TriggerType, Workflow, WorkflowRun
from app.services.agent import AgentService
from app.services.upload_storage import LocalUploadStorage


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


@pytest_asyncio.fixture
async def workflow_asset(database, tmp_path, monkeypatch):
    owner = await User.create(
        id=uuid4(),
        username="owner",
        email="owner@example.test",
        hashed_password="unused",
        is_active=True,
        approval_status="approved",
    )
    other = await User.create(
        id=uuid4(),
        username="other",
        email="other@example.test",
        hashed_password="unused",
        is_active=True,
        approval_status="approved",
    )
    team = await Team.create(id=uuid4(), name="Workflow team")
    permission = await Permission.create(id=uuid4(), scope="team", code="team:read")
    role = await Role.create(id=uuid4(), name=f"Workflow user {uuid4().hex[:8]}")
    await role.permissions.add(permission)
    await owner.roles.add(role)
    await TeamMember.create(team=team, user=owner, role="owner")
    workflow = await Workflow.create(
        id=uuid4(), team=team, name="Reader", created_by=owner
    )
    run = await WorkflowRun.create(
        id=uuid4(),
        workflow=workflow,
        trigger_type=TriggerType.MANUAL,
        triggered_by=owner,
    )
    content = b"alpha\nbeta\n"
    key = "agent-attachments/2026/10/report.txt"
    storage = LocalUploadStorage(tmp_path)
    await storage.save(key, content, "text/plain")
    asset = await Asset.create(
        id=uuid4(),
        team_id=None,
        created_by=owner,
        storage_key=key,
        original_filename="report.txt",
        display_filename="report.txt",
        content_type="text/plain",
        size=len(content),
        checksum=hashlib.sha256(content).hexdigest(),
        source=AssetSource.UPLOAD,
        status=AssetStatus.AVAILABLE,
    )
    await AssetScopeRef.create(
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=run.id,
        asset=asset,
        ref="a1b2",
    )
    image_content = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    image_key = "agent-attachments/2026/10/photo.png"
    await storage.save(image_key, image_content, "image/png")
    image_asset = await Asset.create(
        id=uuid4(),
        team_id=None,
        created_by=owner,
        storage_key=image_key,
        original_filename="photo.png",
        display_filename="photo.png",
        content_type="image/png",
        size=len(image_content),
        checksum=hashlib.sha256(image_content).hexdigest(),
        source=AssetSource.UPLOAD,
        status=AssetStatus.AVAILABLE,
    )
    await AssetScopeRef.create(
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=run.id,
        asset=image_asset,
        ref="1a01",
    )
    monkeypatch.setattr(
        "app.services.upload_storage.get_upload_storage_backend",
        AsyncMock(return_value=storage),
    )
    return SimpleNamespace(
        owner=owner,
        other=other,
        team=team,
        workflow=workflow,
        run=run,
        asset=asset,
        image_asset=image_asset,
        image_content=image_content,
        storage=storage,
    )


def _agent(team_id):
    return SimpleNamespace(
        id=uuid4(),
        team_id=team_id,
        model_id=None,
        system_prompt="",
        tools_config=[],
        enable_attachments=True,
        attachment_config={},
        enable_image_generation=False,
        enable_video_generation=False,
        rag_mode=RAGMode.OFF,
    )


@pytest.mark.anyio
async def test_chat_streams_document_ref_and_reads_it_through_real_tool(
    workflow_asset, monkeypatch
):
    tool_call = ToolCall(
        id="call-1",
        function=FunctionCall(name="read_asset", arguments=json.dumps({"ref": "a1b2"})),
    )
    model_calls: list[list] = []

    async def model_chat(**kwargs):
        model_calls.append(
            [message.model_copy(deep=True) for message in kwargs["messages"]]
        )
        if len(model_calls) == 1:
            return SimpleNamespace(content="", tool_calls=[tool_call], usage=None)
        return SimpleNamespace(content="summary done", tool_calls=[], usage=None)

    monkeypatch.setattr("app.services.agent.build_system_prompt", lambda *_a, **_k: "")
    monkeypatch.setattr("app.services.agent.model_manager.team_chat", model_chat)
    monkeypatch.setattr("app.services.agent.model_manager.chat", model_chat)

    from app.services.tool_context import RuntimeToolIdentity, tool_identity_scope

    with tool_identity_scope(
        RuntimeToolIdentity(
            run_id=workflow_asset.run.id,
            run_kind="workflow",
            entrypoint="workflow",
            entrypoint_id=str(workflow_asset.workflow.id),
            interactive=True,
            tool_call_prefix=(f"workflow-agent:{workflow_asset.run.id}:node-1"),
        )
    ):
        result = await AgentService().chat(
            _agent(workflow_asset.team.id),
            "summarize the report",
            user_id=str(workflow_asset.owner.id),
            workflow_run_id=str(workflow_asset.run.id),
            files=["/api/v1/upload/files/agent-attachments/2026/10/report.txt"],
        )

    assert result["response"] == "summary done"

    first_user_content = model_calls[0][-1].content
    documents = json.loads(first_user_content[-1].text)["documents"]
    assert documents[0]["ref"] == "a1b2"
    assert documents[0]["filename"] == "report.txt"
    assert "alpha" not in first_user_content[-1].text

    tool_message = next(
        message for message in model_calls[1] if message.role.value == "tool"
    )
    assert "alpha" in tool_message.content and "beta" in tool_message.content
    assert "a1b2" in tool_message.content
    displayed = json.loads(
        next(step["content"] for step in result["dialogue"] if step["role"] == "tool")
    )
    assert displayed["ref"] == "a1b2"
    assert [segment["text"] for segment in displayed["segments"]][:2] == [
        "alpha",
        "beta",
    ]
    assert displayed["eof"] is True
    assert displayed["citation_id"] in tool_message.content
    assert "asset_id" not in displayed

    derived = await Asset.filter(parent_id=workflow_asset.asset.id).first()
    assert derived is not None
    assert derived.source == AssetSource.DERIVED_TEXT


@pytest.mark.anyio
async def test_workflow_image_is_materialized_for_chat_and_stream_converters(
    workflow_asset, monkeypatch
):
    model = await Model.create(
        id=uuid4(),
        name="Vision",
        provider=ModelProvider.OPENAI.value,
        model_id="test-vision",
        model_type=ModelType.CHAT.value,
        capabilities={"input_modalities": ["text", "image"]},
        is_enabled=True,
        is_default=True,
    )
    await TeamModel.create(
        id=uuid4(), team_id=workflow_asset.team.id, model_id=model.id, is_enabled=True
    )
    monkeypatch.setattr("app.services.agent.build_system_prompt", lambda *_a, **_k: "")
    monkeypatch.setattr(
        "app.services.agent.AgentService._get_agent_tools", AsyncMock(return_value=[])
    )
    service = AgentService()
    agent = _agent(workflow_asset.team.id)
    captured = []

    async def model_chat(**kwargs):
        captured.extend(kwargs["messages"])
        return SimpleNamespace(content="ok", tool_calls=[], usage=None)

    monkeypatch.setattr("app.services.agent.model_manager.team_chat", model_chat)
    await service.chat(
        agent,
        "describe",
        user_id=str(workflow_asset.owner.id),
        workflow_run_id=str(workflow_asset.run.id),
        images=[{"asset_ref": "1a01"}],
    )
    user_message = next(m for m in captured if m.role == MessageRole.USER)
    image_part = next(p for p in user_message.content if p.type == ContentType.IMAGE)
    assert image_part.image.base64
    assert image_part.image.asset_ref is None
    assert image_part.image.url is None
    from app.llm.adapters.chat.openai_adapter import OpenAIAdapter

    converted = OpenAIAdapter(model)._convert_messages([user_message])
    assert converted[-1]["content"][-1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )
    from app.llm.adapters.chat.gemini_adapter import GeminiAdapter

    _system_instruction, gemini_contents = GeminiAdapter(model)._convert_messages(
        [user_message]
    )
    assert gemini_contents[-1]["parts"][-1]["inline_data"]["mime_type"] == "image/png"
    assert (
        gemini_contents[-1]["parts"][-1]["inline_data"]["data"]
        == image_part.image.base64
    )
    assert (
        workflow_asset.image_asset.checksum
        == hashlib.sha256(workflow_asset.image_content).hexdigest()
    )

    async def model_stream(**kwargs):
        captured.extend(kwargs["messages"])
        yield SimpleNamespace(delta=SimpleNamespace(content="ok"), usage=None)

    monkeypatch.setattr(
        "app.services.agent.model_manager.team_chat_stream", model_stream
    )
    async for _ in service.chat_stream(
        agent,
        "describe",
        user_id=str(workflow_asset.owner.id),
        workflow_run_id=str(workflow_asset.run.id),
        images=[{"asset_ref": "1a01"}],
    ):
        pass
    streamed_user = [m for m in captured if m.role == MessageRole.USER][-1]
    streamed_image = next(
        p.image for p in streamed_user.content if p.type == ContentType.IMAGE
    )
    assert streamed_image.base64
    for prepared_user in (user_message, streamed_user):
        openai_content = OpenAIAdapter(model)._convert_messages([prepared_user])
        data_uri = openai_content[-1]["content"][-1]["image_url"]["url"]
        assert data_uri.startswith("data:image/png;base64,")
        assert (
            base64.b64decode(data_uri.split(",", 1)[1]) == workflow_asset.image_content
        )
        _, gemini_content = GeminiAdapter(model)._convert_messages([prepared_user])
        inline_data = gemini_content[-1]["parts"][-1]["inline_data"]
        assert inline_data["mime_type"] == "image/png"
        assert base64.b64decode(inline_data["data"]) == workflow_asset.image_content
    binding = await AssetScopeRef.get(
        scope_type=AssetScopeType.WORKFLOW_RUN,
        scope_id=workflow_asset.run.id,
        ref="1a01",
    )
    assert binding.asset_id == workflow_asset.image_asset.id


@pytest.mark.anyio
async def test_workflow_image_rejects_unauthorized_scope_and_text_only_model(
    workflow_asset, monkeypatch
):
    from app.llm.errors import InvalidRequestError
    from app.schemas.response import BusinessError

    model = await Model.create(
        id=uuid4(),
        name="Text only",
        provider=ModelProvider.OPENAI.value,
        model_id="test-text",
        model_type=ModelType.CHAT.value,
        capabilities={"input_modalities": ["text"]},
        is_enabled=True,
        is_default=True,
    )
    await TeamModel.create(
        id=uuid4(), team_id=workflow_asset.team.id, model_id=model.id, is_enabled=True
    )
    monkeypatch.setattr("app.services.agent.build_system_prompt", lambda *_a, **_k: "")
    agent = _agent(workflow_asset.team.id)
    with pytest.raises(BusinessError) as denied:
        await AgentService().chat(
            agent,
            "describe",
            user_id=str(workflow_asset.other.id),
            workflow_run_id=str(workflow_asset.run.id),
            images=[{"asset_ref": "1a01"}],
        )
    assert denied.value.status_code == 403
    with pytest.raises(InvalidRequestError, match="does not support image input"):
        await AgentService().chat(
            agent,
            "describe",
            user_id=str(workflow_asset.owner.id),
            workflow_run_id=str(workflow_asset.run.id),
            images=[{"asset_ref": "1a01"}],
        )


@pytest.mark.anyio
async def test_workflow_image_openai_converter_rejects_unresolved_ref():
    from app.llm.adapters.chat.openai_adapter import OpenAIAdapter
    from app.llm.errors import InvalidRequestError

    adapter = OpenAIAdapter(SimpleNamespace(model_id="test"))
    message = LLMMessage(
        role=MessageRole.USER,
        content=[
            {
                "type": "image",
                "image": {
                    "asset_ref": "private-ref",
                    "url": "https://example.test/image.png",
                },
            }
        ],
    )
    with pytest.raises(InvalidRequestError):
        adapter._convert_messages([message])


@pytest.mark.anyio
async def test_chat_denies_external_import_for_unauthorized_run_caller(
    workflow_asset, monkeypatch
):
    from app.schemas.response import BusinessError

    validate = AsyncMock()
    monkeypatch.setattr("app.services.agent.build_system_prompt", lambda *_a, **_k: "")
    with (
        patch("app.core.network_security.ensure_external_http_url_allowed", validate),
        pytest.raises(BusinessError) as error,
    ):
        await AgentService().chat(
            _agent(workflow_asset.team.id),
            "read it",
            user_id=str(workflow_asset.other.id),
            workflow_run_id=str(workflow_asset.run.id),
            files=["https://example.test/report.txt"],
        )

    assert error.value.status_code == 403
    validate.assert_not_awaited()
