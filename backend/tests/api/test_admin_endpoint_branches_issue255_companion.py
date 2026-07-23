from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.api.v1.admin.endpoints import (
    agents,
    conversations,
    site_settings,
    tools,
    users,
)
from app.models.agent import AgentStatus, AgentVisibility
from app.models.tool import CustomToolType
from app.schemas.response import BusinessError, ResponseCode
from app.schemas.tool import ToolExecuteRequest


class Query:
    def __init__(self, result=None):
        self.result = result

    def __getattr__(self, _name):
        return lambda *args, **kwargs: self

    def __await__(self):
        async def resolve():
            return self.result

        return resolve().__await__()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("icp_record_url", 1),
        ("icp_record_url", "ftp://invalid"),
        ("auth_page_layout", "wide"),
        ("theme_mode", "blue"),
        ("theme_branding_display", "logo"),
        ("theme_primary_color", 1),
        ("theme_primary_color", " #fff"),
        ("theme_primary_color", "#12"),
        ("theme_primary_color", "#zzzzzz"),
        ("default_team_role", "owner"),
        ("default_team_id", 1),
        ("default_team_id", "invalid"),
        ("upload_storage_backend", "ftp"),
        ("object_storage_endpoint", 1),
        ("object_storage_secure", "yes"),
        ("kb_document_max_upload_size_mb", True),
        ("kb_document_max_upload_size_mb", 0),
    ],
)
@pytest.mark.asyncio
async def test_setting_validation_rejects_remaining_invalid_values(key, value):
    with pytest.raises(BusinessError) as exc:
        await site_settings._validate_setting_value(key, value)
    assert exc.value.code == ResponseCode.VALIDATION_ERROR


@pytest.mark.asyncio
async def test_setting_validation_accepts_empty_urls_and_ignores_other_keys():
    await site_settings._validate_setting_value("privacy_url", "")
    await site_settings._validate_setting_value("unrelated", object())


@pytest.mark.asyncio
async def test_storage_validation_requires_object_credentials(monkeypatch):
    monkeypatch.setattr(
        site_settings.SiteSetting,
        "get_all_by_category",
        AsyncMock(return_value={"upload_storage_backend": "s3"}),
    )
    with pytest.raises(BusinessError) as exc:
        await site_settings._validate_storage_settings_update(
            {"object_storage_bucket": "bucket"}
        )
    assert exc.value.code == ResponseCode.VALIDATION_ERROR
    await site_settings._validate_storage_settings_update({"site_name": "test"})


@pytest.mark.asyncio
async def test_conversation_team_access_branches(monkeypatch):
    team = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(conversations.Team, "filter", Mock(return_value=Query(None)))
    with pytest.raises(BusinessError) as exc:
        await conversations.check_team_access(
            team.id, SimpleNamespace(is_superuser=True)
        )
    assert exc.value.code == ResponseCode.TEAM_NOT_FOUND

    monkeypatch.setattr(conversations.Team, "filter", Mock(return_value=Query(team)))
    assert (
        await conversations.check_team_access(
            team.id, SimpleNamespace(is_superuser=True)
        )
        is team
    )

    monkeypatch.setattr(
        conversations.TeamMember, "filter", Mock(return_value=Query(None))
    )
    with pytest.raises(BusinessError) as exc:
        await conversations.check_team_access(
            team.id, SimpleNamespace(is_superuser=False)
        )
    assert exc.value.code == ResponseCode.NOT_TEAM_MEMBER


@pytest.mark.asyncio
async def test_conversation_agent_ids_cover_superuser_and_member_queries(monkeypatch):
    ids = [uuid4(), uuid4()]
    monkeypatch.setattr(
        conversations.Agent, "all", Mock(return_value=Query([(ids[0],), ids[1]]))
    )
    assert (
        await conversations.get_user_team_agent_ids(SimpleNamespace(is_superuser=True))
        == ids
    )

    membership_ids = [uuid4()]
    monkeypatch.setattr(
        conversations.TeamMember,
        "filter",
        Mock(return_value=Query([(membership_ids[0],)])),
    )
    monkeypatch.setattr(conversations.Agent, "filter", Mock(return_value=Query(ids)))
    assert (
        await conversations.get_user_team_agent_ids(SimpleNamespace(is_superuser=False))
        == ids
    )


@pytest.mark.asyncio
async def test_conversation_empty_list_and_inaccessible_agent(monkeypatch):
    user = SimpleNamespace(is_superuser=True, roles=[], id=uuid4())
    monkeypatch.setattr(
        conversations, "get_user_team_agent_ids", AsyncMock(return_value=[])
    )
    result = await conversations.list_all_conversations(
        team_id=None,
        agent_id=None,
        user_id=None,
        search=None,
        untitled_only=False,
        page=1,
        page_size=20,
        current_user=user,
    )
    assert result["data"]["total"] == 0

    accessible = uuid4()
    monkeypatch.setattr(
        conversations, "get_user_team_agent_ids", AsyncMock(return_value=[accessible])
    )
    monkeypatch.setattr(
        conversations.Conversation, "filter", Mock(return_value=Query(None))
    )
    result = await conversations.list_all_conversations(
        team_id=None,
        agent_id=[uuid4()],
        user_id=None,
        search=None,
        untitled_only=False,
        page=1,
        page_size=20,
        current_user=user,
    )
    assert result["data"]["total"] == 0


@pytest.mark.asyncio
async def test_agent_helpers_cover_empty_missing_and_model_map(monkeypatch):
    assert agents._option("x") == {"value": "x", "label": "x"}
    assert await agents._get_model_info_map([SimpleNamespace(model_id=None)]) == {}

    monkeypatch.setattr(agents.Agent, "filter", Mock(return_value=Query(None)))
    with pytest.raises(BusinessError) as exc:
        await agents._get_agent(uuid4(), detail=True)
    assert exc.value.code == ResponseCode.AGENT_NOT_FOUND

    model_id = uuid4()
    team_model = SimpleNamespace(
        id=model_id,
        model=SimpleNamespace(name="Model", provider="openai", model_id="m"),
    )
    monkeypatch.setattr(
        agents.TeamModel, "filter", Mock(return_value=Query([team_model]))
    )
    result = await agents._get_model_info_map([SimpleNamespace(model_id=model_id)])
    assert result[str(model_id)].name == "Model"


@pytest.mark.asyncio
async def test_agent_publish_skips_team_notification(monkeypatch):
    agent = SimpleNamespace(
        id=uuid4(),
        name="Agent",
        status=AgentStatus.DRAFT,
        team_id=None,
        visibility=AgentVisibility.PRIVATE,
        save=AsyncMock(),
    )
    monkeypatch.setattr(agents, "_get_agent", AsyncMock(return_value=agent))
    monkeypatch.setattr(agents.AuditLogService, "log", AsyncMock())
    notify = AsyncMock()
    monkeypatch.setattr(agents.AutoNotificationService, "send_to_team", notify)
    monkeypatch.setattr(agents, "build_agent_out", AsyncMock(return_value={}))

    await agents.publish_agent(Mock(), agent.id, SimpleNamespace())
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_lookup_helpers_and_mcp_failure(monkeypatch):
    monkeypatch.setattr(tools.Tool, "filter", Mock(return_value=Query(None)))
    with pytest.raises(BusinessError) as exc:
        await tools._get_db_tool(uuid4(), detail=True)
    assert exc.value.code == ResponseCode.NOT_FOUND

    monkeypatch.setattr(tools.Team, "filter", Mock(return_value=Query(None)))
    with pytest.raises(BusinessError) as exc:
        await tools._get_team(uuid4())
    assert exc.value.code == ResponseCode.TEAM_NOT_FOUND

    monkeypatch.setattr(
        tools, "list_mcp_tools", AsyncMock(side_effect=RuntimeError("down"))
    )
    with pytest.raises(BusinessError) as exc:
        await tools.get_mcp_tools(
            SimpleNamespace(mcp_config=Mock(model_dump=Mock(return_value={})))
        )
    assert exc.value.code == ResponseCode.INTERNAL_ERROR


@pytest.mark.asyncio
async def test_tool_execution_missing_code_and_unsupported_type(monkeypatch):
    request = ToolExecuteRequest(name="custom", arguments={})
    monkeypatch.setattr(tools.tool_registry, "get_tool", Mock(return_value=None))

    custom = SimpleNamespace(
        type=SimpleNamespace(value="custom"),
        custom_type=CustomToolType.CODE,
        code_config={},
    )
    monkeypatch.setattr(tools.Tool, "filter", Mock(return_value=Query(custom)))
    result = await tools.test_tool(request)
    assert result["data"].success is False

    custom.custom_type = None
    result = await tools.test_tool(ToolExecuteRequest(name="custom", arguments={}))
    assert result["data"].success is False


@pytest.mark.parametrize(
    ("active", "approval", "expected"),
    [
        (False, "pending", "pending"),
        (True, "pending", "active"),
        (False, "approved", "inactive"),
    ],
)
def test_user_status_branches(active, approval, expected):
    assert (
        users.get_user_status(
            SimpleNamespace(is_active=active, approval_status=approval)
        )
        == expected
    )


@pytest.mark.asyncio
async def test_user_email_remaining_branches(monkeypatch):
    monkeypatch.setattr(users.SiteSetting, "get_value", AsyncMock(return_value=True))
    monkeypatch.setattr(
        users, "check_bulk_email_rate", AsyncMock(return_value=(True, 0, 3))
    )
    monkeypatch.setattr(
        users.User,
        "filter",
        Mock(return_value=Query([SimpleNamespace(email=None, username="none")])),
    )
    increment = AsyncMock()
    monkeypatch.setattr(users, "increment_bulk_email_count", increment)
    result = await users.send_email_to_users(
        data=users.SendEmailRequest(subject="s", content="c", user_ids=[uuid4()]),
        background_tasks=Mock(),
        current_user=SimpleNamespace(id=uuid4()),
    )
    assert result["data"]["sent_count"] == 0
    increment.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_password_expiration_disabled(monkeypatch):
    monkeypatch.setattr(users.SiteSetting, "get_value", AsyncMock(return_value=False))
    result = await users.get_password_expiration_stats()
    assert result["data"].total_users == 0
