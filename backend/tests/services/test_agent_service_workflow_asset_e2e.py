"""End-to-end Workflow Agent attachment contract with real scoped Assets."""

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from tortoise.context import TortoiseContext

from app.llm.types import FunctionCall, ToolCall
from app.models.agent import RAGMode
from app.models.asset import (
    Asset,
    AssetScopeRef,
    AssetScopeType,
    AssetSource,
    AssetStatus,
)
from app.models.user import Team, User
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
