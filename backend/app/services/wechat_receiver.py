"""WeChat update polling: one durable batch per binding per tick."""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import uuid4

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


async def accept_updates(binding: WeChatKnowledgeBinding, response: dict) -> list[str]:
    """Atomically commit receipt snapshots before acknowledging the upstream cursor."""
    accepted_agent = False
    ids = []
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
            or current.cursor != binding.cursor
        ):
            return []
        feature = "agent_chat" if current.purpose == "agent" else current.purpose
        enabled = await enabled_features("wechat")
        if not enabled or (current.purpose != "none" and feature not in enabled):
            return []
        messages = response.get("msgs") or []
        if not isinstance(messages, list):
            raise WeChatAPIError("invalid_messages")
        collection = (
            await WeChatKnowledgeCollection.filter(binding_id=current.id)
            .using_db(db)
            .first()
        )
        agent_config = (
            await WeChatAgentConfig.filter(binding_id=current.id).using_db(db).first()
        )
        for message in messages:
            if not isinstance(message, dict):
                continue
            if (
                message.get("from_user_id") != current.wechat_user_id
                or message.get("message_type") != 1
                or message.get("message_state") != 2
            ):
                continue
            identifier = message.get("message_id")
            if identifier is None or len(str(identifier)) > 128:
                continue
            if (
                await WeChatAgentReceipt.filter(
                    binding_id=current.id, message_id=str(identifier)
                )
                .using_db(db)
                .exists()
            ):
                continue
            if (
                current.purpose == "agent"
                and await WeChatKnowledgeReceipt.filter(
                    binding_id=current.id, message_id=str(identifier)
                )
                .using_db(db)
                .exists()
            ):
                continue
            if current.purpose == "agent":
                if agent_config and agent_config.agent_id:
                    await WeChatAgentReceipt.get_or_create(
                        binding_id=current.id,
                        message_id=str(identifier),
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
                    accepted_agent = True
                continue
            if (
                current.purpose != "knowledge_collection"
                or not collection
                or not collection.knowledge_base_id
            ):
                continue
            receipt, _ = await WeChatKnowledgeReceipt.get_or_create(
                binding_id=current.id,
                message_id=str(identifier),
                using_db=db,
                defaults={
                    "user_id": current.user_id,
                    "knowledge_base_id": collection.knowledge_base_id,
                    "vision_model_id": collection.vision_model_id,
                    "stt_model_id": collection.stt_model_id,
                    "payload": encrypt_secret(json.dumps(message, ensure_ascii=False)),
                },
            )
            ids.append(str(receipt.id))
        cursor = response.get("get_updates_buf")
        if cursor:
            current.cursor = encrypt_secret(str(cursor))
        current.last_received_at = (
            utcnow() if ids or accepted_agent else current.last_received_at
        )
        current.last_error = None
        await current.save(
            using_db=db,
            update_fields=["cursor", "last_received_at", "last_error", "updated_at"],
        )
    return ids


# A scheduled poll returns quickly: the upstream long-poll is bounded so one
# Beat tick never occupies a worker slot for the full HTTP timeout.
POLL_WAIT_SECONDS = 2.5
LEASE_SECONDS = 90


async def poll_binding(binding: WeChatKnowledgeBinding) -> dict:
    """Read one update batch for a binding and persist it durably.

    Safe to call from any number of workers: a Redis lease elects a single
    poller per binding, and ``accept_updates`` re-checks the cursor and
    generation under a row lock before committing.
    """
    feature = "agent_chat" if binding.purpose == "agent" else binding.purpose
    if feature not in await enabled_features("wechat"):
        return {"polled": False, "reason": "feature_disabled"}
    redis = await get_redis()
    key, owner = f"wechat:poll:{binding.id}", str(uuid4())
    if not await redis.set(key, owner, nx=True, ex=LEASE_SECONDS):
        return {"polled": False, "reason": "leased"}
    try:
        async with WeChatClient(
            binding.base_url, decrypt_secret(binding.token)
        ) as client:
            response = await client.get_updates(
                decrypt_secret(binding.cursor) if binding.cursor else "",
                wait_seconds=POLL_WAIT_SECONDS,
            )
        # Keep the lease through the short receipt transaction.
        renewed = await redis.eval(
            "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('expire',KEYS[1],ARGV[2]) else return 0 end",
            1,
            key,
            owner,
            LEASE_SECONDS,
        )
        if not renewed:
            return {"polled": False, "reason": "lease_lost"}
        ids = await accept_updates(binding, response)
        if binding.purpose == "agent":
            await asyncio.to_thread(
                celery_app.send_task,
                "app.tasks.wechat_agent.process_binding_task",
                args=[str(binding.id)],
                queue="agent",
            )
        for receipt_id in ids:
            await asyncio.to_thread(
                celery_app.send_task,
                "app.tasks.wechat_knowledge.process_receipt_task",
                args=[receipt_id],
                queue="knowledge",
            )
        return {"polled": True, "accepted": len(ids)}
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


async def poll_connected_bindings() -> dict:
    """Poll every connected binding once; called by the Celery Beat tick."""
    enabled = await enabled_features("wechat")
    purposes = [
        purpose
        for purpose, feature in (
            ("agent", "agent_chat"),
            ("knowledge_collection", "knowledge_collection"),
        )
        if feature in enabled
    ]
    if not purposes:
        return {"bindings": 0, "polled": 0}
    bindings = await WeChatKnowledgeBinding.filter(
        status="connected", purpose__in=purposes
    ).exclude(token="")
    results = await asyncio.gather(
        *(poll_binding(binding) for binding in bindings), return_exceptions=True
    )
    polled = sum(
        1 for result in results if isinstance(result, dict) and result.get("polled")
    )
    return {"bindings": len(bindings), "polled": polled}
