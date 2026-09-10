"""
MongoDB 数据库工具

功能: 连接 MongoDB 数据库，支持 schema (查看集合与字段结构)、find (文档过滤查询)、aggregate (聚合统计)、count (文档计数)。

实际执行入口为 db_executor.execute_database_tool（自定义 `database` 工具类型），凭证来自
工具的业务编排配置 (tools_config.database_config)，不暴露给 LLM 工具参数。
"""

from typing import Any

DISALLOWED_AGGREGATION_STAGES = {"$out", "$merge"}


def _get_mongo_client_and_db(db_config: dict[str, Any] | None):
    import motor.motor_asyncio

    config = dict(db_config or {})

    uri = config.get("url") or config.get("uri")
    db_name = config.get("database") or "test"

    if uri:
        client = motor.motor_asyncio.AsyncIOMotorClient(
            uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000
        )
    else:
        host = config.get("host") or "127.0.0.1"
        port = int(config.get("port") or 27017)
        user = config.get("username")
        password = config.get("password")
        auth_source = config.get("auth_source") or "admin"

        if user and password:
            uri = f"mongodb://{user}:{password}@{host}:{port}/{db_name}?authSource={auth_source}"
            client = motor.motor_asyncio.AsyncIOMotorClient(
                uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000
            )
        else:
            client = motor.motor_asyncio.AsyncIOMotorClient(
                host=host,
                port=port,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
            )

    return client, client[db_name]


def _infer_schema_from_docs(docs: list[dict[str, Any]]) -> dict[str, str]:
    fields_schema: dict[str, str] = {}

    def _walk(d: dict[str, Any], prefix: str = ""):
        for k, v in d.items():
            field_name = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                fields_schema[field_name] = "object"
                _walk(v, field_name)
            elif isinstance(v, list):
                if v and isinstance(v[0], dict):
                    fields_schema[field_name] = "array[object]"
                else:
                    elem_type = type(v[0]).__name__ if v else "any"
                    fields_schema[field_name] = f"array[{elem_type}]"
            else:
                fields_schema[field_name] = (
                    type(v).__name__ if v is not None else "null"
                )

    for doc in docs:
        _walk(doc)

    return fields_schema
