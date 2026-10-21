"""Current-user WeChat authorization and optional collection summaries."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core.i18n import t
from app.integrations.credentials import decrypt_secret, encrypt_secret
from app.integrations.wechat import WeChatAPIError, WeChatClient, official_url
from app.models.model import ModelType, TeamModel
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.models.wechat_knowledge import (
    WeChatKnowledgeBinding,
    WeChatKnowledgeCollection,
    WeChatKnowledgeLogin,
)
from app.schemas.response import BusinessError, ResponseCode
from app.services.integration_features import require_any_feature


def utcnow():
    return datetime.now(timezone.utc)


def collection_error(key: str, status: int = 400) -> BusinessError:
    return BusinessError(
        code=ResponseCode.VALIDATION_ERROR, msg_key=key, status_code=status
    )


async def check_binding_target(kb_id: UUID | None, user: User) -> KnowledgeBase:
    from app.api.v1.endpoints.knowledge_bases import _kb_access_mode, check_kb_access

    if not user.is_active or getattr(user, "approval_status", "approved") != "approved":
        raise collection_error("inactive_user", 403)
    if not kb_id:
        raise collection_error("kb_not_found", 404)
    mode = _kb_access_mode.set("platform")
    try:
        kb = await check_kb_access(kb_id, user, require_write=True)
    finally:
        _kb_access_mode.reset(mode)
    if kb.status != "active" or (getattr(kb, "team", None) and kb.team.is_deleted):
        raise collection_error("wechat_kb_inactive")
    return kb


async def available_models(kb: KnowledgeBase) -> dict:
    granted = await TeamModel.filter(
        team_id=kb.team_id, is_enabled=True, model__is_enabled=True
    ).prefetch_related("model")
    result = {"vision": [], "stt": []}
    for grant in granted:
        model = grant.model
        if model.model_type == ModelType.STT:
            result["stt"].append({"id": str(model.id), "name": model.name})
        elif model.model_type == ModelType.CHAT and (model.capabilities or {}).get(
            "vision"
        ):
            result["vision"].append({"id": str(model.id), "name": model.name})
    return result


async def validate_models(
    kb: KnowledgeBase, vision_id: UUID | None, stt_id: UUID | None
):
    choices = await available_models(kb)
    for kind, identifier in (("vision", vision_id), ("stt", stt_id)):
        if identifier and str(identifier) not in {item["id"] for item in choices[kind]}:
            raise collection_error("wechat_model_unavailable")


async def binding_summary(binding: WeChatKnowledgeBinding) -> dict:
    collection = await WeChatKnowledgeCollection.filter(binding_id=binding.id).first()
    kb = (
        await KnowledgeBase.filter(id=collection.knowledge_base_id).first()
        if collection and collection.knowledge_base_id
        else None
    )
    from app.models.wechat_agent import WeChatAgentConfig, WeChatAgentSession

    config = (
        await WeChatAgentConfig.filter(binding_id=binding.id)
        .prefetch_related("agent")
        .first()
    )
    session = (
        await WeChatAgentSession.filter(binding_id=binding.id, agent_id=config.agent_id)
        .prefetch_related("active_run")
        .first()
        if config and config.agent_id
        else None
    )
    return {
        "id": str(binding.id),
        "bot_id": binding.bot_id,
        "purpose": binding.purpose,
        "agent_config": {
            "agent_id": str(config.agent_id) if config.agent_id else None,
            "agent_name": config.agent.name if config.agent else None,
            "variables": config.variables,
            "stt_model_id": str(config.stt_model_id) if config.stt_model_id else None,
            "conversation_id": str(session.conversation_id)
            if session and session.conversation_id
            else None,
            "run_status": session.active_run.status
            if session and session.active_run
            else None,
            "run_id": str(session.active_run_id)
            if session and session.active_run_id
            else None,
        }
        if config
        else None,
        "collection": {
            "knowledge_base_id": str(kb.id) if kb else None,
            "knowledge_base_name": kb.name if kb else None,
            "vision_model_id": str(collection.vision_model_id)
            if collection.vision_model_id
            else None,
            "stt_model_id": str(collection.stt_model_id)
            if collection.stt_model_id
            else None,
        }
        if collection
        else None,
        "status": binding.status,
        "last_error": t(binding.last_error) if binding.last_error else None,
        "last_received_at": binding.last_received_at,
        "created_at": binding.created_at,
    }


async def start_login(user: User) -> WeChatKnowledgeLogin:
    await require_any_feature("wechat", ("agent_chat", "knowledge_collection"))
    await WeChatKnowledgeLogin.filter(user_id=user.id, expires_at__lt=utcnow()).delete()
    active = (
        await WeChatKnowledgeLogin.filter(user_id=user.id, expires_at__gt=utcnow())
        .exclude(status__in=["expired", "confirmed"])
        .count()
    )
    if active >= 3:
        raise collection_error("wechat_login_limit", 429)
    try:
        async with WeChatClient() as client:
            result = await client.get_qrcode()
    except WeChatAPIError as exc:
        raise collection_error("wechat_connection_failed", 502) from exc
    if not result.get("qrcode") or not result.get("qrcode_img_content"):
        raise collection_error("wechat_connection_failed", 502)
    return await WeChatKnowledgeLogin.create(
        user_id=user.id,
        qrcode=encrypt_secret(result["qrcode"]),
        qrcode_content=result["qrcode_img_content"],
        expires_at=utcnow() + timedelta(minutes=5),
    )


async def poll_login(
    login_id: UUID, user: User, verify_code: str | None = None
) -> dict:
    await require_any_feature("wechat", ("agent_chat", "knowledge_collection"))
    login = await WeChatKnowledgeLogin.filter(id=login_id, user_id=user.id).first()
    if not login:
        raise collection_error("wechat_login_not_found", 404)
    if login.expires_at <= utcnow() and login.status != "confirmed":
        login.status = "expired"
        await login.save(update_fields=["status"])
    elif login.status not in ("confirmed", "expired", "verify_code_blocked"):
        try:
            async with WeChatClient(login.base_url) as client:
                result = await client.get_qrcode_status(
                    decrypt_secret(login.qrcode), verify_code
                )
            state = result.get("status", "wait")
            if state == "scaned_but_redirect":
                host = str(result.get("redirect_host", ""))
                login.base_url = official_url(
                    host if host.startswith("https://") else f"https://{host}"
                )
                state = "scaned"
            if state == "binded_redirect":
                # We cannot reconstruct credentials for some other installation.
                raise collection_error("wechat_already_connected")
            if state == "confirmed":
                await require_any_feature(
                    "wechat", ("agent_chat", "knowledge_collection")
                )
                token, identity, bot = (
                    result.get("bot_token"),
                    result.get("ilink_user_id"),
                    result.get("ilink_bot_id"),
                )
                if not all(
                    isinstance(value, str) and value for value in (token, identity, bot)
                ):
                    raise WeChatAPIError("identity")
                base = official_url(result.get("baseurl") or login.base_url)
                try:
                    async with in_transaction() as db:
                        locked_login = (
                            await WeChatKnowledgeLogin.filter(id=login.id)
                            .using_db(db)
                            .select_for_update()
                            .get()
                        )
                        if locked_login.status == "confirmed":
                            binding = await WeChatKnowledgeBinding.get(
                                id=locked_login.binding_id, using_db=db
                            )
                        else:
                            binding = (
                                await WeChatKnowledgeBinding.filter(
                                    wechat_user_id=identity
                                )
                                .using_db(db)
                                .select_for_update()
                                .first()
                            )
                            if binding and binding.user_id != user.id:
                                raise collection_error("wechat_identity_in_use", 409)
                            values = dict(
                                user_id=user.id,
                                token=encrypt_secret(token),
                                bot_id=bot,
                                base_url=base,
                                cursor="",
                                generation=uuid4(),
                                status="connected",
                                last_error=None,
                            )
                            if binding:
                                binding.update_from_dict(values)
                                await binding.save(using_db=db)
                            else:
                                binding = await WeChatKnowledgeBinding.create(
                                    wechat_user_id=identity, using_db=db, **values
                                )
                            from app.services.audit_log import AuditLogService

                            await AuditLogService.log(
                                user=user,
                                action="connect_wechat_binding",
                                resource_type="wechat_binding",
                                resource_id=binding.id,
                                resource_name=bot,
                                operation="create",
                                status="success",
                                metadata={},
                            )
                            locked_login.status = "confirmed"
                            locked_login.binding_id = binding.id
                            await locked_login.save(
                                using_db=db, update_fields=["status", "binding_id"]
                            )
                        login = locked_login
                except IntegrityError as exc:
                    raise collection_error("wechat_identity_in_use", 409) from exc
            else:
                if state not in (
                    "wait",
                    "scaned",
                    "expired",
                    "need_verifycode",
                    "verify_code_blocked",
                ):
                    raise WeChatAPIError("login_status")
                login.status = state
                await login.save(update_fields=["status", "base_url"])
        except WeChatAPIError as exc:
            raise collection_error("wechat_connection_failed", 502) from exc
    output = {
        "id": str(login.id),
        "status": login.status,
        "qrcode_content": login.qrcode_content,
        "expires_at": login.expires_at,
    }
    if login.status == "confirmed" and login.binding_id:
        binding = await WeChatKnowledgeBinding.get(id=login.binding_id, user_id=user.id)
        output["binding"] = await binding_summary(binding)
    return output
