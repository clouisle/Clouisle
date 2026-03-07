"""
钉钉通知服务模块
支持钉钉机器人 Webhook 和企业内部应用两种方式
"""

import logging
import hmac
import hashlib
import base64
import time
from typing import Optional
from urllib.parse import quote_plus

import httpx

from app.models.site_setting import SiteSetting

logger = logging.getLogger(__name__)


async def get_dingtalk_config() -> dict:
    """获取钉钉配置"""
    return {
        "enabled": await SiteSetting.get_value("dingtalk_enabled", False),
        "webhook_url": await SiteSetting.get_value("dingtalk_webhook_url", ""),
        "secret": await SiteSetting.get_value("dingtalk_secret", ""),
        "app_key": await SiteSetting.get_value("dingtalk_app_key", ""),
        "app_secret": await SiteSetting.get_value("dingtalk_app_secret", ""),
        "agent_id": await SiteSetting.get_value("dingtalk_agent_id", ""),
        "notification_type": await SiteSetting.get_value(
            "dingtalk_notification_type", "webhook"
        ),  # webhook 或 app
    }


def _generate_sign(secret: str, timestamp: int) -> str:
    """
    生成钉钉机器人签名

    根据钉钉官方文档：
    把timestamp+"\n"+密钥当做签名字符串，使用HmacSHA256算法计算签名，
    然后进行Base64 encode，最后再把签名参数再进行urlEncode，得到最终的签名

    Args:
        secret: 机器人密钥
        timestamp: 时间戳（毫秒）

    Returns:
        签名字符串
    """
    secret_enc = secret.encode("utf-8")
    string_to_sign = f"{timestamp}\n{secret}"
    string_to_sign_enc = string_to_sign.encode("utf-8")
    hmac_code = hmac.new(
        secret_enc, string_to_sign_enc, digestmod=hashlib.sha256
    ).digest()
    sign = quote_plus(base64.b64encode(hmac_code).decode("utf-8"))
    return sign


async def send_dingtalk_webhook(
    title: str,
    content: str,
    link_url: Optional[str] = None,
) -> bool:
    """
    通过 Webhook 发送钉钉机器人消息

    Args:
        title: 消息标题
        content: 消息内容
        link_url: 链接地址（可选）

    Returns:
        bool: 是否发送成功
    """
    config = await get_dingtalk_config()

    # 调试日志
    logger.info(
        "DingTalk config loaded: enabled=%s webhook_configured=%s secret_configured=%s",
        config["enabled"],
        bool(config["webhook_url"]),
        bool(config["secret"]),
    )

    if not config["enabled"]:
        logger.warning("DingTalk is not enabled, skipping message send")
        return False

    if not config["webhook_url"]:
        logger.error("DingTalk webhook URL is not configured")
        return False

    try:
        # 构建 Webhook URL（带签名）
        webhook_url = config["webhook_url"]
        if config["secret"]:
            timestamp = int(time.time() * 1000)
            sign = _generate_sign(config["secret"], timestamp)
            webhook_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"

        # 构建 Markdown 消息
        markdown_text = f"### {title}\n\n{content}"
        if link_url:
            markdown_text += f"\n\n[查看详情]({link_url})"

        # 构建消息体
        message = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": markdown_text,
            },
        }

        # 发送消息
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=message)
            result = response.json()

            if result.get("errcode") == 0:
                logger.info("DingTalk webhook message sent successfully")
                return True
            else:
                logger.error(f"Failed to send DingTalk webhook message: {result}")
                return False

    except Exception as e:
        logger.error(f"Failed to send DingTalk webhook message: {e}")
        return False


async def get_dingtalk_access_token() -> Optional[str]:
    """
    获取钉钉企业内部应用 access_token

    Returns:
        access_token 或 None
    """
    config = await get_dingtalk_config()

    if not config["app_key"] or not config["app_secret"]:
        logger.error("DingTalk app credentials not configured")
        return None

    try:
        url = "https://oapi.dingtalk.com/gettoken"
        params = {
            "appkey": config["app_key"],
            "appsecret": config["app_secret"],
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            result = response.json()

            if result.get("errcode") == 0:
                return result.get("access_token")
            else:
                logger.error(f"Failed to get DingTalk access token: {result}")
                return None

    except Exception as e:
        logger.error(f"Failed to get DingTalk access token: {e}")
        return None


async def send_dingtalk_app_message(
    user_id_list: list[str],
    title: str,
    content: str,
    link_url: Optional[str] = None,
) -> bool:
    """
    通过企业内部应用发送工作通知

    Args:
        user_id_list: 钉钉用户 ID 列表
        title: 消息标题
        content: 消息内容
        link_url: 链接地址（可选）

    Returns:
        bool: 是否发送成功
    """
    config = await get_dingtalk_config()

    if not config["enabled"]:
        logger.warning("DingTalk is not enabled, skipping message send")
        return False

    if not config["agent_id"]:
        logger.error("DingTalk agent_id is not configured")
        return False

    # 获取 access_token
    access_token = await get_dingtalk_access_token()
    if not access_token:
        return False

    try:
        # 构建 Markdown 消息
        markdown_text = f"### {title}\n\n{content}"
        if link_url:
            markdown_text += f"\n\n[查看详情]({link_url})"

        # 构建消息体
        message = {
            "agent_id": config["agent_id"],
            "userid_list": ",".join(user_id_list),
            "msg": {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": markdown_text,
                },
            },
        }

        # 发送消息
        url = f"https://oapi.dingtalk.com/topapi/message/corpconversation/asyncsend_v2?access_token={access_token}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=message)
            result = response.json()

            if result.get("errcode") == 0:
                logger.info(
                    f"DingTalk app message sent successfully to {len(user_id_list)} users"
                )
                return True
            else:
                logger.error(f"Failed to send DingTalk app message: {result}")
                return False

    except Exception as e:
        logger.error(f"Failed to send DingTalk app message: {e}")
        return False


async def send_dingtalk_notification(
    title: str,
    content: str,
    link_url: Optional[str] = None,
    user_id_list: Optional[list[str]] = None,
) -> bool:
    """
    发送钉钉通知（自动选择 Webhook 或企业应用方式）

    Args:
        title: 消息标题
        content: 消息内容
        link_url: 链接地址（可选）
        user_id_list: 钉钉用户 ID 列表（仅企业应用方式需要）

    Returns:
        bool: 是否发送成功
    """
    config = await get_dingtalk_config()

    if config["notification_type"] == "app" and user_id_list:
        # 使用企业内部应用发送
        return await send_dingtalk_app_message(user_id_list, title, content, link_url)
    else:
        # 使用 Webhook 机器人发送
        return await send_dingtalk_webhook(title, content, link_url)
