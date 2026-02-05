"""
飞书通知服务模块
支持飞书群机器人 Webhook 和企业应用两种方式
"""

import logging
import hmac
import hashlib
import base64
import time
from typing import Optional

import httpx

from app.models.site_setting import SiteSetting

logger = logging.getLogger(__name__)


async def get_feishu_config() -> dict:
    """获取飞书配置"""
    return {
        "enabled": await SiteSetting.get_value("feishu_enabled", False),
        "notification_type": await SiteSetting.get_value(
            "feishu_notification_type", "webhook"
        ),
        "webhook_url": await SiteSetting.get_value("feishu_webhook_url", ""),
        "secret": await SiteSetting.get_value("feishu_secret", ""),
        "app_id": await SiteSetting.get_value("feishu_app_id", ""),
        "app_secret": await SiteSetting.get_value("feishu_app_secret", ""),
    }


def _generate_sign(secret: str, timestamp: int) -> str:
    """
    生成飞书机器人签名

    Args:
        secret: 机器人密钥
        timestamp: 时间戳（秒）

    Returns:
        签名字符串
    """
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return sign


async def send_feishu_webhook(
    title: str,
    content: str,
    link_url: Optional[str] = None,
) -> bool:
    """
    通过 Webhook 发送飞书群机器人消息

    Args:
        title: 消息标题
        content: 消息内容
        link_url: 链接地址（可选）

    Returns:
        bool: 是否发送成功
    """
    config = await get_feishu_config()

    if not config["enabled"]:
        logger.warning("Feishu is not enabled, skipping message send")
        return False

    if not config["webhook_url"]:
        logger.error("Feishu webhook URL is not configured")
        return False

    try:
        # 构建消息内容
        markdown_content = f"**{title}**\n\n{content}"
        if link_url:
            markdown_content += f"\n\n[查看详情]({link_url})"

        # 构建卡片消息
        message: dict = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title,
                    },
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content,
                    },
                ],
            },
        }

        # 添加链接按钮
        if link_url:
            message["card"]["elements"].append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "查看详情",
                            },
                            "type": "primary",
                            "url": link_url,
                        },
                    ],
                }
            )

        # 添加签名
        if config["secret"]:
            timestamp = int(time.time())
            sign = _generate_sign(config["secret"], timestamp)
            message["timestamp"] = str(timestamp)
            message["sign"] = sign

        # 发送消息
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(config["webhook_url"], json=message)
            result = response.json()

            if result.get("code") == 0 or result.get("StatusCode") == 0:
                logger.info("Feishu webhook message sent successfully")
                return True
            else:
                logger.error(f"Failed to send Feishu webhook message: {result}")
                return False

    except Exception as e:
        logger.error(f"Failed to send Feishu webhook message: {e}")
        return False


async def get_feishu_tenant_access_token() -> Optional[str]:
    """
    获取飞书 tenant_access_token

    Returns:
        tenant_access_token 或 None
    """
    config = await get_feishu_config()

    if not config["app_id"] or not config["app_secret"]:
        logger.error("Feishu app credentials not configured")
        return None

    try:
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": config["app_id"],
            "app_secret": config["app_secret"],
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            result = response.json()

            if result.get("code") == 0:
                return result.get("tenant_access_token")
            else:
                logger.error(f"Failed to get Feishu tenant access token: {result}")
                return None

    except Exception as e:
        logger.error(f"Failed to get Feishu tenant access token: {e}")
        return None


async def send_feishu_app_message(
    title: str,
    content: str,
    link_url: Optional[str] = None,
    receive_id: str = "",
    receive_id_type: str = "open_id",
) -> bool:
    """
    通过企业应用发送消息

    Args:
        title: 消息标题
        content: 消息内容
        link_url: 链接地址（可选）
        receive_id: 接收者ID
        receive_id_type: ID类型 (open_id, user_id, union_id, email, chat_id)

    Returns:
        bool: 是否发送成功
    """
    config = await get_feishu_config()

    if not config["enabled"]:
        logger.warning("Feishu is not enabled, skipping message send")
        return False

    if not receive_id:
        logger.error("Feishu receive_id is required for app message")
        return False

    # 获取 tenant_access_token
    access_token = await get_feishu_tenant_access_token()
    if not access_token:
        return False

    try:
        # 构建卡片消息
        card: dict = {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title,
                },
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": content,
                },
            ],
        }

        # 添加链接按钮
        if link_url:
            card["elements"].append(
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "查看详情",
                            },
                            "type": "primary",
                            "url": link_url,
                        },
                    ],
                }
            )

        # 构建消息体
        message = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": str({"card": card}),
        }

        # 发送消息
        url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_id_type}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=message, headers=headers)
            result = response.json()

            if result.get("code") == 0:
                logger.info("Feishu app message sent successfully")
                return True
            else:
                logger.error(f"Failed to send Feishu app message: {result}")
                return False

    except Exception as e:
        logger.error(f"Failed to send Feishu app message: {e}")
        return False


async def send_feishu_notification(
    title: str,
    content: str,
    link_url: Optional[str] = None,
    receive_id: str = "",
    receive_id_type: str = "open_id",
) -> bool:
    """
    发送飞书通知（自动选择 Webhook 或企业应用方式）

    Args:
        title: 消息标题
        content: 消息内容
        link_url: 链接地址（可选）
        receive_id: 接收者ID（仅企业应用方式需要）
        receive_id_type: ID类型（仅企业应用方式需要）

    Returns:
        bool: 是否发送成功
    """
    config = await get_feishu_config()

    if config["notification_type"] == "app" and receive_id:
        return await send_feishu_app_message(
            title, content, link_url, receive_id, receive_id_type
        )
    else:
        return await send_feishu_webhook(title, content, link_url)
