"""
Unit Tests for Custom Database Tool Execution & Connection Testing
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.llm.tools.builtin.db_executor import (
    test_database_connection as check_db_conn,
    execute_database_tool,
)
from app.models.tool import Tool, CustomToolType


@pytest.mark.asyncio
async def test_database_connection_pg_mocked():
    mock_conn = MagicMock()
    mock_conn.close = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"ok": 1})

    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn):
        res = await check_db_conn(
            {
                "db_type": "postgresql",
                "host": "localhost",
                "port": 5432,
                "database": "test",
                "username": "u",
                "password": "p",
            }
        )
        assert res["success"] is True
        assert res["ping"] == 1


@pytest.mark.asyncio
async def test_database_connection_mysql_mocked():
    mock_conn = MagicMock()
    mock_cursor = AsyncMock()
    mock_cursor.__aenter__.return_value = mock_cursor
    mock_cursor.__aexit__.return_value = None
    mock_cursor.fetchone.return_value = [1]
    mock_conn.cursor.return_value = mock_cursor

    with patch("asyncmy.connect", new_callable=AsyncMock, return_value=mock_conn):
        res = await check_db_conn(
            {
                "db_type": "mysql",
                "host": "localhost",
                "port": 3306,
                "database": "test",
                "username": "u",
                "password": "p",
            }
        )
        assert res["success"] is True
        assert res["ping"] == 1


@pytest.mark.asyncio
async def test_database_connection_redis_mocked():
    mock_client = AsyncMock()
    mock_client.ping.return_value = "PONG"

    with (
        patch("redis.asyncio.Redis", return_value=mock_client),
        patch("redis.asyncio.from_url", return_value=mock_client),
    ):
        res = await check_db_conn(
            {
                "db_type": "redis",
                "host": "localhost",
                "port": 6379,
            }
        )
        assert res["success"] is True
        assert res["ping"] == "PONG"


@pytest.mark.asyncio
async def test_database_connection_mongo_mocked():
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_db.command = AsyncMock(return_value={"ok": 1.0})
    mock_client.__getitem__.return_value = mock_db

    with patch("motor.motor_asyncio.AsyncIOMotorClient", return_value=mock_client):
        res = await check_db_conn(
            {
                "db_type": "mongodb",
                "host": "localhost",
                "port": 27017,
                "database": "test",
            }
        )
        assert res["success"] is True


@pytest.mark.asyncio
async def test_execute_database_tool_pg_mocked():
    tool = MagicMock(spec=Tool)
    tool.name = "company_pg_db"
    tool.custom_type = CustomToolType.DATABASE
    tool.database_config = {
        "db_type": "postgresql",
        "host": "localhost",
        "port": 5432,
    }

    with (
        patch(
            "app.llm.tools.builtin.db_executor._pg_schema", new_callable=AsyncMock
        ) as mock_schema,
        patch(
            "app.llm.tools.builtin.db_executor._pg_query", new_callable=AsyncMock
        ) as mock_query,
    ):
        mock_schema.return_value = {"tables": ["users"], "success": True}
        mock_query.return_value = {"columns": ["id"], "rows": [[1]], "success": True}

        # 1. Schema
        res_schema = await execute_database_tool(
            tool=tool,
            arguments={"action": "schema"},
        )
        assert res_schema["success"] is True

        # 2. Query
        res_query = await execute_database_tool(
            tool=tool,
            arguments={"action": "query", "sql": "SELECT 1"},
        )
        assert res_query["success"] is True

        # 3. Action = query with dangerous SQL
        with pytest.raises(ValueError, match="disallowed_sql"):
            await execute_database_tool(
                tool=tool,
                arguments={"action": "query", "sql": "DROP TABLE users"},
            )
