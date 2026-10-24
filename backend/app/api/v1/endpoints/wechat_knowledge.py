"""Personal WeChat connections and optional collection. No admin impersonation."""

from uuid import UUID, uuid4
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_active_user
from app.core.i18n import t
from app.services.audit_log import AuditLogService
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.models.wechat_knowledge import (
    WeChatKnowledgeBinding,
    WeChatKnowledgeCollection,
    WeChatKnowledgeReceipt,
)
from app.schemas.response import BusinessError, success
from app.services.wechat_connection import (
    available_models,
    binding_summary,
    check_binding_target,
    collection_error,
    poll_login,
    start_login,
    validate_models,
)
from app.services.integration_features import enabled_features, require_feature

router = APIRouter()


class PurposeInput(BaseModel):
    purpose: Literal["none", "knowledge_collection", "agent"]
    knowledge_base_id: UUID | None = None
    vision_model_id: UUID | None = None
    stt_model_id: UUID | None = None
    agent_id: UUID | None = None
    variables: dict = Field(default_factory=dict)


class PollInput(BaseModel):
    verify_code: str | None = Field(
        None, min_length=1, max_length=32, pattern=r"^[0-9]+$"
    )


async def owned_binding(identifier: UUID, user: User) -> WeChatKnowledgeBinding:
    binding = await WeChatKnowledgeBinding.filter(
        id=identifier, user_id=user.id
    ).first()
    if not binding:
        raise collection_error("wechat_binding_not_found", 404)
    return binding


@router.get("/features")
async def features(user: User = Depends(get_current_active_user)):
    enabled = await enabled_features("wechat")
    return success(
        data={
            "agent_chat": "agent_chat" in enabled,
            "knowledge_collection": "knowledge_collection" in enabled,
        }
    )


@router.get("/bindings")
async def bindings(user: User = Depends(get_current_active_user)):
    rows = await WeChatKnowledgeBinding.filter(user_id=user.id).order_by("-created_at")
    return success(data=[await binding_summary(row) for row in rows])


@router.get("/targets")
async def targets(user: User = Depends(get_current_active_user)):
    await require_feature("wechat", "knowledge_collection")
    from app.api.v1.endpoints.knowledge_bases import (
        _kb_access_mode,
        kb_read_visibility_filter,
    )

    # Candidate filtering is only an optimization; every result passes WRITE ACL.
    mode = _kb_access_mode.set("platform")
    try:
        candidates = KnowledgeBase.filter(status="active")
        candidates = candidates.filter(await kb_read_visibility_filter(user))
        output = []
        for kb in await candidates.prefetch_related("team").order_by("name"):
            try:
                await check_binding_target(kb.id, user)
            except BusinessError:
                continue
            output.append(
                {"id": str(kb.id), "name": kb.name, "team_name": kb.team.name}
            )
        return success(data=output)
    finally:
        _kb_access_mode.reset(mode)


@router.get("/models")
async def models(
    knowledge_base_id: UUID, user: User = Depends(get_current_active_user)
):
    await require_feature("wechat", "knowledge_collection")
    kb = await check_binding_target(knowledge_base_id, user)
    return success(data=await available_models(kb))


@router.post("/logins")
async def logins(user: User = Depends(get_current_active_user)):
    login = await start_login(user)
    return success(
        data={
            "id": str(login.id),
            "status": login.status,
            "qrcode_content": login.qrcode_content,
            "expires_at": login.expires_at,
        }
    )


@router.post("/logins/{identifier}/poll")
async def poll(
    identifier: UUID, data: PollInput, user: User = Depends(get_current_active_user)
):
    return success(data=await poll_login(identifier, user, data.verify_code))


@router.get("/agents")
async def agents(user: User = Depends(get_current_active_user)):
    await require_feature("wechat", "agent_chat")
    from app.services.wechat_purpose import available_agents

    output = []
    for agent in await available_agents(user):
        output.append(
            {
                "id": str(agent.id),
                "name": agent.name,
                "team_name": agent.team.name,
                "variables": agent.variables,
                "enable_attachments": agent.enable_attachments,
                "attachment_config": agent.attachment_config,
            }
        )
    return success(data=output)


@router.get("/agent-models")
async def agent_models(agent_id: UUID, user: User = Depends(get_current_active_user)):
    await require_feature("wechat", "agent_chat")
    from app.services.wechat_purpose import authorized_agent

    agent = await authorized_agent(agent_id, user)
    return success(data={"stt": (await available_models(agent))["stt"]})


@router.put("/bindings/{identifier}/purpose")
async def update_purpose(
    identifier: UUID, data: PurposeInput, user: User = Depends(get_current_active_user)
):
    from tortoise.transactions import in_transaction
    from app.models.wechat_agent import WeChatAgentConfig, WeChatAgentSession
    from app.services.wechat_purpose import (
        authorized_agent,
        check_switch_idle,
        resolve_variables,
    )

    binding = await owned_binding(identifier, user)
    if data.purpose != "none":
        await require_feature(
            "wechat",
            "agent_chat" if data.purpose == "agent" else "knowledge_collection",
        )
    if data.purpose == "agent" and (data.knowledge_base_id or data.vision_model_id):
        raise collection_error("validation_error")
    if data.purpose == "knowledge_collection" and (data.agent_id or data.variables):
        raise collection_error("validation_error")
    config_values = None
    if data.purpose == "knowledge_collection":
        saved = await WeChatKnowledgeCollection.filter(binding_id=binding.id).first()
        kb = await check_binding_target(
            data.knowledge_base_id or (saved.knowledge_base_id if saved else None), user
        )
        vision = (
            data.vision_model_id
            if "vision_model_id" in data.model_fields_set
            else (saved.vision_model_id if saved else None)
        )
        stt = (
            data.stt_model_id
            if "stt_model_id" in data.model_fields_set
            else (saved.stt_model_id if saved else None)
        )
        await validate_models(kb, vision, stt)
        config_values = {
            "knowledge_base_id": kb.id,
            "vision_model_id": vision,
            "stt_model_id": stt,
        }
    elif data.purpose == "agent":
        saved = await WeChatAgentConfig.filter(binding_id=binding.id).first()
        agent = await authorized_agent(
            data.agent_id or (saved.agent_id if saved else None), user
        )
        values = (
            data.variables
            if "variables" in data.model_fields_set
            else (saved.variables if saved and saved.agent_id == agent.id else {})
        )
        stt = (
            data.stt_model_id
            if "stt_model_id" in data.model_fields_set
            else (saved.stt_model_id if saved and saved.agent_id == agent.id else None)
        )
        variables = resolve_variables(agent, values)
        await validate_models(agent, None, stt)
        config_values = {
            "agent_id": agent.id,
            "variables": variables,
            "stt_model_id": stt,
        }
    async with in_transaction() as db:
        binding = (
            await WeChatKnowledgeBinding.filter(id=binding.id)
            .using_db(db)
            .select_for_update()
            .get()
        )
        await check_switch_idle(binding.id)
        if data.purpose != "none":
            await require_feature(
                "wechat",
                "agent_chat" if data.purpose == "agent" else "knowledge_collection",
            )
        if data.purpose == "knowledge_collection":
            await WeChatKnowledgeCollection.update_or_create(
                binding_id=binding.id, defaults=config_values, using_db=db
            )
        elif data.purpose == "agent":
            old = (
                await WeChatAgentConfig.filter(binding_id=binding.id)
                .using_db(db)
                .first()
            )
            if (
                old
                and old.agent_id == config_values["agent_id"]
                and old.variables != config_values["variables"]
            ):
                await (
                    WeChatAgentSession.filter(
                        binding_id=binding.id, agent_id=old.agent_id
                    )
                    .using_db(db)
                    .update(
                        conversation_id=None,
                        pending_answers={},
                        pending_tool_call_id=None,
                    )
                )
            await WeChatAgentConfig.update_or_create(
                binding_id=binding.id, defaults=config_values, using_db=db
            )
        binding.purpose = data.purpose
        binding.generation = uuid4()
        await binding.save(
            using_db=db, update_fields=["purpose", "generation", "updated_at"]
        )
    await AuditLogService.log(
        user=user,
        action="update_wechat_binding",
        resource_type="wechat_binding",
        resource_id=binding.id,
        resource_name=None,
        operation="update",
        status="success",
        metadata={"purpose": data.purpose},
    )
    return success(data=await binding_summary(binding))


@router.get("/agent-receipts")
async def agent_receipts(
    binding_id: UUID | None = None, user: User = Depends(get_current_active_user)
):
    from app.models.wechat_agent import WeChatAgentReceipt, WeChatAgentSession

    query = WeChatAgentReceipt.filter(user_id=user.id)
    if binding_id:
        await owned_binding(binding_id, user)
        query = query.filter(binding_id=binding_id)
    rows = (
        await query.prefetch_related("agent", "run", "deliveries")
        .order_by("-created_at")
        .limit(50)
    )
    output = []
    for row in rows:
        session = await WeChatAgentSession.filter(
            binding_id=row.binding_id, agent_id=row.agent_id
        ).first()
        output.append(
            {
                "id": str(row.id),
                "binding_id": str(row.binding_id),
                "status": row.status,
                "agent_name": row.agent.name if row.agent else None,
                "agent_id": str(row.agent_id) if row.agent_id else None,
                "conversation_id": str(row.run.conversation_id)
                if row.run
                else (
                    str(session.conversation_id)
                    if session and session.conversation_id
                    else None
                ),
                "run_id": str(row.run_id) if row.run_id else None,
                "run_status": row.run.status if row.run else None,
                "error": t(row.error) if row.error else None,
                "delivery_status": [delivery.status for delivery in row.deliveries],
                "created_at": row.created_at,
            }
        )
    return success(data=output)


@router.delete("/bindings/{identifier}")
async def disconnect(identifier: UUID, user: User = Depends(get_current_active_user)):
    binding = await owned_binding(identifier, user)
    binding.status = "disconnected"
    binding.token = ""
    binding.cursor = ""
    binding.generation = uuid4()
    from app.services.wechat_connection import utcnow

    binding.disconnected_at = utcnow()
    await binding.save(
        update_fields=[
            "status",
            "token",
            "cursor",
            "generation",
            "disconnected_at",
            "updated_at",
        ]
    )
    await AuditLogService.log(
        user=user,
        action="disconnect_wechat_binding",
        resource_type="wechat_binding",
        resource_id=binding.id,
        resource_name=None,
        operation="delete",
        status="success",
    )
    return success(data={"id": str(binding.id)})


@router.get("/receipts")
async def receipts(
    binding_id: UUID | None = None, user: User = Depends(get_current_active_user)
):
    query = WeChatKnowledgeReceipt.filter(user_id=user.id)
    if binding_id:
        await owned_binding(binding_id, user)
        query = query.filter(binding_id=binding_id)
    rows = await query.order_by("-created_at").limit(50)
    return success(
        data=[
            {
                "id": str(row.id),
                "binding_id": str(row.binding_id),
                "knowledge_base_id": str(row.knowledge_base_id)
                if row.knowledge_base_id
                else None,
                "status": row.status,
                "results": [
                    {**item, "error": t(item["error"]) if item.get("error") else None}
                    for item in row.results
                ],
                "last_error": t(row.last_error) if row.last_error else None,
                "reply_status": row.reply_status,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    )


@router.get("/items/{identifier}/original")
async def original(identifier: UUID, user: User = Depends(get_current_active_user)):
    from app.models.wechat_knowledge import WeChatKnowledgeItem
    from app.services.document_processor import document_processor
    from app.services.upload_storage import get_upload_storage_backend

    item = (
        await WeChatKnowledgeItem.filter(id=identifier, receipt__user_id=user.id)
        .prefetch_related("receipt")
        .first()
    )
    if not item or not item.original_path:
        raise collection_error("file_not_found", 404)
    # Even a former contributor must still have access to the target.
    from app.api.v1.endpoints.knowledge_bases import _kb_access_mode, check_kb_access

    mode = _kb_access_mode.set("platform")
    try:
        await check_kb_access(item.receipt.knowledge_base_id, user)
    finally:
        _kb_access_mode.reset(mode)
    expected = f"documents/{item.receipt.knowledge_base_id}/wechat/{item.id}/original/"
    if not item.original_path.startswith(expected):
        raise collection_error("file_not_found", 404)
    storage = await get_upload_storage_backend(document_processor._storage_root())
    if not await storage.exists(item.original_path):
        raise collection_error("file_not_found", 404)
    return await storage.response(
        item.original_path,
        content_type="application/octet-stream",
        filename=item.name or "original",
    )
