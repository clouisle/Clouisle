"""WeChat update polling: one durable batch per binding per tick."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from uuid import uuid4

import httpx

from tortoise.transactions import in_transaction

from app.core.redis import get_redis
from app.core.celery import celery_app
from app.integrations.credentials import decrypt_secret, encrypt_secret
from app.integrations.wechat import WeChatAPIError, WeChatClient
from app.models.wechat_knowledge import (
    WeChatKnowledgeBinding,
    WeChatKnowledgeCollection,
    WeChatKnowledgeReceipt,
)
from app.models.wechat_agent import WeChatAgentConfig, WeChatAgentReceipt
from app.services.wechat_connection import utcnow
from app.services.integration_features import enabled_features

logger = logging.getLogger(__name__)


@dataclass
class UpdateAcceptResult:
    agent_receipt_ids: list[str] = field(default_factory=list)
    knowledge_receipt_ids: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> int:
        return len(self.agent_receipt_ids) + len(self.knowledge_receipt_ids)


def _candidate_messages(
    binding: WeChatKnowledgeBinding, response: dict
) -> list[tuple[str, dict]]:
    messages = response.get("msgs") or []
    if not isinstance(messages, list):
        raise WeChatAPIError("invalid_messages")
    candidates = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if (
            message.get("from_user_id") != binding.wechat_user_id
            or message.get("message_type") != 1
            or message.get("message_state") != 2
        ):
            continue
        identifier = message.get("message_id")
        if identifier is None or len(str(identifier)) > 128:
            continue
        candidates.append((str(identifier), message))
    return candidates


async def accept_updates(
    binding: WeChatKnowledgeBinding, response: dict
) -> UpdateAcceptResult:
    """Atomically commit new receipt snapshots before acknowledging the cursor."""
    candidates = _candidate_messages(binding, response)
    cursor = response.get("get_updates_buf")
    prior_cursor = decrypt_secret(binding.cursor) if binding.cursor else ""
    if (
        not candidates
        and (cursor is None or str(cursor) == prior_cursor)
        and not getattr(binding, "last_error", None)
    ):
        return UpdateAcceptResult()

    result = UpdateAcceptResult()
    async with in_transaction() as db:
        current = (
            await WeChatKnowledgeBinding.filter(id=binding.id)
            .using_db(db)
            .select_for_update()
            .first()
        )
        if (
            not current
            or current.status != "connected"
            or current.generation != binding.generation
            or (
                getattr(binding, "poll_claim", None) is not None
                and (
                    current.poll_claim != getattr(binding, "poll_claim", None)
                    or current.poll_claim_expires_at is None
                    or current.poll_claim_expires_at <= utcnow()
                )
            )
            or current.cursor != binding.cursor
        ):
            return result
        feature = "agent_chat" if current.purpose == "agent" else current.purpose
        enabled = await enabled_features("wechat")
        if not enabled or (current.purpose != "none" and feature not in enabled):
            return result

        collection = None
        agent_config = None
        if candidates and current.purpose == "knowledge_collection":
            collection = (
                await WeChatKnowledgeCollection.filter(binding_id=current.id)
                .using_db(db)
                .first()
            )
        elif candidates and current.purpose == "agent":
            agent_config = (
                await WeChatAgentConfig.filter(binding_id=current.id)
                .using_db(db)
                .first()
            )

        for identifier, message in candidates:
            if current.purpose == "agent":
                if not agent_config or not agent_config.agent_id:
                    continue
                if (
                    await WeChatKnowledgeReceipt.filter(
                        binding_id=current.id, message_id=identifier
                    )
                    .using_db(db)
                    .exists()
                ):
                    continue
                receipt, created = await WeChatAgentReceipt.get_or_create(
                    binding_id=current.id,
                    message_id=identifier,
                    using_db=db,
                    defaults={
                        "user_id": current.user_id,
                        "agent_id": agent_config.agent_id,
                        "variables": agent_config.variables,
                        "stt_model_id": agent_config.stt_model_id,
                        "payload": encrypt_secret(
                            json.dumps(message, ensure_ascii=False)
                        ),
                    },
                )
                if created:
                    result.agent_receipt_ids.append(str(receipt.id))
                continue
            if (
                current.purpose != "knowledge_collection"
                or not collection
                or not collection.knowledge_base_id
            ):
                continue
            if (
                await WeChatAgentReceipt.filter(
                    binding_id=current.id, message_id=identifier
                )
                .using_db(db)
                .exists()
            ):
                continue
            knowledge_receipt, created = await WeChatKnowledgeReceipt.get_or_create(
                binding_id=current.id,
                message_id=identifier,
                using_db=db,
                defaults={
                    "user_id": current.user_id,
                    "knowledge_base_id": collection.knowledge_base_id,
                    "vision_model_id": collection.vision_model_id,
                    "stt_model_id": collection.stt_model_id,
                    "payload": encrypt_secret(json.dumps(message, ensure_ascii=False)),
                },
            )
            if created:
                result.knowledge_receipt_ids.append(str(knowledge_receipt.id))

        cursor_changed = cursor is not None and str(cursor) != prior_cursor
        if cursor_changed:
            current.cursor = encrypt_secret(str(cursor))
        has_new_receipts = result.accepted > 0
        if has_new_receipts:
            current.last_received_at = utcnow()
        if cursor_changed or has_new_receipts or current.last_error:
            current.last_error = None
            await current.save(
                using_db=db,
                update_fields=[
                    "cursor",
                    "last_received_at",
                    "last_error",
                    "updated_at",
                ],
            )
    return result


# A scheduled poll returns quickly: the upstream long-poll is bounded so one
# Beat tick never occupies a worker slot for the full HTTP timeout.
POLL_WAIT_SECONDS = 2.5
LEASE_SECONDS = 90


async def poll_binding(
    binding: WeChatKnowledgeBinding, *, http: httpx.AsyncClient | None = None
) -> dict:
    """Read one update batch for a binding and persist it durably."""
    feature = "agent_chat" if binding.purpose == "agent" else binding.purpose
    if feature not in await enabled_features("wechat"):
        return {"polled": False, "reason": "feature_disabled"}
    redis = await get_redis()
    key, owner = f"wechat:poll:{binding.id}", str(uuid4())
    if not await redis.set(key, owner, nx=True, ex=LEASE_SECONDS):
        return {"polled": False, "reason": "leased"}
    try:
        client_args = (binding.base_url, decrypt_secret(binding.token))
        client_context = (
            WeChatClient(*client_args, http=http)
            if http is not None
            else WeChatClient(*client_args)
        )
        async with client_context as client:
            response = await client.get_updates(
                decrypt_secret(binding.cursor) if binding.cursor else "",
                wait_seconds=POLL_WAIT_SECONDS,
            )
        renewed = await redis.eval(
            "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('expire',KEYS[1],ARGV[2]) else return 0 end",
            1,
            key,
            owner,
            LEASE_SECONDS,
        )
        if not renewed:
            return {"polled": False, "reason": "lease_lost"}
        accepted = await accept_updates(binding, response)
        if accepted.agent_receipt_ids:
            from app.services.wechat_agent_dispatch import enqueue_binding

            await enqueue_binding(binding.id)
        for receipt_id in accepted.knowledge_receipt_ids:
            await asyncio.to_thread(
                celery_app.send_task,
                "app.tasks.wechat_knowledge.process_receipt_task",
                args=[receipt_id],
                queue="knowledge",
            )
        return {"polled": True, "accepted": accepted.accepted}
    except WeChatAPIError as exc:
        await WeChatKnowledgeBinding.filter(
            id=binding.id, generation=binding.generation, status="connected"
        ).update(
            last_error="wechat_authorization_expired"
            if exc.code == -14
            else "wechat_connection_failed",
            **({"status": "error"} if exc.code == -14 else {}),
        )
        return {"polled": False, "reason": "wechat_error", "code": exc.code}
    finally:
        await redis.eval(
            "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",
            1,
            key,
            owner,
        )
