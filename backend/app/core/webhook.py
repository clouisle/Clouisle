"""
通用 Webhook 通知服务模块
支持自定义请求头、请求体模板和 HMAC 签名
"""

import logging
import hmac
import hashlib
import json
import re
from typing import Optional

import httpx

from app.models.site_setting import SiteSetting

logger = logging.getLogger(__name__)


async def get_webhook_config() -> dict:
    """获取 Webhook 配置"""
    return {
        "enabled": await SiteSetting.get_value("webhook_enabled", False),
        "url": await SiteSetting.get_value("webhook_url", ""),
        "method": await SiteSetting.get_value("webhook_method", "POST"),
        "headers": await SiteSetting.get_value("webhook_headers", {}),
        "body_template": await SiteSetting.get_value(
            "webhook_body_template",
            '{"title": "{{title}}", "content": "{{content}}", "link_url": "{{link_url}}"}',
        ),
        "secret": await SiteSetting.get_value("webhook_secret", ""),
    }


def _render_template(template: str, variables: dict) -> str:
    """
    渲染模板，替换 {{variable}} 占位符

    Args:
        template: 模板字符串
        variables: 变量字典

    Returns:
        渲染后的字符串
    """
    result = template
    for key, value in variables.items():
        # 转义 JSON 特殊字符
        if isinstance(value, str):
            escaped_value = json.dumps(value)[1:-1]  # 去掉首尾引号
        else:
            escaped_value = str(value) if value is not None else ""
        result = re.sub(r"\{\{\s*" + key + r"\s*\}\}", escaped_value, result)
    return result


def _generate_signature(secret: str, payload: str) -> str:
    """
    生成 HMAC-SHA256 签名

    Args:
        secret: 密钥
        payload: 请求体

    Returns:
        签名字符串 (hex)
    """
    return hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


async def send_webhook_notification(
    title: str,
    content: str,
    link_url: Optional[str] = None,
) -> bool:
    """
    发送通用 Webhook 通知

    Args:
        title: 消息标题
        content: 消息内容
        link_url: 链接地址（可选）

    Returns:
        bool: 是否发送成功
    """
    config = await get_webhook_config()

    if not config["enabled"]:
        logger.warning("Webhook is not enabled, skipping message send")
        return False

    if not config["url"]:
        logger.error("Webhook URL is not configured")
        return False

    try:
        # 准备变量
        variables = {
            "title": title,
            "content": content,
            "link_url": link_url or "",
        }

        # 渲染请求体
        body_str = _render_template(config["body_template"], variables)

        # 尝试解析为 JSON
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            # 如果不是有效 JSON，作为纯文本发送
            body = body_str

        # 准备请求头
        headers = dict(config["headers"]) if config["headers"] else {}

        # 添加签名
        if config["secret"]:
            signature = _generate_signature(config["secret"], body_str)
            headers["X-Webhook-Signature"] = f"sha256={signature}"
            headers["X-Webhook-Signature-256"] = signature

        # 发送请求
        async with httpx.AsyncClient(timeout=30.0) as client:
            method = config["method"].upper()

            if method == "GET":
                # GET 请求，参数放在 URL 中
                response = await client.get(
                    config["url"],
                    params=variables,
                    headers=headers,
                )
            else:
                # POST/PUT/PATCH 请求
                if isinstance(body, dict):
                    response = await client.request(
                        method,
                        config["url"],
                        json=body,
                        headers=headers,
                    )
                else:
                    headers.setdefault("Content-Type", "text/plain")
                    response = await client.request(
                        method,
                        config["url"],
                        content=body,
                        headers=headers,
                    )

            # 检查响应状态
            if 200 <= response.status_code < 300:
                logger.info(
                    f"Webhook notification sent successfully, status: {response.status_code}"
                )
                return True
            else:
                logger.error(
                    f"Failed to send webhook notification, status: {response.status_code}, "
                    f"response: {response.text[:500]}"
                )
                return False

    except Exception as e:
        logger.error(f"Failed to send webhook notification: {e}")
        return False
