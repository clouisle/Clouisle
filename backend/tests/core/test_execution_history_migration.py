"""The history cutover only adds columns; legacy rows stay the owner's history."""

from contextlib import asynccontextmanager
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from tortoise.context import TortoiseContext

from app.core import execution_history_migration as migration
from app.core.execution_history_migration import migrate_execution_history_schema


@pytest.mark.asyncio
async def test_sqlite_schema_does_not_need_cutover():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await migrate_execution_history_schema()


@pytest.mark.asyncio
@pytest.mark.parametrize("already_migrated", [True, False])
async def test_postgres_migration_adds_columns_without_rewriting_rows(
    monkeypatch, already_migrated
):
    execute = AsyncMock()
    conn = SimpleNamespace(
        capabilities=SimpleNamespace(dialect="postgres"), execute_query=execute
    )

    @asynccontextmanager
    async def transaction():
        yield conn

    monkeypatch.setattr(migration, "in_transaction", transaction)
    monkeypatch.setattr(
        "app.core.integration_migration._tables",
        AsyncMock(return_value={"conversations", "messages", "agent_runs"}),
    )
    monkeypatch.setattr(
        "app.core.integration_migration._columns",
        AsyncMock(
            return_value={"api_key_origin_unknown"} if already_migrated else set()
        ),
    )

    await migrate_execution_history_schema()

    statements = [call.args[0] for call in execute.await_args_list]
    assert "pg_advisory_xact_lock" in statements[0]
    writes = statements[3:]
    if already_migrated:
        assert not writes
        return

    # One ALTER per table and nothing else: legacy rows are never re-attributed.
    assert writes == [
        "ALTER TABLE conversations ADD COLUMN api_key_id UUID, "
        "ADD COLUMN api_key_origin_unknown BOOLEAN NOT NULL DEFAULT FALSE"
    ]


def test_migration_carries_no_backfill_statements():
    """There is no classification SQL to run: old records belong to their owner."""
    assert not [
        name
        for name in dir(migration)
        if name.startswith("_AGENT") or name.startswith("_WORKFLOW")
    ]


@pytest.mark.asyncio
async def test_legacy_rows_become_the_owners_own_history():
    url = os.getenv("EXECUTION_HISTORY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("set EXECUTION_HISTORY_TEST_DATABASE_URL to a disposable, empty DB")
    async with TortoiseContext() as context:
        await context.init(db_url=url, modules={"models": ["app.models"]})
        conn = context.connections.get("default")
        await conn.execute_script("""
            CREATE TABLE conversations (id uuid PRIMARY KEY);
            CREATE TABLE messages (id uuid, conversation_id uuid, role text, round_id uuid);
            CREATE TABLE agent_runs (
                conversation_id uuid, api_key_id uuid, worker_payload jsonb,
                source_message_id uuid, active_round_id uuid
            );
            CREATE TABLE workflow_runs (
                id uuid PRIMARY KEY, root_run_id uuid, trigger_type text,
                is_debug boolean DEFAULT false, context_snapshot jsonb
            );
            CREATE TABLE audit_logs (
                action text, metadata jsonb, api_key_id uuid, resource_id uuid,
                auth_method text
            );
        """)
        try:
            key, other_key = uuid4(), uuid4()
            web, single, two_keys, mixed, untracked = (uuid4() for _ in range(5))
            webhook, embed_run, manual = (uuid4() for _ in range(3))
            await conn.execute_script(f"""
                INSERT INTO conversations VALUES ('{web}'), ('{single}'),
                    ('{two_keys}'), ('{mixed}'), ('{untracked}');
                INSERT INTO messages (id, conversation_id, role) VALUES
                    (gen_random_uuid(), '{untracked}', 'user');
                INSERT INTO agent_runs (conversation_id, api_key_id, worker_payload) VALUES
                    ('{web}', NULL, '{{"tool_entrypoint":"chat"}}'),
                    ('{single}', '{key}', NULL),
                    ('{two_keys}', '{key}', NULL),
                    ('{two_keys}', '{other_key}', NULL),
                    ('{mixed}', '{key}', NULL);
                INSERT INTO workflow_runs (id, root_run_id, trigger_type, context_snapshot) VALUES
                    ('{webhook}', NULL, 'webhook',
                     '{{"execution_origin":{{"entrypoint":"api_key","entrypoint_id":"{key}"}}}}'),
                    ('{embed_run}', NULL, 'manual',
                     '{{"execution_origin":{{"entrypoint":"embed"}}}}'),
                    ('{manual}', NULL, 'manual', NULL);
                INSERT INTO audit_logs VALUES
                    ('run_workflow_embed', '{{"run_id":"{embed_run}"}}', '{key}', NULL, 'api_key');
            """)

            async def snapshot():
                conversations = await conn.execute_query_dict(
                    "SELECT id, api_key_id, api_key_origin_unknown FROM conversations"
                )
                runs = await conn.execute_query_dict(
                    "SELECT id, api_key_id, api_key_origin_unknown FROM workflow_runs"
                )
                return conversations, runs

            async def identifier_sets():
                conversations = await conn.execute_query_dict(
                    "SELECT id FROM conversations"
                )
                runs = await conn.execute_query_dict("SELECT id FROM workflow_runs")
                return {row["id"] for row in conversations}, {row["id"] for row in runs}

            before = await identifier_sets()
            await migrate_execution_history_schema()
            after_first = await snapshot()
            await migrate_execution_history_schema()
            after_second = await snapshot()

            # Every legacy row keeps its id and is served as the owner's own
            # history: no key attribution, no quarantine, nothing deleted.
            for rows in (after_first[0], after_first[1]):
                assert rows
                assert all(row["api_key_id"] is None for row in rows)
                assert all(row["api_key_origin_unknown"] is False for row in rows)
            assert (after_first[0] and {row["id"] for row in after_first[0]}) == before[
                0
            ]
            assert (after_first[1] and {row["id"] for row in after_first[1]}) == before[
                1
            ]
            # Second run is a no-op even though the columns already exist.
            assert after_second == after_first
        finally:
            await conn.execute_script(
                "DROP TABLE audit_logs, workflow_runs, agent_runs, messages, conversations"
            )
