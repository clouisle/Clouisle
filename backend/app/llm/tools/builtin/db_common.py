"""
数据库连接与安全工具通用基础模块

包含：
1. SQL 只读语法分析与危险语句拦截 (dialect-aware AST validation)
2. 基础连接配置校验与脱敏
3. 结果序列化（JSON 友好转换，如 UUID, datetime, bytes, Decimal 等）
"""

import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError


_READONLY_SQL_MAX_LENGTH = 65_536
_READONLY_ROOT_TYPES = (
    exp.Query,
    exp.Show,
    exp.Describe,
    exp.Pragma,
)

_READONLY_SQL_STARTS = {"SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "PRAGMA"}
_EXPLAIN_OPTIONS = {
    "ANALYZE",
    "ANALYSE",
    "VERBOSE",
    "COSTS",
    "SETTINGS",
    "BUFFERS",
    "WAL",
    "TIMING",
    "SUMMARY",
    "MEMORY",
    "SERIALIZE",
    "GENERIC_PLAN",
    "FORMAT",
    "TEXT",
    "BINARY",
    "NONE",
    "TRUE",
    "FALSE",
    "JSON",
    "XML",
    "YAML",
    "TRADITIONAL",
    "TREE",
}


def _skip_sql_trivia(sql: str, index: int) -> int:
    while index < len(sql):
        if sql[index].isspace():
            index += 1
        elif sql.startswith("--", index) or sql[index] == "#":
            newline = sql.find("\n", index)
            if newline == -1:
                return len(sql)
            index = newline + 1
        elif sql.startswith("/*", index):
            depth = 1
            index += 2
            while index < len(sql) and depth:
                if sql.startswith("/*", index):
                    depth += 1
                    index += 2
                elif sql.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                return len(sql)
        else:
            return index
    return index


def _extract_explained_query(sql: str) -> str:
    index = _skip_sql_trivia(sql, 0)
    if sql.startswith("(", index):
        end = sql.find(")", index + 1)
        if end == -1:
            raise ValueError("invalid_sql_syntax")
        options = sql[index + 1 : end].replace(",", " ").replace("=", " ").split()
        if any(option.upper() not in _EXPLAIN_OPTIONS for option in options):
            raise ValueError("invalid_sql_syntax")
        index = end + 1

    while index < len(sql):
        index = _skip_sql_trivia(sql, index)
        start = index
        while index < len(sql) and (sql[index].isalnum() or sql[index] == "_"):
            index += 1
        if start == index:
            raise ValueError("invalid_sql_syntax")
        word = sql[start:index].upper()
        if word in _READONLY_SQL_STARTS:
            return sql[start:]
        if word not in _EXPLAIN_OPTIONS:
            raise ValueError("invalid_sql_syntax")
        if word == "FORMAT":
            index = _skip_sql_trivia(sql, index)
            if index < len(sql) and sql[index] == "=":
                index += 1
    raise ValueError("invalid_sql_syntax")


def validate_readonly_sql(sql: str, dialect: str | None = None) -> None:
    """Allow one bounded read-only statement parsed for its target SQL dialect."""
    if not sql or not sql.strip():
        raise ValueError("sql_empty")
    if len(sql) > _READONLY_SQL_MAX_LENGTH:
        raise ValueError("sql_too_long")

    try:
        statements = [
            statement
            for statement in sqlglot.parse(sql, read=dialect)
            if statement is not None
        ]
    except (ParseError, TokenError) as exc:
        raise ValueError("invalid_sql_syntax") from exc
    if not statements:
        raise ValueError("sql_empty")
    if len(statements) > 1:
        raise ValueError("multiple_statements_not_allowed")

    statement = statements[0]
    if isinstance(statement, exp.Command) and statement.this.upper() == "EXPLAIN":
        explanation = statement.expression
        if not isinstance(explanation, exp.Literal) or not explanation.is_string:
            raise ValueError("invalid_sql_syntax")
        try:
            explained_statements = [
                item
                for item in sqlglot.parse(
                    _extract_explained_query(explanation.this), read=dialect
                )
                if item is not None
            ]
        except (ParseError, TokenError) as exc:
            raise ValueError("invalid_sql_syntax") from exc
        if len(explained_statements) != 1:
            raise ValueError("disallowed_sql_statement_type: EXPLAIN")
        statement = explained_statements[0]
    if isinstance(statement, exp.Command) and statement.this.upper() in {
        "SHOW",
        "DESCRIBE",
        "DESC",
    }:
        return

    if not isinstance(statement, _READONLY_ROOT_TYPES):
        raise ValueError(f"disallowed_sql_statement_type: {statement.key.upper()}")

    if any(
        isinstance(node, (exp.DML, exp.DDL, exp.Into, exp.Lock))
        for node in statement.walk()
    ):
        raise ValueError("disallowed_sql_keyword: write_operation")


def sanitize_value(val: Any) -> Any:
    """将特殊类型安全转化为 JSON 可序列化类型"""
    if val is None:
        return None
    if isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val) if val.as_tuple().exponent != 0 else int(val)
    if isinstance(val, UUID):
        return str(val)
    if isinstance(val, (bytes, bytearray, memoryview)):
        try:
            return bytes(val).decode("utf-8")
        except UnicodeDecodeError:
            return f"<binary data: {len(val)} bytes>"
    if isinstance(val, (list, tuple, set)):
        return [sanitize_value(item) for item in val]
    if isinstance(val, dict):
        return {str(k): sanitize_value(v) for k, v in val.items()}
    # 兼容 MongoDB ObjectId
    if hasattr(val, "__class__") and val.__class__.__name__ == "ObjectId":
        return str(val)
    return str(val)
