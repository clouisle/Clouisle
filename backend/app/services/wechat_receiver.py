"""Standalone receiver: no FastAPI worker owns long-lived WeChat polling."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from uuid import uuid4

from tortoise import Tortoise
from tortoise.transactions import in_transaction

from app.core.config import settings
from app.core.redis import close_redis, get_redis
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


async def receive_once(binding: WeChatKnowledgeBinding):
    redis = await get_redis()
    key, owner = f"wechat:poll:{binding.id}", str(uuid4())
    if not await redis.set(key, owner, nx=True, ex=90):
        await asyncio.sleep(2)
        return
    try:
        async with WeChatClient(
            binding.base_url, decrypt_secret(binding.token)
        ) as client:
            polling = asyncio.create_task(
                client.get_updates(
                    decrypt_secret(binding.cursor) if binding.cursor else ""
                )
            )
            try:
                while not polling.done():
                    done, _ = await asyncio.wait({polling}, timeout=1)
                    if done:
                        break
                    valid = await WeChatKnowledgeBinding.filter(
                        id=binding.id, status="connected", generation=binding.generation
                    ).exists()
                    lock_owner = await redis.get(key)
                    if not valid or lock_owner not in (owner, owner.encode()):
                        polling.cancel()
                        return
                response = await polling
                # Keep a bounded lease through the short receipt transaction.
                renewed = await redis.eval(
                    "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('expire',KEYS[1],90) else return 0 end",
                    1,
                    key,
                    owner,
                )
                if not renewed:
                    return
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
            finally:
                if not polling.done():
                    polling.cancel()
                with suppress(asyncio.CancelledError):
                    await polling
    except WeChatAPIError as exc:
        await WeChatKnowledgeBinding.filter(
            id=binding.id, generation=binding.generation, status="connected"
        ).update(
            last_error="wechat_authorization_expired"
            if exc.code == -14
            else "wechat_connection_failed",
            **({"status": "error"} if exc.code == -14 else {}),
        )
        await asyncio.sleep(5)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning(
            "WeChat receiver iteration failed; durable receipts remain recoverable"
        )
        await asyncio.sleep(5)
    finally:
        await redis.eval(
            "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",
            1,
            key,
            owner,
        )


async def run_receiver():
    active: dict = {}
    await Tortoise.init(
        db_url=settings.DATABASE_URL,
        modules={"models": ["app.models"]},
        _enable_global_fallback=True,
    )
    try:
        while True:
            bindings = await WeChatKnowledgeBinding.filter(status="connected").exclude(
                token=""
            )
            current = {row.id: row for row in bindings}
            for identifier, task in list(active.items()):
                if identifier not in current:
                    task.cancel()
                if task.done() or identifier not in current:
                    with suppress(asyncio.CancelledError, Exception):
                        await task
                    active.pop(identifier, None)
            for identifier, binding in current.items():
                if identifier not in active:
                    active[identifier] = asyncio.create_task(receive_once(binding))
            await asyncio.sleep(1)
    finally:
        for task in active.values():
            task.cancel()
        await asyncio.gather(*active.values(), return_exceptions=True)
        await Tortoise.close_connections()
        await close_redis()
