"""
Unit Tests for the custom `database` tool.

Covers the db_common guards plus per-database execution through
execute_database_tool (the single LLM-facing entry point), including the
tool-config -> driver parameter normalization (config stores `username`,
drivers require `user`).
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.llm.tools.builtin.db_common import validate_readonly_sql, sanitize_value
from app.llm.tools.builtin.db_executor import (
    execute_database_tool,
    test_database_connection as run_test_connection,
)
from app.llm.tools.builtin.mongo_db import (
    _get_mongo_client_and_db,
    _infer_schema_from_docs,
)


def _db_tool(db_type: str, **config):
    """Fake Tool row carrying the persisted database_config payload."""
    tool = MagicMock()
    tool.name = f"{db_type}_tool"
    tool.database_config = {"db_type": db_type, **config}
    return tool


# ==================== db_common tests ====================
def test_validate_readonly_sql():
    validate_readonly_sql("SELECT * FROM users")
    validate_readonly_sql("WITH temp AS (SELECT id FROM users) SELECT * FROM temp")
    validate_readonly_sql("EXPLAIN SELECT 1")
    validate_readonly_sql("SHOW TABLES")
    validate_readonly_sql("PRAGMA table_info('users')")

    with pytest.raises(ValueError, match="sql_empty"):
        validate_readonly_sql("")
    with pytest.raises(ValueError, match="multiple_statements_not_allowed"):
        validate_readonly_sql("SELECT 1; DROP TABLE users;")
    with pytest.raises(ValueError, match="disallowed_sql_statement_type"):
        validate_readonly_sql("INSERT INTO users VALUES (1)")
    with pytest.raises(ValueError, match="disallowed_sql_keyword"):
        validate_readonly_sql("SELECT * FROM users WHERE id IN (DELETE FROM users)")


def test_sanitize_value():
    from decimal import Decimal
    from uuid import uuid4
    import datetime

    uid = uuid4()
    now = datetime.datetime.now()
    assert sanitize_value("abc") == "abc"
    assert sanitize_value(123) == 123
    assert sanitize_value(Decimal("10.5")) == 10.5
    assert sanitize_value(uid) == str(uid)
    assert sanitize_value(now) == now.isoformat()
    assert sanitize_value(b"hello") == "hello"
    assert sanitize_value(b"\xff\xfe") == "<binary data: 2 bytes>"


# ==================== PostgreSQL ====================
@pytest.mark.asyncio
async def test_execute_postgresql_schema_and_query():
    schema_conn = AsyncMock()
    schema_conn.fetch.side_effect = [
        [{"table_name": "products"}],
        [
            {
                "column_name": "id",
                "data_type": "integer",
                "is_nullable": "NO",
                "column_default": None,
                "column_comment": "Primary Key",
            }
        ],
        [{"column_name": "id"}],
        [{"id": 1}],
    ]

    tool = _db_tool(
        "postgresql",
        host="10.0.0.1",
        port=5432,
        database="app_db",
        username="app_user",
        password="s3cret",
        max_limit=100,
    )

    with patch(
        "asyncpg.connect", new_callable=AsyncMock, return_value=schema_conn
    ) as connect:
        res_schema = await execute_database_tool(
            tool=tool,
            arguments={"action": "schema", "include_samples": True},
        )

    # config `username` must reach the driver as `user`
    assert connect.call_args.kwargs["user"] == "app_user"
    assert connect.call_args.kwargs["database"] == "app_db"
    assert connect.call_args.kwargs["host"] == "10.0.0.1"
    assert res_schema["success"] is True
    assert res_schema["tables"] == ["products"]
    assert (
        res_schema["selected_schemas"]["products"]["columns"][0]["primary_key"] is True
    )
    assert res_schema["selected_schemas"]["products"]["samples"] == [{"id": 1}]

    query_conn = MagicMock()
    query_conn.close = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    query_conn.transaction.return_value = tx
    query_conn.fetch = AsyncMock(return_value=[{"id": 1}, {"id": 2}, {"id": 3}])

    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=query_conn):
        res_query = await execute_database_tool(
            tool=tool,
            arguments={"action": "query", "sql": "SELECT id FROM products", "limit": 2},
        )

    assert res_query["success"] is True
    assert res_query["columns"] == ["id"]
    assert res_query["rows"] == [[1], [2]]
    assert res_query["truncated"] is True


@pytest.mark.asyncio
async def test_execute_postgresql_guards_and_edge_cases():
    tool = _db_tool("postgresql", host="localhost", username="app_user")

    with patch("asyncpg.connect", new_callable=AsyncMock) as connect:
        missing_sql = await execute_database_tool(
            tool=tool, arguments={"action": "query", "sql": "  "}
        )
        assert missing_sql == {"error": "sql_query_required", "success": False}

        bad_action = await execute_database_tool(
            tool=tool, arguments={"action": "drop-everything"}
        )
        assert bad_action["error"] == "unsupported_action: drop-everything"

        with pytest.raises(ValueError, match="disallowed_sql"):
            await execute_database_tool(
                tool=tool, arguments={"action": "query", "sql": "DROP TABLE users"}
            )

    connect.assert_not_called()

    # Schema with include_samples=False and empty tables
    schema_conn = AsyncMock()
    schema_conn.fetch.side_effect = [
        [{"table_name": "empty_table"}],
        [
            {
                "column_name": "id",
                "data_type": "int",
                "is_nullable": "YES",
                "column_default": None,
                "column_comment": None,
            }
        ],
        [],  # primary keys
    ]
    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=schema_conn):
        res = await execute_database_tool(
            tool=tool, arguments={"action": "schema", "include_samples": False}
        )
        assert res["selected_schemas"]["empty_table"]["samples"] is None

    # Query with pre-existing LIMIT in SQL and empty results
    empty_conn = MagicMock()
    empty_conn.close = AsyncMock()
    tx = MagicMock()
    tx.__aenter__ = AsyncMock()
    tx.__aexit__ = AsyncMock()
    empty_conn.transaction.return_value = tx
    empty_conn.fetch = AsyncMock(return_value=[])

    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=empty_conn):
        res = await execute_database_tool(
            tool=tool,
            arguments={"action": "query", "sql": "SELECT * FROM users LIMIT 10"},
        )
        assert res["rows"] == []
        assert res["columns"] == []
        assert res["truncated"] is False


# ==================== MySQL ====================
@pytest.mark.asyncio
async def test_execute_mysql_schema_and_query():
    schema_conn = MagicMock()
    schema_cursor = AsyncMock()
    schema_cursor.__aenter__.return_value = schema_cursor
    schema_cursor.__aexit__.return_value = None
    schema_cursor.fetchall.side_effect = [
        [{"table_name": "customers"}],
        [
            {
                "column_name": "id",
                "column_type": "int",
                "is_nullable": "NO",
                "column_key": "PRI",
                "column_default": None,
                "column_comment": "",
            }
        ],
        [{"id": 100}],
    ]
    schema_conn.cursor.return_value = schema_cursor

    tool = _db_tool(
        "mysql",
        host="db.internal",
        port=3306,
        database="shop_db",
        username="ro_user",
        password="pw",
    )

    with patch(
        "asyncmy.connect", new_callable=AsyncMock, return_value=schema_conn
    ) as connect:
        res_schema = await execute_database_tool(
            tool=tool, arguments={"action": "schema", "include_samples": True}
        )

    assert connect.call_args.kwargs["user"] == "ro_user"
    assert connect.call_args.kwargs["database"] == "shop_db"
    assert res_schema["success"] is True
    assert res_schema["tables"] == ["customers"]
    assert (
        res_schema["selected_schemas"]["customers"]["columns"][0]["primary_key"] is True
    )

    query_conn = MagicMock()
    query_cursor = AsyncMock()
    query_cursor.__aenter__.return_value = query_cursor
    query_cursor.__aexit__.return_value = None
    query_cursor.fetchall.return_value = [{"total": 1}, {"total": 2}, {"total": 3}]
    query_conn.cursor.return_value = query_cursor

    with patch("asyncmy.connect", new_callable=AsyncMock, return_value=query_conn):
        res_query = await execute_database_tool(
            tool=tool,
            arguments={
                "action": "query",
                "sql": "SELECT total FROM customers",
                "limit": 2,
            },
        )

    assert res_query["rows"] == [[1], [2]]
    assert res_query["truncated"] is True
    assert res_query["success"] is True


@pytest.mark.asyncio
async def test_execute_mysql_guards_and_edge_cases():
    tool = _db_tool("mysql", host="localhost", database="test")

    bad_act = await execute_database_tool(tool=tool, arguments={"action": "unknown"})
    assert bad_act["error"] == "unsupported_action: unknown"

    empty_sql = await execute_database_tool(
        tool=tool, arguments={"action": "query", "sql": "   "}
    )
    assert empty_sql["error"] == "sql_query_required"

    # Schema with include_samples=False
    schema_conn = MagicMock()
    schema_cursor = AsyncMock()
    schema_cursor.__aenter__.return_value = schema_cursor
    schema_cursor.__aexit__.return_value = None
    schema_cursor.fetchall.side_effect = [
        [{"table_name": "t1"}],
        [
            {
                "column_name": "id",
                "column_type": "int",
                "is_nullable": "YES",
                "column_key": "",
                "column_default": None,
                "column_comment": "",
            }
        ],
    ]
    schema_conn.cursor.return_value = schema_cursor
    with patch("asyncmy.connect", new_callable=AsyncMock, return_value=schema_conn):
        res = await execute_database_tool(
            tool=tool, arguments={"action": "schema", "include_samples": False}
        )
        assert res["selected_schemas"]["t1"]["samples"] is None

    # Query with pre-existing LIMIT in SQL and empty results
    query_conn = MagicMock()
    query_cursor = AsyncMock()
    query_cursor.__aenter__.return_value = query_cursor
    query_cursor.__aexit__.return_value = None
    query_cursor.fetchall.return_value = []
    query_conn.cursor.return_value = query_cursor

    with patch("asyncmy.connect", new_callable=AsyncMock, return_value=query_conn):
        res = await execute_database_tool(
            tool=tool, arguments={"action": "query", "sql": "SELECT * FROM t1 LIMIT 5"}
        )
        assert res["rows"] == []
        assert res["columns"] == []
        assert res["truncated"] is False


# ==================== Redis ====================
@pytest.mark.asyncio
async def test_execute_redis_scan_get_and_command():
    client = AsyncMock()
    client.scan.return_value = (0, ["user:1", "user:2"])
    client.type.return_value = "hash"
    client.ttl.return_value = 3600
    client.exists.return_value = 1
    client.hgetall.return_value = {"name": "Alice"}
    client.execute_command.return_value = 1

    tool = _db_tool("redis", host="redis.internal", port=6379, db=3)

    with (
        patch("redis.asyncio.Redis", return_value=client) as redis_cls,
        patch("redis.asyncio.from_url", return_value=client) as from_url,
    ):
        scan = await execute_database_tool(
            tool=tool, arguments={"action": "scan", "pattern": "user:*"}
        )
        assert scan["success"] is True
        assert [k["key"] for k in scan["keys"]] == ["user:1", "user:2"]
        assert scan["keys"][0]["type"] == "hash"

        get = await execute_database_tool(
            tool=tool, arguments={"action": "get", "key": "user:1"}
        )
        assert get["value"] == {"name": "Alice"}
        assert get["ttl_seconds"] == 3600

        allowed = await execute_database_tool(
            tool=tool,
            arguments={"action": "command", "key": "user:1", "command": "EXISTS"},
        )
        assert allowed["success"] is True

        write_cmd = await execute_database_tool(
            tool=tool,
            arguments={"action": "command", "key": "user:1", "command": "SET"},
        )
        assert write_cmd["success"] is False
        assert write_cmd["error"] == "command_not_permitted: SET"

        dangerous = await execute_database_tool(
            tool=tool,
            arguments={"action": "command", "key": "*", "command": "FLUSHALL"},
        )
        assert dangerous["error"] == "dangerous_command_blocked: FLUSHALL"

        missing_key = await execute_database_tool(
            tool=tool, arguments={"action": "get"}
        )
        assert missing_key["error"] == "key_required"

    from_url.assert_not_called()
    assert redis_cls.call_args.kwargs["db"] == 3
    assert redis_cls.call_args.kwargs["host"] == "redis.internal"
    assert client.aclose.await_count == 6


@pytest.mark.asyncio
async def test_execute_redis_branch_coverage():
    client = AsyncMock()
    # 1. Scan with cursor pagination: first call returns cursor=5, second returns cursor=0
    client.scan.side_effect = [
        (5, ["k1"]),
        (0, ["k2"]),
    ]
    client.type.return_value = "string"
    client.ttl.return_value = 100

    tool = _db_tool("redis")
    with patch("redis.asyncio.Redis", return_value=client):
        res = await execute_database_tool(
            tool=tool, arguments={"action": "scan", "count": 10}
        )
        assert res["total_found"] == 2

        # 2. Get non-existent key
        client.exists.return_value = 0
        res = await execute_database_tool(
            tool=tool, arguments={"action": "get", "key": "nonexistent"}
        )
        assert res["exists"] is False

        # 3. Get key of type "string"
        client.exists.return_value = 1
        client.type.return_value = "string"
        client.get.return_value = "val1"
        res = await execute_database_tool(
            tool=tool, arguments={"action": "get", "key": "strkey"}
        )
        assert res["value"] == "val1"

        # 4. Get key of type "list"
        client.type.return_value = "list"
        client.lrange.return_value = ["item1", "item2"]
        res = await execute_database_tool(
            tool=tool, arguments={"action": "get", "key": "listkey"}
        )
        assert res["value"] == ["item1", "item2"]

        # 5. Get key of type "set"
        client.type.return_value = "set"
        client.smembers.return_value = {"s1", "s2"}
        res = await execute_database_tool(
            tool=tool, arguments={"action": "get", "key": "setkey"}
        )
        assert sorted(res["value"]) == ["s1", "s2"]

        # 6. Get key of type "zset"
        client.type.return_value = "zset"
        client.zrange.return_value = [("z1", 1.0)]
        res = await execute_database_tool(
            tool=tool, arguments={"action": "get", "key": "zsetkey"}
        )
        assert res["value"] == [["z1", 1.0]]

        # 7. Command missing command or key
        res = await execute_database_tool(
            tool=tool, arguments={"action": "command", "key": "k", "command": ""}
        )
        assert res["error"] == "command_and_key_required"
        res = await execute_database_tool(
            tool=tool, arguments={"action": "command", "key": "", "command": "PING"}
        )
        assert res["error"] == "command_and_key_required"

        # 8. Unsupported action
        res = await execute_database_tool(tool=tool, arguments={"action": "bad_act"})
        assert res["error"] == "unsupported_action: bad_act"


@pytest.mark.asyncio
async def test_execute_redis_uses_connection_url():
    url_client = AsyncMock()
    url_client.scan.return_value = (0, [])
    host_client = AsyncMock()

    tool = _db_tool("redis", url="redis://:pw@cache.internal:6380/1", host="ignored")

    with (
        patch("redis.asyncio.from_url", return_value=url_client) as from_url,
        patch("redis.asyncio.Redis", return_value=host_client) as redis_cls,
    ):
        res = await execute_database_tool(tool=tool, arguments={"action": "scan"})

    assert res["success"] is True
    from_url.assert_called_once_with(
        "redis://:pw@cache.internal:6380/1", decode_responses=True
    )
    redis_cls.assert_not_called()
    url_client.scan.assert_awaited()


# ==================== MongoDB ====================
def test_infer_schema_from_docs():
    docs = [
        {
            "name": "Alice",
            "age": 30,
            "tags": ["admin"],
            "meta": {"city": "SH"},
            "items": [{"id": 1}],
            "empty": [],
        },
    ]
    schema = _infer_schema_from_docs(docs)
    assert schema["name"] == "str"
    assert schema["age"] == "int"
    assert schema["tags"] == "array[str]"
    assert schema["meta"] == "object"
    assert schema["meta.city"] == "str"
    assert schema["items"] == "array[object]"
    assert schema["empty"] == "array[any]"


def test_mongo_client_with_credentials():
    with patch("motor.motor_asyncio.AsyncIOMotorClient") as mock_client:
        client, db = _get_mongo_client_and_db(
            {
                "host": "mongo.local",
                "port": 27018,
                "username": "admin",
                "password": "pass",
                "auth_source": "admin_db",
                "database": "my_db",
            }
        )
        mock_client.assert_called_once()
        uri = mock_client.call_args[0][0]
        assert "mongodb://admin:pass@mongo.local:27018/my_db?authSource=admin_db" in uri


@pytest.mark.asyncio
async def test_execute_mongodb_actions():
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=[{"_id": "1", "title": "Article 1"}])
    cursor.limit.return_value = cursor

    coll = MagicMock()
    coll.estimated_document_count = AsyncMock(return_value=50)
    coll.find.return_value = cursor
    coll.aggregate.return_value = cursor
    coll.count_documents = AsyncMock(return_value=1)

    db = MagicMock()
    db.name = "app_db"
    db.list_collection_names = AsyncMock(return_value=["articles", "users"])
    db.__getitem__.return_value = coll

    client = MagicMock()
    client.__getitem__.return_value = db

    tool = _db_tool(
        "mongodb", url="mongodb://u:p@mongo.internal:27017", database="app_db"
    )

    with patch(
        "motor.motor_asyncio.AsyncIOMotorClient", return_value=client
    ) as motor_cls:
        schema_all = await execute_database_tool(
            tool=tool, arguments={"action": "schema"}
        )
        assert schema_all["collections"] == [
            {"collection": "articles", "estimated_count": 50},
            {"collection": "users", "estimated_count": 50},
        ]

        schema_coll = await execute_database_tool(
            tool=tool, arguments={"action": "schema", "collection": "articles"}
        )
        assert schema_coll["fields_schema"]["title"] == "str"

        found = await execute_database_tool(
            tool=tool, arguments={"action": "find", "collection": "articles"}
        )
        assert found["count"] == 1
        assert found["results"][0]["title"] == "Article 1"

        counted = await execute_database_tool(
            tool=tool, arguments={"action": "count", "collection": "articles"}
        )
        assert counted["count"] == 1

        # Aggregate with existing $limit
        aggregated = await execute_database_tool(
            tool=tool,
            arguments={
                "action": "aggregate",
                "collection": "articles",
                "pipeline": [{"$match": {}}, {"$limit": 5}],
            },
        )
        assert aggregated["success"] is True

        blocked = await execute_database_tool(
            tool=tool,
            arguments={
                "action": "aggregate",
                "collection": "articles",
                "pipeline": [{"$out": "leak"}],
            },
        )
        assert blocked["error"] == "aggregation_stage_not_permitted: $out"

        # Missing collection guards
        assert (await execute_database_tool(tool=tool, arguments={"action": "find"}))[
            "error"
        ] == "collection_required"
        assert (await execute_database_tool(tool=tool, arguments={"action": "count"}))[
            "error"
        ] == "collection_required"
        assert (
            await execute_database_tool(tool=tool, arguments={"action": "aggregate"})
        )["error"] == "collection_required"

        # Unsupported action
        assert (
            await execute_database_tool(tool=tool, arguments={"action": "drop_coll"})
        )["error"] == "unsupported_action: drop_coll"

    assert motor_cls.call_args.args[0] == "mongodb://u:p@mongo.internal:27017"
    client.close.assert_called()


# ==================== test_database_connection ====================
@pytest.mark.asyncio
async def test_database_connection_mongodb_and_unsupported():
    db = AsyncMock()
    db.command.return_value = {"ok": 1}
    client = MagicMock()
    client.__getitem__.return_value = db

    with (
        patch(
            "app.llm.tools.builtin.db_executor._get_mongo_client_and_db",
            return_value=(client, db),
        ),
        patch(
            "app.llm.tools.builtin.db_executor.validate_database_config",
            return_value=None,
        ),
    ):
        res = await run_test_connection(
            {"db_type": "mongodb", "url": "mongodb://localhost:27017"}
        )
        assert res["success"] is True
        assert res["message"] == "MongoDB connection successful"
    with patch(
        "app.llm.tools.builtin.db_executor.validate_database_config", return_value=None
    ):
        unsupported = await run_test_connection({"db_type": "couchdb"})
        assert unsupported["success"] is False
        assert "unsupported_db_type" in unsupported["error"]

    with (
        patch(
            "app.llm.tools.builtin.db_executor._get_mongo_client_and_db",
            side_effect=Exception("connection refused"),
        ),
        patch(
            "app.llm.tools.builtin.db_executor.validate_database_config",
            return_value=None,
        ),
    ):
        err = await run_test_connection({"db_type": "mongodb", "host": "1.1.1.1"})
        assert err["success"] is False
        assert "connection refused" in err["error"]


# ==================== dispatch ====================
@pytest.mark.asyncio
async def test_execute_database_tool_unsupported_type():
    res = await execute_database_tool(
        tool=_db_tool("cassandra", host="localhost"), arguments={"action": "schema"}
    )
    assert res == {"error": "unsupported_database_type: cassandra", "success": False}


@pytest.mark.asyncio
async def test_execute_postgresql_and_mysql_uses_url():
    # PostgreSQL via URL
    pg_conn = MagicMock()
    pg_conn.close = AsyncMock()
    pg_tx = MagicMock()
    pg_tx.__aenter__ = AsyncMock()
    pg_tx.__aexit__ = AsyncMock()
    pg_conn.transaction.return_value = pg_tx
    pg_conn.fetch = AsyncMock(return_value=[{"id": 1}])

    pg_tool = _db_tool(
        "postgresql", url="postgresql://pguser:pgpass%40123@pg.host.net:5433/pg_db"
    )
    with patch(
        "asyncpg.connect", new_callable=AsyncMock, return_value=pg_conn
    ) as pg_connect:
        res = await execute_database_tool(
            pg_tool, {"action": "query", "sql": "SELECT 1"}
        )
        assert res["success"] is True
        assert pg_connect.call_args.kwargs["user"] == "pguser"
        assert pg_connect.call_args.kwargs["password"] == "pgpass@123"
        assert pg_connect.call_args.kwargs["host"] == "pg.host.net"
        assert pg_connect.call_args.kwargs["port"] == 5433
        assert pg_connect.call_args.kwargs["database"] == "pg_db"

    # MySQL via URL
    my_conn = MagicMock()
    my_cursor = AsyncMock()
    my_cursor.__aenter__.return_value = my_cursor
    my_cursor.__aexit__.return_value = None
    my_cursor.fetchall.return_value = [{"val": 42}]
    my_conn.cursor.return_value = my_cursor

    my_tool = _db_tool("mysql", url="mysql://myuser:mypass@my.host.net:3307/shop_db")
    with patch(
        "asyncmy.connect", new_callable=AsyncMock, return_value=my_conn
    ) as my_connect:
        res = await execute_database_tool(
            my_tool, {"action": "query", "sql": "SELECT 1"}
        )
        assert res["success"] is True
        assert my_connect.call_args.kwargs["user"] == "myuser"
        assert my_connect.call_args.kwargs["password"] == "mypass"
        assert my_connect.call_args.kwargs["host"] == "my.host.net"
        assert my_connect.call_args.kwargs["port"] == 3307
        assert my_connect.call_args.kwargs["database"] == "shop_db"


def test_parse_pg_and_mysql_minimal_url_branches():
    from app.llm.tools.builtin.postgresql import _parse_pg_config
    from app.llm.tools.builtin.mysql_db import _parse_mysql_config

    # Bare URL without username, password, port, or path
    pg_cfg = _parse_pg_config({"url": "postgresql://myhost"})
    assert pg_cfg["host"] == "myhost"
    assert pg_cfg["port"] == 5432
    assert pg_cfg["user"] == ""
    assert pg_cfg["password"] == ""
    assert pg_cfg["database"] == ""

    my_cfg = _parse_mysql_config({"url": "mysql://myhost"})
    assert my_cfg["host"] == "myhost"
    assert my_cfg["port"] == 3306
    assert my_cfg["user"] == ""
    assert my_cfg["password"] == ""
    assert my_cfg["database"] == ""


@pytest.mark.asyncio
async def test_pg_and_mysql_schema_empty_samples():
    # PostgreSQL schema with table but s_rows returning []
    pg_conn = AsyncMock()
    pg_conn.fetch.side_effect = [
        [{"table_name": "empty_table"}],
        [
            {
                "column_name": "id",
                "data_type": "int",
                "is_nullable": "NO",
                "column_default": None,
                "column_comment": None,
            }
        ],
        [],  # primary key
        [],  # s_rows is empty
    ]
    tool_pg = _db_tool("postgresql")
    with patch("asyncpg.connect", new_callable=AsyncMock, return_value=pg_conn):
        res = await execute_database_tool(
            tool_pg, {"action": "schema", "include_samples": True}
        )
        assert res["selected_schemas"]["empty_table"]["samples"] == []

    # MySQL schema with table but s_rows returning []
    my_conn = MagicMock()
    my_cursor = AsyncMock()
    my_cursor.__aenter__.return_value = my_cursor
    my_cursor.__aexit__.return_value = None
    my_cursor.fetchall.side_effect = [
        [{"table_name": "empty_table"}],
        [
            {
                "column_name": "id",
                "column_type": "int",
                "is_nullable": "NO",
                "column_key": "",
                "column_default": None,
                "column_comment": "",
            }
        ],
        [],  # s_rows is empty
    ]
    my_conn.cursor.return_value = my_cursor
    tool_my = _db_tool("mysql")
    with patch("asyncmy.connect", new_callable=AsyncMock, return_value=my_conn):
        res = await execute_database_tool(
            tool_my, {"action": "schema", "include_samples": True}
        )
        assert res["selected_schemas"]["empty_table"]["samples"] == []
