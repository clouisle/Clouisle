"""
企业微信通知服务模块
支持企业微信群机器人 Webhook 和企业应用两种方式
"""

import logging
from typing import Optional

import httpx

from app.models.site_setting import SiteSetting

logger = logging.getLogger(__name__)


async def get_wechat_config() -> dict:
    """获取企业微信配置"""
    return {
        "enabled": await SiteSetting.get_value("wechat_enabled", False),
        "notification_type": await SiteSetting.get_value("wechat_notification_type", "webhook"),
        "webhook_url": await SiteSetting.get_value("wechat_webhook_url", ""),
        "corp_id": await SiteSetting.get_value("wechat_corp_id", ""),
        "agent_id": await SiteSetting.get_value("wechat_agent_id", ""),
        "secret": await SiteSetting.get_value("wechat_secret", ""),
    }


async def send_wechat_webhook(
    title: str,
    content: str,
    link_url: Optional[str] = None,
) -> bool:
    """
    通过 Webhook 发送企业微信群机器人消息

    Args:
        title: 消息标题
        content: 消息内容
        link_url: 链接地址（可选）

    Returns:
        bool: 是否发送成功
    """
    config = await get_wechat_config()

    if not config["enabled"]:
        logger.warning("WeChat Work is not enabled, skipping message send")
        return False

    if not config["webhook_url"]:
        logger.error("WeChat Work webhook URL is not configured")
        return False

    try:
        # 构建 Markdown 消息
        markdown_content = f"### {title}\n\n{content}"
        if link_url:
            markdown_content += f"\n\n[查看详情]({link_url})"

        # 构建消息体
        message = {
            "msgtype": "markdown",
            "markdown": {
                "content": markdown_content,
            },
        }

        # 发送消息
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(config["webhook_url"], json=message)
            result = response.json()

            if result.get("errcode") == 0:
                logger.info("WeChat Work webhook message sent successfully")
                return True
            else:
                logger.error(f"Failed to send WeChat Work webhook message: {result}")
                return False

    except Exception as e:
        logger.error(f"Failed to send WeChat Work webhook message: {e}")
        return False


async def get_wechat_access_token() -> Optional[str]:
    """
    获取企业微信 access_token

    Returns:
        access_token 或 None
    """
    config = await get_wechat_config()

    if not config["corp_id"] or not config["secret"]:
        logger.error("WeChat Work app credentials not configured")
        return None

    try:
        url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        params = {
            "corpid": config["corp_id"],
            "corpsecret": config["secret"],
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            result = response.json()

            if result.get("errcode") == 0:
                return result.get("access_token")
            else:
                logger.error(f"Failed to get WeChat Work access token: {result}")
                return None

    except Exception as e:
        logger.error(f"Failed to get WeChat Work access token: {e}")
        return None


async def send_wechat_app_message(
    title: str,
    content: str,
    link_url: Optional[str] = None,
    to_user: str = "@all",
) -> bool:
    """
    通过企业应用发送消息

    Args:
        title: 消息标题
        content: 消息内容
        link_url: 链接地址（可选）
        to_user: 接收者用户ID列表，多个用|分隔，@all表示全部

    Returns:
        bool: 是否发送成功
    """
    config = await get_wechat_config()

    if not config["enabled"]:
        logger.warning("WeChat Work is not enabled, skipping message send")
        return False

    if not config["agent_id"]:
        logger.error("WeChat Work agent_id is not configured")
        return False

    # 获取 access_token
    access_token = await get_wechat_access_token()
    if not access_token:
        return False

    try:
        # 构建 Markdown 消息
        markdown_content = f"### {title}\n\n{content}"
        if link_url:
            markdown_content += f"\n\n[查看详情]({link_url})"

        # 构建消息体
        message = {
            "touser": to_user,
            "msgtype": "markdown",
            "agentid": int(config["agent_id"]),
            "markdown": {
                "content": markdown_content,
            },
        }

        # 发送消息
        url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=message)
            result = response.json()

            if result.get("errcode") == 0:
                logger.info("WeChat Work app message sent successfully")
                return True
            else:
                logger.error(f"Failed to send WeChat Work app message: {result}")
                return False

    except Exception as e:
        logger.error(f"Failed to send WeChat Work app message: {e}")
        return False


async def send_wechat_notification(
    title: str,
    content: str,
    link_url: Optional[str] = None,
    to_user: str = "@all",
) -> bool:
    """
    发送企业微信通知（自动选择 Webhook 或企业应用方式）

    Args:
        title: 消息标题
        content: 消息内容
        link_url: 链接地址（可选）
        to_user: 接收者用户ID（仅企业应用方式需要）

    Returns:
        bool: 是否发送成功
    """
    config = await get_wechat_config()

    if config["notification_type"] == "app":
        return await send_wechat_app_message(title, content, link_url, to_user)
    else:
        return await send_wechat_webhook(title, content, link_url)
