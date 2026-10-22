"""Idempotent startup upgrades for legacy WeChat collection schemas."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from tortoise import Tortoise
from tortoise.context import TortoiseContext

from app.core.wechat_migration import migrate_wechat_knowledge_schema


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield


@pytest.mark.asyncio
async def test_current_schema_migration_is_idempotent(database):
    connection = Tortoise.get_connection("default")
    await migrate_wechat_knowledge_schema()

    columns = await connection.execute_query_dict(
        'PRAGMA table_info("wechat_knowledge_bindings")'
    )
    names = {column["name"] for column in columns}
    assert "disconnected_at" in names
    assert "knowledge_base_id" not in names
    await migrate_wechat_knowledge_schema()
    after_rerun = await connection.execute_query_dict(
        'PRAGMA table_info("wechat_knowledge_bindings")'
    )
    assert {column["name"] for column in after_rerun} == names


@pytest.mark.asyncio
async def test_missing_disconnected_column_is_added(database):
    connection = Tortoise.get_connection("default")
    await connection.execute_query(
        'ALTER TABLE "wechat_knowledge_bindings" DROP COLUMN "disconnected_at"'
    )

    await migrate_wechat_knowledge_schema()

    columns = await connection.execute_query_dict(
        'PRAGMA table_info("wechat_knowledge_bindings")'
    )
    assert "disconnected_at" in {column["name"] for column in columns}


@pytest.mark.asyncio
async def test_column_upgrade_failure_propagates_without_claiming_success(
    database, monkeypatch
):
    connection = Tortoise.get_connection("default")
    original_execute_query = connection.execute_query

    async def fail_disconnected_column_ddl(query, *args, **kwargs):
        if 'ADD COLUMN "disconnected_at"' in query:
            raise RuntimeError("simulated DDL failure")
        return await original_execute_query(query, *args, **kwargs)

    monkeypatch.setattr(connection, "execute_query", fail_disconnected_column_ddl)
    await connection.execute_query(
        'ALTER TABLE "wechat_knowledge_bindings" DROP COLUMN "disconnected_at"'
    )
    with pytest.raises(RuntimeError, match="simulated DDL failure"):
        await migrate_wechat_knowledge_schema()

    monkeypatch.setattr(connection, "execute_query", original_execute_query)
    columns = await connection.execute_query_dict(
        'PRAGMA table_info("wechat_knowledge_bindings")'
    )
    assert "disconnected_at" not in {column["name"] for column in columns}


class FakeDatabase:
    capabilities = type("Capabilities", (), {"dialect": "postgres"})()

    def __init__(self, column_rows=()):
        self.column_rows = list(column_rows)
        self.queries = []

    async def execute_query(self, query, *args):
        self.queries.append(query)

    async def execute_query_dict(self, query, *args):
        self.queries.append(query)
        if "information_schema.columns" in query:
            return self.column_rows
        return []


class FakeTransaction:
    def __init__(self, database):
        self.database = database

    async def __aenter__(self):
        return self.database

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_postgres_purpose_migration_skips_existing_column(monkeypatch):
    from tortoise import transactions
    from app.core.wechat_migration import migrate_wechat_purpose

    db = FakeDatabase(column_rows=[{"column_name": "purpose"}])
    monkeypatch.setattr(transactions, "in_transaction", lambda: FakeTransaction(db))

    await migrate_wechat_purpose()

    assert any("pg_advisory_xact_lock" in query for query in db.queries)
    assert not any(
        "ALTER TABLE wechat_knowledge_bindings" in query for query in db.queries
    )


@pytest.mark.asyncio
async def test_postgres_purpose_migration_adds_missing_column(monkeypatch):
    from tortoise import transactions
    from app.core.wechat_migration import migrate_wechat_purpose

    db = FakeDatabase()
    monkeypatch.setattr(transactions, "in_transaction", lambda: FakeTransaction(db))

    await migrate_wechat_purpose()

    alterations = [
        query
        for query in db.queries
        if "ALTER TABLE wechat_knowledge_bindings" in query
    ]
    assert alterations == [
        "ALTER TABLE wechat_knowledge_bindings ADD COLUMN purpose VARCHAR(24) NOT NULL DEFAULT 'none'"
    ]
    assert any(
        "UPDATE wechat_knowledge_bindings SET purpose='knowledge_collection'" in query
        for query in db.queries
    )


@pytest.mark.asyncio
async def test_postgres_legacy_configuration_drops_old_columns(monkeypatch):
    from tortoise import transactions
    from app.core.wechat_migration import _migrate_wechat_connection_configuration

    db = FakeDatabase(
        column_rows=[{"column_name": "knowledge_base_id"}, {"column_name": "id"}]
    )
    lookups = iter(
        [
            [{"column_name": "knowledge_base_id"}],
            [{"column_name": "knowledge_base_id"}],
        ]
    )

    async def columns(query, *args):
        db.queries.append(query)
        return next(lookups, [])

    db.execute_query_dict = columns
    monkeypatch.setattr(transactions, "in_transaction", lambda: FakeTransaction(db))

    await _migrate_wechat_connection_configuration()

    drops = [query for query in db.queries if "DROP COLUMN IF EXISTS" in query]
    assert len(drops) == 6
    assert any(
        "INSERT INTO wechat_knowledge_collections" in query for query in db.queries
    )


@pytest.mark.asyncio
async def test_sqlite_purpose_column_is_added_and_backfilled(database):
    from app.core.wechat_migration import migrate_wechat_purpose

    connection = Tortoise.get_connection("default")
    await connection.execute_query(
        'ALTER TABLE "wechat_knowledge_bindings" DROP COLUMN "purpose"'
    )

    await migrate_wechat_purpose()

    columns = await connection.execute_query_dict(
        'PRAGMA table_info("wechat_knowledge_bindings")'
    )
    purpose = next(column for column in columns if column["name"] == "purpose")
    assert purpose["dflt_value"] == "'none'"


@pytest.mark.asyncio
async def test_sqlite_legacy_configuration_rebuilds_both_tables(database):
    connection = Tortoise.get_connection("default")
    for column in ("knowledge_base_id", "vision_model_id", "stt_model_id"):
        await connection.execute_query(
            f'ALTER TABLE "wechat_knowledge_bindings" ADD COLUMN {column} VARCHAR(36) NULL'
        )
    for column in ("knowledge_base_id", "vision_model_id", "stt_model_id"):
        await connection.execute_query(
            f'ALTER TABLE "wechat_knowledge_logins" ADD COLUMN {column} VARCHAR(36) NULL'
        )

    await migrate_wechat_knowledge_schema()

    for table in ("wechat_knowledge_bindings", "wechat_knowledge_logins"):
        columns = await connection.execute_query_dict(f'PRAGMA table_info("{table}")')
        assert "knowledge_base_id" not in {column["name"] for column in columns}


@pytest.mark.asyncio
async def test_postgres_outer_migration_skips_sqlite_foreign_key_pragmas(monkeypatch):
    from app.core import wechat_migration

    connection = FakeDatabase()
    monkeypatch.setattr(Tortoise, "get_connection", lambda name: connection)
    inner = AsyncMock()
    monkeypatch.setattr(
        wechat_migration, "_migrate_wechat_connection_configuration", inner
    )

    await wechat_migration.migrate_wechat_connection_configuration()

    assert connection.queries == []
    inner.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_restore_sources_skips_non_wechat_documents(database):
    from uuid import uuid4

    from app.core.wechat_migration import restore_wechat_document_sources
    from app.models.knowledge_base import Document, KnowledgeBase
    from app.models.user import Team, User

    team = await Team.create(name="Migration test team")
    user = await User.create(
        username="migration-doc",
        email="migration-doc@example.test",
        hashed_password="unused",
    )
    kb = await KnowledgeBase.create(name="Migration KB", team=team, created_by=user)
    document = await Document.create(
        id=uuid4(),
        knowledge_base=kb,
        uploaded_by=user,
        name="ordinary.md",
        doc_type="markdown",
        metadata={"source": "upload"},
    )

    await restore_wechat_document_sources()
    await document.refresh_from_db()

    assert document.doc_type == "markdown"
    assert document.metadata == {"source": "upload"}


@pytest.mark.asyncio
async def test_polling_upgrade_preserves_existing_binding_and_becomes_schedulable(
    database,
):
    from app.models.user import User
    from app.models.wechat_knowledge import WeChatKnowledgeBinding
    from app.services.wechat_connection import utcnow

    connection = Tortoise.get_connection("default")
    user = await User.create(
        username="legacy-poll",
        email="legacy-poll@example.test",
        hashed_password="unused",
    )
    binding = await WeChatKnowledgeBinding.create(
        user=user,
        wechat_user_id="legacy",
        bot_id="legacy",
        token="encrypted",
        base_url="https://ilinkai.weixin.qq.com",
        purpose="agent",
    )
    for name in (
        "poll_next_at",
        "poll_claim",
        "poll_claim_expires_at",
        "agent_recovery_at",
    ):
        await connection.execute_query(
            f'ALTER TABLE "wechat_knowledge_bindings" DROP COLUMN "{name}"'
        )
    await migrate_wechat_knowledge_schema()
    await migrate_wechat_knowledge_schema()
    saved = await WeChatKnowledgeBinding.get(id=binding.id)
    assert saved.token == "encrypted" and saved.purpose == "agent"
    assert saved.poll_next_at <= utcnow()
    assert saved.agent_recovery_at <= utcnow()
    assert saved.poll_claim is None and saved.poll_claim_expires_at is None
