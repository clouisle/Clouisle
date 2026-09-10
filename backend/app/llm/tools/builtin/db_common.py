"""
数据库连接与安全工具通用基础模块

包含：
1. SQL 只读静态语法与危险指令拦截 (AST / Keyword checking)
2. 基础连接配置校验与脱敏
3. 结果序列化（JSON 友好转换，如 UUID, datetime, bytes, Decimal 等）
"""

import datetime
from decimal import Decimal
import re
from typing import Any
from uuid import UUID


# 禁止在只读模式下执行的 SQL 关键字模式 (全词匹配)
_DISALLOWED_SQL_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "REPLACE",
    "GRANT",
    "REVOKE",
    "LOCK",
    "UNLOCK",
    "CALL",
    "EXEC",
    "EXECUTE",
    "MERGE",
}

# 匹配 SQL 语句开头的词（去除前置注释和空白）
_SQL_COMMENT_RE = re.compile(r"(\/\*.*?\*\/|--[^\r\n]*$)", re.MULTILINE | re.DOTALL)


def validate_readonly_sql(sql: str) -> None:
    """
    检查 SQL 语句是否为安全的只读查询语句 (仅允许 SELECT / WITH ... SELECT / EXPLAIN 等)。
    若发现破坏性关键字或非只读开头的指令，抛出 ValueError。
    """
    if not sql or not sql.strip():
        raise ValueError("sql_empty")

    # 去除注释
    cleaned_sql = _SQL_COMMENT_RE.sub("", sql).strip()
    if not cleaned_sql:
        raise ValueError("sql_empty")

    # 检查是否包含多条语句（防止 SQL 注入中注入分号执行多条语句）
    statements = [stmt.strip() for stmt in cleaned_sql.split(";") if stmt.strip()]
    if len(statements) > 1:
        raise ValueError("multiple_statements_not_allowed")

    statement = statements[0]

    # 提取开头的操作词
    first_token_match = re.match(r"^([a-zA-Z]+)", statement)
    if not first_token_match:
        raise ValueError("invalid_sql_syntax")

    first_token = first_token_match.group(1).upper()
    allowed_first_tokens = {
        "SELECT",
        "WITH",
        "EXPLAIN",
        "SHOW",
        "DESCRIBE",
        "DESC",
        "PRAGMA",
    }
    if first_token not in allowed_first_tokens:
        raise ValueError(f"disallowed_sql_statement_type: {first_token}")

    # 提取所有的词，检查是否包含禁用的写关键字
    tokens = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", statement.upper()))
    intersection = tokens & _DISALLOWED_SQL_KEYWORDS
    if intersection:
        raise ValueError(f"disallowed_sql_keyword: {', '.join(sorted(intersection))}")


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
