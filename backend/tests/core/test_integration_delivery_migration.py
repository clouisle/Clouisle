"""Cutover from provider delivery tables to the shared outbound queue."""

import pytest
import pytest_asyncio
from tortoise import Tortoise
from tortoise.context import TortoiseContext

from app.core.integration_delivery_migration import migrate_integration_deliveries


@pytest_asyncio.fixture
async def database():
    async with TortoiseContext() as context:
        await context.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await context.generate_schemas()
        yield context


async def _legacy_tables(connection) -> None:
    for table in (
        "feishu_agent_receipts",
        "wechat_agent_receipts",
    ):
        await connection.execute_query(f"DROP TABLE IF EXISTS {table}")
    await connection.execute_query(
        """
        CREATE TABLE feishu_agent_receipts (
            id CHAR(36) PRIMARY KEY,
            integration_id CHAR(36),
            user_id CHAR(36),
            agent_id CHAR(36),
            run_id CHAR(36),
            chat_id VARCHAR(128),
            message_id VARCHAR(128)
        )
        """
    )
    await connection.execute_query(
        """
        CREATE TABLE feishu_agent_deliveries (
            id CHAR(36) PRIMARY KEY,
            receipt_id CHAR(36) NOT NULL,
            event_key VARCHAR(255) NOT NULL,
            sequence INT NOT NULL,
            uuid VARCHAR(50) NOT NULL UNIQUE,
            text TEXT NOT NULL DEFAULT '',
            kind VARCHAR(20) NOT NULL DEFAULT 'text',
            asset_id CHAR(36),
            filename VARCHAR(500),
            content_type VARCHAR(255),
            size BIGINT,
            media_type VARCHAR(20),
            media_key VARCHAR(255),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            error VARCHAR(100),
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    await connection.execute_query(
        """
        CREATE TABLE wechat_agent_receipts (
            id CHAR(36) PRIMARY KEY,
            user_id CHAR(36),
            agent_id CHAR(36),
            run_id CHAR(36),
            binding_id CHAR(36),
            message_id VARCHAR(128)
        )
        """
    )
    await connection.execute_query(
        """
        CREATE TABLE wechat_agent_deliveries (
            id CHAR(36) PRIMARY KEY,
            receipt_id CHAR(36) NOT NULL,
            event_key VARCHAR(255) NOT NULL,
            sequence INT NOT NULL,
            payload TEXT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            error TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )


@pytest.mark.asyncio
async def test_legacy_rows_move_once_then_tables_are_dropped(database):
    connection = Tortoise.get_connection("default")
    await _legacy_tables(connection)
    await connection.execute_query(
        "INSERT INTO feishu_agent_receipts VALUES "
        "('r1', 'i1', 'u1', 'a1', 'run1', 'chat1', 'om1')"
    )
    await connection.execute_query(
        "INSERT INTO feishu_agent_deliveries VALUES "
        "('d1', 'r1', 'final-asset', 0, 'dedup-1', 'answer', 'asset', 'asset1', "
        "'report.pptx', 'application/x-pptx', 55, 'file', 'key1', 'sent', NULL, "
        "'2026-10-22 10:00:00', '2026-10-22 10:00:01')"
    )
    await connection.execute_query(
        "INSERT INTO wechat_agent_receipts VALUES "
        "('r2', 'u2', 'a2', 'run2', 'b2', 'wx-msg')"
    )
    await connection.execute_query(
        "INSERT INTO wechat_agent_deliveries VALUES "
        "('d2', 'r2', 'final', 0, "
        '\'{"kind": "text", "text": "hi"}\', '
        "'submitted', NULL, '2026-10-22 11:00:00', '2026-10-22 11:00:01')"
    )

    # Legacy rows carry identities that exist in production; the isolated
    # test database keeps only the fixture rows it asserts on.
    await connection.execute_query("PRAGMA foreign_keys = OFF")
    try:
        await migrate_integration_deliveries()
    finally:
        await connection.execute_query("PRAGMA foreign_keys = ON")

    rows = await connection.execute_query_dict(
        "SELECT provider_type, receipt_id, user_id, chat_id, message_id, kind, "
        "text, status, media_key, payload FROM integration_deliveries ORDER BY id"
    )
    assert [row["provider_type"] for row in rows] == ["feishu", "wechat"]
    feishu, wechat = rows
    assert feishu["receipt_id"] == "r1"
    assert feishu["user_id"] == "u1"
    assert feishu["chat_id"] == "chat1"
    assert feishu["media_key"] == "key1"
    assert feishu["status"] == "sent"
    assert wechat["chat_id"] == "b2"
    assert wechat["kind"] == "text"
    assert wechat["text"] == "hi"
    # WeChat's historical ``submitted`` is the same terminal state as ``sent``.
    assert wechat["status"] == "sent"

    for table in ("feishu_agent_deliveries", "wechat_agent_deliveries"):
        remaining = await connection.execute_query_dict(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [table]
        )
        assert remaining == []

    # A second startup must find no legacy table and add no duplicate row.
    await migrate_integration_deliveries()
    assert await connection.execute_query_dict(
        "SELECT COUNT(*) AS total FROM integration_deliveries"
    ) == [{"total": 2}]


@pytest.mark.asyncio
async def test_existing_queue_gains_error_detail_column(database):
    connection = Tortoise.get_connection("default")
    await connection.execute_query("DROP TABLE integration_deliveries")
    await connection.execute_query(
        """
        CREATE TABLE integration_deliveries (
            id CHAR(36) PRIMARY KEY,
            provider_type VARCHAR(32) NOT NULL,
            receipt_id CHAR(36) NOT NULL,
            event_key VARCHAR(255) NOT NULL,
            sequence INT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            error TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    await connection.execute_query(
        "INSERT INTO integration_deliveries "
        "(id, provider_type, receipt_id, event_key, sequence) "
        "VALUES ('d1', 'feishu', 'r1', 'final', 0)"
    )

    await migrate_integration_deliveries()

    columns = await connection.execute_query_dict(
        'PRAGMA table_info("integration_deliveries")'
    )
    assert "error_detail" in {row["name"] for row in columns}
    assert await connection.execute_query_dict(
        "SELECT error_detail FROM integration_deliveries WHERE id = 'd1'"
    ) == [{"error_detail": None}]

    await migrate_integration_deliveries()
    columns = await connection.execute_query_dict(
        'PRAGMA table_info("integration_deliveries")'
    )
    assert [row["name"] for row in columns].count("error_detail") == 1
