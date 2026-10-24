"""Cut provider-specific delivery tables over to ``integration_deliveries``.

Messaging integrations share one durable outbound queue instead of a table per
provider. Existing deployments still hold rows in ``feishu_agent_deliveries``
and ``wechat_agent_deliveries``; this migration copies them once, then removes
the legacy tables so no integration keeps a private delivery table.

Deploy API and workers together: an old process would insert into a table this
migration has already dropped.
"""

import logging

from tortoise.transactions import in_transaction

logger = logging.getLogger(__name__)

_FEISHU_COLUMNS = """
    id, integration_id, provider_type, receipt_id, user_id, agent_id, run_id,
    chat_id, message_id, event_key, sequence, provider_uuid, kind, text, payload,
    asset_id, filename, content_type, size, media_type, media_key, status, error,
    created_at, updated_at
"""


async def _ensure_delivery_columns(db, sqlite: bool) -> None:
    """Add columns introduced after a deployment already created the queue."""
    if sqlite:
        columns = await db.execute_query_dict(
            'PRAGMA table_info("integration_deliveries")'
        )
        names = {row["name"] for row in columns}
    else:
        columns = await db.execute_query_dict(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'integration_deliveries'"
        )
        names = {row["column_name"] for row in columns}
    if "error_detail" not in names:
        await db.execute_query(
            'ALTER TABLE integration_deliveries ADD COLUMN "error_detail" TEXT'
        )
        logger.info("Added integration_deliveries.error_detail")


async def _table_exists(db, sqlite: bool, name: str) -> bool:
    if sqlite:
        rows = await db.execute_query_dict(
            f"SELECT name FROM sqlite_master WHERE type = 'table' AND name = '{name}'"
        )
    else:
        rows = await db.execute_query_dict(
            f"SELECT to_regclass('public.{name}') AS name"
        )
    return bool(rows and rows[0].get("name"))


async def _copy_feishu(db, sqlite: bool) -> None:
    if sqlite:
        sql = f"""
        INSERT OR IGNORE INTO integration_deliveries ({_FEISHU_COLUMNS})
        SELECT d.id, i.id, 'feishu', d.receipt_id, r.user_id, r.agent_id,
               r.run_id, r.chat_id, r.message_id, d.event_key, d.sequence,
               d.uuid, d.kind, d.text, '{{}}', d.asset_id, d.filename,
               d.content_type, d.size, d.media_type, d.media_key, d.status,
               d.error, d.created_at, d.updated_at
        FROM feishu_agent_deliveries d
        JOIN feishu_agent_receipts r ON r.id = d.receipt_id
        LEFT JOIN integrations i ON i.provider_type = 'feishu'
        """
    else:
        sql = f"""
        INSERT INTO integration_deliveries ({_FEISHU_COLUMNS})
        SELECT d.id, i.id, 'feishu', d.receipt_id, r.user_id, r.agent_id,
               r.run_id, r.chat_id, r.message_id, d.event_key, d.sequence,
               d.uuid, d.kind, d.text, '{{}}'::jsonb, d.asset_id, d.filename,
               d.content_type, d.size, d.media_type, d.media_key, d.status,
               d.error, d.created_at, d.updated_at
        FROM feishu_agent_deliveries d
        JOIN feishu_agent_receipts r ON r.id = d.receipt_id
        LEFT JOIN integrations i ON i.provider_type = 'feishu'
        ON CONFLICT (id) DO NOTHING
        """
    await db.execute_query(sql)


async def _copy_wechat(db, sqlite: bool) -> None:
    if sqlite:
        sql = f"""
        INSERT OR IGNORE INTO integration_deliveries ({_FEISHU_COLUMNS})
        SELECT d.id, i.id, 'wechat', d.receipt_id, r.user_id, r.agent_id,
               r.run_id, r.binding_id, r.message_id, d.event_key, d.sequence,
               NULL,
               COALESCE(json_extract(d.payload, '$.kind'), 'text'),
               COALESCE(json_extract(d.payload, '$.text'), ''),
               d.payload,
               json_extract(d.payload, '$.asset_id'),
               COALESCE(json_extract(d.payload, '$.filename'), a.display_filename),
               COALESCE(json_extract(d.payload, '$.content_type'), a.content_type),
               COALESCE(CAST(json_extract(d.payload, '$.size') AS INTEGER), a.size),
               NULL, NULL,
               CASE WHEN d.status = 'submitted' THEN 'sent' ELSE d.status END,
               d.error, d.created_at, d.updated_at
        FROM wechat_agent_deliveries d
        JOIN wechat_agent_receipts r ON r.id = d.receipt_id
        LEFT JOIN assets a ON a.id = json_extract(d.payload, '$.asset_id')
        LEFT JOIN integrations i ON i.provider_type = 'wechat'
        """
    else:
        sql = f"""
        INSERT INTO integration_deliveries ({_FEISHU_COLUMNS})
        SELECT d.id, i.id, 'wechat', d.receipt_id, r.user_id, r.agent_id,
               r.run_id, r.binding_id::text, r.message_id, d.event_key,
               d.sequence, NULL,
               COALESCE(d.payload->>'kind', 'text'),
               COALESCE(d.payload->>'text', ''),
               d.payload,
               NULLIF(d.payload->>'asset_id', '')::uuid,
               COALESCE(d.payload->>'filename', a.display_filename),
               COALESCE(d.payload->>'content_type', a.content_type),
               COALESCE(NULLIF(d.payload->>'size', '')::bigint, a.size),
               NULL, NULL,
               CASE WHEN d.status = 'submitted' THEN 'sent' ELSE d.status END,
               d.error, d.created_at, d.updated_at
        FROM wechat_agent_deliveries d
        JOIN wechat_agent_receipts r ON r.id = d.receipt_id
        LEFT JOIN assets a ON a.id = NULLIF(d.payload->>'asset_id', '')::uuid
        LEFT JOIN integrations i ON i.provider_type = 'wechat'
        ON CONFLICT (id) DO NOTHING
        """
    await db.execute_query(sql)


async def migrate_integration_deliveries() -> None:
    """Copy legacy provider queues once, then drop their tables."""
    async with in_transaction() as db:
        sqlite = db.capabilities.dialect == "sqlite"
        if not sqlite:
            await db.execute_query("SET LOCAL lock_timeout = '5s'")
            await db.execute_query(
                "SELECT pg_advisory_xact_lock(hashtext('integration-deliveries-schema'))"
            )
        await _ensure_delivery_columns(db, sqlite)
        if await _table_exists(db, sqlite, "feishu_agent_deliveries"):
            await _copy_feishu(db, sqlite)
            await db.execute_query("DROP TABLE feishu_agent_deliveries")
            logger.info("Migrated Feishu deliveries into integration_deliveries")
        if await _table_exists(db, sqlite, "wechat_agent_deliveries"):
            await _copy_wechat(db, sqlite)
            await db.execute_query("DROP TABLE wechat_agent_deliveries")
            logger.info("Migrated WeChat deliveries into integration_deliveries")
