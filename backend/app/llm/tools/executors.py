"""
共享的工具执行函数

提供 HTTP 工具和代码工具的执行功能，供 API 端点复用。
"""

import json
import logging
import re
import mimetypes
from base64 import b64decode
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _render_text_template(template: str, variables: dict[str, Any]) -> str:
    """Render plain-text templates such as URLs, headers and query params."""
    result = template
    for key, value in variables.items():
        if value is None:
            replacement = ""
        elif isinstance(value, (dict, list)):
            replacement = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, bool):
            replacement = "true" if value else "false"
        else:
            replacement = str(value)

        pattern = re.compile(r"\{\{\s*" + re.escape(key) + r"\s*\}\}")
        result = pattern.sub(lambda _: replacement, result)
    return result


def _render_json_template(template: str, variables: dict[str, Any]) -> str:
    """
    Render JSON templates while preserving native JSON types.

    Examples:
    - {"data": "{{meta}}"} + meta=dict -> {"data": {...}}
    - {"count": "{{count}}"} + count=1 -> {"count": 1}
    - {"title": "{{title}}"} + title="x" -> {"title": "x"}
    """
    result = template

    for key, value in variables.items():
        json_value = json.dumps(value, ensure_ascii=False)

        # If the placeholder occupies the entire JSON string value, replace the
        # quoted token so objects/arrays/bools/numbers remain typed JSON values.
        quoted_pattern = re.compile(r'"\{\{\s*' + re.escape(key) + r'\s*\}\}"')
        result = quoted_pattern.sub(lambda _: json_value, result)

        # Fallback replacement for unquoted placeholders.
        if isinstance(value, str):
            replacement = json.dumps(value, ensure_ascii=False)[1:-1]
        elif value is None:
            replacement = "null"
        else:
            replacement = json_value

        raw_pattern = re.compile(r"\{\{\s*" + re.escape(key) + r"\s*\}\}")
        result = raw_pattern.sub(lambda _: replacement, result)

    return result


def _extract_placeholder_name(value: str | None) -> str | None:
    """Return the placeholder name when the whole string is exactly {{name}}."""
    if not value:
        return None
    match = re.fullmatch(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}", value)
    return match.group(1) if match else None


def _guess_filename(
    field_name: str, mime_type: str | None, source_url: str | None = None
) -> str:
    """Build a reasonable filename for uploaded multipart assets."""
    if source_url:
        tail = source_url.rstrip("/").rsplit("/", 1)[-1]
        if tail and "." in tail:
            return tail

    extension = mimetypes.guess_extension(mime_type or "") or ""
    if not extension and mime_type == "image/jpeg":
        extension = ".jpg"
    return f"{field_name}{extension or '.bin'}"


def _parse_data_url(value: str) -> tuple[bytes, str | None]:
    """Decode a data URL into bytes and content type."""
    match = re.fullmatch(r"data:([^;,]+)?;base64,(.*)", value, re.DOTALL)
    if not match:
        raise ValueError("Invalid data URL")
    mime_type = match.group(1) or "application/octet-stream"
    return b64decode(match.group(2)), mime_type


async def _normalize_file_upload_value(
    value: Any,
    field_name: str,
    timeout: float,
) -> list[tuple[str, tuple[str, bytes, str]]]:
    """Normalize file/image variables into httpx multipart file tuples."""
    if value is None:
        return []

    if isinstance(value, list):
        uploads: list[tuple[str, tuple[str, bytes, str]]] = []
        for item in value:
            uploads.extend(
                await _normalize_file_upload_value(item, field_name, timeout)
            )
        return uploads

    filename: str | None = None
    mime_type: str | None = None
    source_url: str | None = None
    raw_value = value

    if isinstance(value, dict):
        source_url = value.get("url")
        filename = value.get("filename") or value.get("name")
        mime_type = value.get("mime_type") or value.get("mimeType")
        raw_value = source_url or value.get("content") or value.get("data")

    if not isinstance(raw_value, str):
        raise ValueError(f"Unsupported file value for field '{field_name}'")

    if raw_value.startswith("data:"):
        content, detected_mime = _parse_data_url(raw_value)
        mime_type = mime_type or detected_mime
    elif raw_value.startswith("http://") or raw_value.startswith("https://"):
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(raw_value)
            response.raise_for_status()
            content = response.content
            mime_type = (
                mime_type
                or response.headers.get("content-type", "").split(";", 1)[0].strip()
                or None
            )
            source_url = raw_value
    else:
        raise ValueError(
            f"Unsupported file/image value for field '{field_name}'. Expected data URL or http(s) URL."
        )

    resolved_filename = filename or _guess_filename(field_name, mime_type, source_url)
    resolved_mime = mime_type or "application/octet-stream"
    return [(field_name, (resolved_filename, content, resolved_mime))]


async def _build_request_payload(
    http_config: dict[str, Any],
    variables: dict[str, Any],
    method: str,
    timeout: float,
) -> tuple[Any, dict[str, Any]]:
    """Build request body/files kwargs based on configured content type."""
    extra_kwargs: dict[str, Any] = {}
    content_type = http_config.get("content_type", "application/json")

    if method not in ["POST", "PUT", "PATCH"]:
        return None, extra_kwargs

    if content_type == "multipart/form-data":
        form_data: dict[str, str] = {}
        files: list[tuple[str, tuple[str, bytes, str]]] = []

        for field in http_config.get("form_fields", []) or []:
            field_name = field.get("name")
            if not field_name:
                continue

            field_value_template = field.get("value", "")
            placeholder_name = _extract_placeholder_name(field_value_template)
            raw_value = (
                variables.get(placeholder_name)
                if placeholder_name
                else _render_text_template(field_value_template, variables)
            )

            if field.get("type") == "file":
                files.extend(
                    await _normalize_file_upload_value(
                        raw_value,
                        field_name=field_name,
                        timeout=timeout,
                    )
                )
            else:
                if raw_value is None:
                    continue
                if isinstance(raw_value, (dict, list)):
                    form_data[field_name] = json.dumps(raw_value, ensure_ascii=False)
                elif isinstance(raw_value, bool):
                    form_data[field_name] = "true" if raw_value else "false"
                else:
                    form_data[field_name] = str(raw_value)

        extra_kwargs["data"] = form_data
        extra_kwargs["files"] = files
        return None, extra_kwargs

    body_template = http_config.get("body_template")
    if not body_template:
        return None, extra_kwargs

    if content_type == "application/x-www-form-urlencoded":
        body_str = _render_json_template(body_template, variables)
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            body = body_str

        if isinstance(body, dict):
            extra_kwargs["data"] = {
                key: json.dumps(val, ensure_ascii=False)
                if isinstance(val, (dict, list))
                else (
                    "true"
                    if val is True
                    else "false"
                    if val is False
                    else ""
                    if val is None
                    else str(val)
                )
                for key, val in body.items()
            }
            return None, extra_kwargs
        return body, extra_kwargs

    body_str = _render_json_template(body_template, variables)
    try:
        body = json.loads(body_str)
    except json.JSONDecodeError:
        body = body_str
    return body, extra_kwargs


async def execute_http_tool(
    http_config: dict,
    arguments: dict[str, Any],
    credentials: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> dict:
    """
    执行 HTTP 工具

    Args:
        http_config: HTTP 配置（url, method, headers, etc.）
        arguments: 工具参数
        credentials: 凭证信息（可选）
        timeout: Request timeout in seconds

    Returns:
        dict: 执行结果，包含 success, status_code, result/error 字段
    """

    # 合并参数和凭证
    all_vars = {**arguments}
    if credentials:
        all_vars.update(credentials)

    url = _render_text_template(http_config.get("url", ""), all_vars)
    method = http_config.get("method", "GET").upper()

    headers = {
        k: _render_text_template(v, all_vars)
        for k, v in http_config.get("headers", {}).items()
    }

    query_params = {
        k: _render_text_template(str(v), all_vars)
        for k, v in http_config.get("query_params", {}).items()
    }

    body, extra_request_kwargs = await _build_request_payload(
        http_config=http_config,
        variables=all_vars,
        method=method,
        timeout=timeout,
    )

    if http_config.get("content_type") == "multipart/form-data":
        headers.pop("Content-Type", None)
        headers.pop("content-type", None)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=query_params,
                json=body if body is not None and not isinstance(body, str) else None,
                content=body if isinstance(body, str) else None,
                **extra_request_kwargs,
            )

            try:
                result = response.json()
            except Exception:
                result = response.text

            # 提取指定路径的数据
            response_path = http_config.get("response_path")
            if response_path and isinstance(result, dict):
                for key in response_path.split("."):
                    if isinstance(result, dict) and key in result:
                        result = result[key]
                    else:
                        break

            return {
                "success": response.is_success,
                "status_code": response.status_code,
                "result": result,
            }

    except httpx.TimeoutException:
        return {"success": False, "error": "Request timeout"}
    except Exception as e:
        logger.exception(f"HTTP tool execution error: {e}")
        return {"success": False, "error": str(e)}


def format_http_result_for_llm(result: dict) -> str:
    """
    将 HTTP 工具执行结果格式化为 LLM 可读的字符串

    Args:
        result: execute_http_tool 的返回结果

    Returns:
        str: JSON 格式的结果字符串
    """
    if result.get("success"):
        return json.dumps(result.get("result", {}), ensure_ascii=False)
    else:
        return json.dumps(
            {
                "error": result.get("error", "Unknown error"),
                "status_code": result.get("status_code"),
            },
            ensure_ascii=False,
        )
