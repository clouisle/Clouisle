"""
Slack 通知服务模块
支持 Slack Incoming Webhook
"""

import logging
from typing import Optional

import httpx

from app.models.site_setting import SiteSetting

logger = logging.getLogger(__name__)


async def get_slack_config() -> dict:
    """获取 Slack 配置"""
    return {
        "enabled": await SiteSetting.get_value("slack_enabled", False),
        "webhook_url": await SiteSetting.get_value("slack_webhook_url", ""),
    }


async def send_slack_notification(
    title: str,
    content: str,
    link_url: Optional[str] = None,
) -> bool:
    """
    发送 Slack 通知

    Args:
        title: 消息标题
        content: 消息内容
        link_url: 链接地址（可选）

    Returns:
        bool: 是否发送成功
    """
    config = await get_slack_config()

    if not config["enabled"]:
        logger.warning("Slack is not enabled, skipping message send")
        return False

    if not config["webhook_url"]:
        logger.error("Slack webhook URL is not configured")
        return False

    try:
        # 构建 Slack Block Kit 消息
        blocks: list = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title,
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": content,
                },
            },
        ]

        # 添加链接按钮
        if link_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Details",
                            "emoji": True,
                        },
                        "url": link_url,
                        "style": "primary",
                    },
                ],
            })

        # 构建消息体
        message = {
            "text": title,  # 后备文本
            "blocks": blocks,
        }

        # 发送消息
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(config["webhook_url"], json=message)

            # Slack webhook 返回 "ok" 表示成功
            if response.status_code == 200 and response.text == "ok":
                logger.info("Slack notification sent successfully")
                return True
            else:
                logger.error(
                    f"Failed to send Slack notification, status: {response.status_code}, "
                    f"response: {response.text}"
                )
                return False

    except Exception as e:
        logger.error(f"Failed to send Slack notification: {e}")
        return False
