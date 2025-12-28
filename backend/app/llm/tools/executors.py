"""
共享的工具执行函数

提供 HTTP 工具和代码工具的执行功能，供 API 端点复用。
"""

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def execute_http_tool(
    http_config: dict,
    arguments: dict[str, Any],
    credentials: dict[str, str] | None = None,
) -> dict:
    """
    执行 HTTP 工具

    Args:
        http_config: HTTP 配置（url, method, headers, etc.）
        arguments: 工具参数
        credentials: 凭证信息（可选）

    Returns:
        dict: 执行结果，包含 success, status_code, result/error 字段
    """

    def replace_vars(text: str, vars_dict: dict) -> str:
        """替换模板变量 {{var}}"""
        for key, value in vars_dict.items():
            text = text.replace(f"{{{{{key}}}}}", str(value))
        return text

    # 合并参数和凭证
    all_vars = {**arguments}
    if credentials:
        all_vars.update(credentials)

    url = replace_vars(http_config.get("url", ""), all_vars)
    method = http_config.get("method", "GET").upper()
    timeout = http_config.get("timeout", 30)

    headers = {
        k: replace_vars(v, all_vars) for k, v in http_config.get("headers", {}).items()
    }

    query_params = {
        k: replace_vars(str(v), all_vars)
        for k, v in http_config.get("query_params", {}).items()
    }

    body = None
    body_template = http_config.get("body_template")
    if body_template and method in ["POST", "PUT", "PATCH"]:
        body_str = replace_vars(body_template, all_vars)
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            body = body_str

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                params=query_params,
                json=body if isinstance(body, dict) else None,
                content=body if isinstance(body, str) else None,
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
