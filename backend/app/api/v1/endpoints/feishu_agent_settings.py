"""Owner-scoped Feishu Agent preferences; no administrator impersonation."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.api.deps import get_current_active_user
from app.models.integration import Integration
from app.models.feishu_agent import FeishuAgentPreference
from app.models.user import User
from app.schemas.response import success
from app.services.audit_log import AuditLogService
from app.services.feishu_agent_locks import chat_lock
from app.services.feishu_agent_preferences import (
    available_agents,
    channel_available,
    linked_user,
    preference_summary,
    set_preference,
)
from app.services.feishu_agent_runtime import _authorized_agent, channel_error

router = APIRouter()


class PreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: UUID | None = None
    is_enabled: bool | None = None


@router.get("/config")
async def get_config(user: User = Depends(get_current_active_user)):
    integration = await Integration.get_or_none(provider_type="feishu")
    return success(data=await preference_summary(integration, user))


@router.get("/agents")
async def list_agents(user: User = Depends(get_current_active_user)):
    integration = await Integration.get_or_none(provider_type="feishu")
    if not channel_available(integration) or not await linked_user(integration, user):
        return success(data=[])
    return success(
        data=[
            {
                "id": str(agent.id),
                "name": agent.name,
                "description": agent.description or "",
                "team_name": agent.team.name,
            }
            for agent in await available_agents(user)
        ]
    )


@router.put("/config")
async def update_config(
    data: PreferenceInput,
    request: Request,
    user: User = Depends(get_current_active_user),
):
    integration = await Integration.get_or_none(provider_type="feishu")
    if integration is None:
        raise channel_error("feishu_agent_channel_disabled", 403)
    async with chat_lock(integration.id, "", user.id):
        preference, _ = await FeishuAgentPreference.get_or_create(
            integration_id=integration.id, user_id=user.id
        )
        selected_id = (
            data.agent_id
            if "agent_id" in data.model_fields_set
            else preference.agent_id
        )
        if (
            "agent_id" in data.model_fields_set and selected_id is not None
        ) or data.is_enabled is True:
            if not channel_available(integration) or not await linked_user(
                integration, user
            ):
                raise channel_error("feishu_agent_channel_disabled", 403)
            if selected_id is None:
                raise channel_error("feishu_agent_agent_unavailable", 400)
            await _authorized_agent(selected_id, user)
        if "agent_id" in data.model_fields_set:
            await set_preference(integration, user, selected_id)
        if data.is_enabled is not None:
            await FeishuAgentPreference.filter(id=preference.id).update(
                is_enabled=data.is_enabled
            )
    await AuditLogService.log(
        user=user,
        action="update_feishu_agent_preference",
        resource_type="integration",
        resource_id=integration.id,
        resource_name="feishu_agent_preference",
        operation="update",
        status="success",
        request=request,
        changes={"after": data.model_dump(mode="json", exclude_unset=True)},
    )
    return success(data=await preference_summary(integration, user))
