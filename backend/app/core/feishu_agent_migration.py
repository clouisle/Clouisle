"""Idempotent cutover from administrator lists/chat markers to user preferences."""

from tortoise.transactions import in_transaction

from app.models.feishu_agent import FeishuAgentPreference
from app.models.integration import Integration


async def migrate_feishu_agent_selection() -> None:
    """Keep each user's latest selected session, never distribute admin defaults."""
    async with in_transaction() as db:
        sqlite = db.capabilities.dialect == "sqlite"
        if sqlite:
            columns = await db.execute_query_dict(
                'PRAGMA table_info("feishu_agent_sessions")'
            )
            legacy = "is_selected" in {row["name"] for row in columns}
        else:
            await db.execute_query("SET LOCAL lock_timeout = '2s'")
            await db.execute_query(
                "SELECT pg_advisory_xact_lock(hashtext('feishu-agent-selection-schema'))"
            )
            columns = await db.execute_query_dict(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
                "AND table_name = 'feishu_agent_sessions'"
            )
            legacy = "is_selected" in {row["column_name"] for row in columns}
        preference_columns = await db.execute_query_dict(
            'PRAGMA table_info("feishu_agent_preferences")'
            if sqlite
            else "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'feishu_agent_preferences'"
        )
        names = {row["name" if sqlite else "column_name"] for row in preference_columns}
        if "is_enabled" not in names:
            await db.execute_query(
                "ALTER TABLE feishu_agent_preferences ADD COLUMN is_enabled BOOLEAN NOT NULL DEFAULT FALSE"
            )
            await db.execute_query(
                "UPDATE feishu_agent_preferences SET is_enabled = TRUE WHERE agent_id IS NOT NULL"
            )
        # The column is the one-time migration marker. Never reconstruct a
        # cleared personal preference from historical sessions on restart.
        if legacy:
            rows = await db.execute_query_dict(
                "SELECT integration_id, user_id, agent_id FROM ("
                " SELECT integration_id, user_id, agent_id, row_number() OVER ("
                " PARTITION BY integration_id, user_id ORDER BY is_selected DESC, updated_at DESC, id DESC"
                " ) AS position FROM feishu_agent_sessions WHERE agent_id IS NOT NULL"
                ") AS ranked WHERE position = 1"
            )
            for row in rows:
                await FeishuAgentPreference.get_or_create(
                    integration_id=row["integration_id"],
                    user_id=row["user_id"],
                    defaults={"agent_id": row["agent_id"], "is_enabled": True},
                    using_db=db,
                )
            await db.execute_query(
                "DROP INDEX IF EXISTS idx_feishu_agent_session_selected"
            )
            await db.execute_query(
                "ALTER TABLE feishu_agent_sessions DROP COLUMN is_selected"
            )
        for integration in await Integration.filter(provider_type="feishu").using_db(
            db
        ):
            if "agent_chat_agent_ids" in integration.config:
                integration.config = {
                    key: value
                    for key, value in integration.config.items()
                    if key != "agent_chat_agent_ids"
                }
                await integration.save(using_db=db, update_fields=["config"])
