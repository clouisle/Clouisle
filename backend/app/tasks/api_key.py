"""
API Key 相关的定时任务
"""

import logging
from datetime import timedelta

from app.core.celery import celery_app
from app.core.i18n import t
from app.core.timezone import now_utc
from app.models.api_key import APIKey
from app.models.notification import AutoNotificationType, NotificationLevel
from app.services.auto_notification import AutoNotificationService

logger = logging.getLogger(__name__)


def _get_event_loop():
    """获取或创建事件循环"""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


@celery_app.task(name="tasks.check_api_key_expiration")
def check_api_key_expiration_task():
    """
    检查 API Key 过期状态的定时任务

    - 检查即将过期的 API Key（7天内）并发送提醒
    - 检查已过期的 API Key 并发送通知
    """
    loop = _get_event_loop()
    try:
        loop.run_until_complete(_check_api_key_expiration())
    except Exception as e:
        logger.error(f"Failed to check API key expiration: {e}")
        raise


async def _check_api_key_expiration():
    """检查 API Key 过期状态的实际逻辑"""
    now = now_utc()

    # 检查即将过期的 API Key（7天内过期，且还未过期）
    expiring_threshold = now + timedelta(days=7)
    expiring_keys = await APIKey.filter(
        is_active=True,
        expires_at__isnull=False,
        expires_at__gt=now,
        expires_at__lte=expiring_threshold,
    ).prefetch_related("user")

    for api_key in expiring_keys:
        # 计算剩余天数
        days_remaining = (api_key.expires_at - now).days
        if days_remaining < 1:
            days_remaining = 1

        # 检查是否已经发送过提醒（通过 data 字段记录）
        # 为避免重复发送，我们只在特定天数发送：7天、3天、1天
        if days_remaining not in [7, 3, 1]:
            continue

        await AutoNotificationService.send_to_user(
            notification_type=AutoNotificationType.APIKEY_EXPIRING,
            user_id=api_key.user.id,
            title=t("notify_apikey_expiring_title"),
            content=t(
                "notify_apikey_expiring_content",
                key_name=api_key.name,
                key_prefix=api_key.key_prefix,
                days=days_remaining,
            ),
            level=NotificationLevel.HIGH,
            data={
                "api_key_id": str(api_key.id),
                "key_name": api_key.name,
                "key_prefix": api_key.key_prefix,
                "expires_at": api_key.expires_at.isoformat(),
                "days_remaining": days_remaining,
            },
        )
        logger.info(
            f"Sent expiring notification for API key {api_key.key_prefix}... "
            f"(expires in {days_remaining} days)"
        )

    # 检查刚刚过期的 API Key（过期时间在过去24小时内）
    expired_threshold = now - timedelta(hours=24)
    expired_keys = await APIKey.filter(
        is_active=True,
        expires_at__isnull=False,
        expires_at__gt=expired_threshold,
        expires_at__lte=now,
    ).prefetch_related("user")

    for api_key in expired_keys:
        await AutoNotificationService.send_to_user(
            notification_type=AutoNotificationType.APIKEY_EXPIRED,
            user_id=api_key.user.id,
            title=t("notify_apikey_expired_title"),
            content=t(
                "notify_apikey_expired_content",
                key_name=api_key.name,
                key_prefix=api_key.key_prefix,
            ),
            level=NotificationLevel.HIGH,
            data={
                "api_key_id": str(api_key.id),
                "key_name": api_key.name,
                "key_prefix": api_key.key_prefix,
                "expired_at": api_key.expires_at.isoformat(),
            },
        )
        logger.info(f"Sent expired notification for API key {api_key.key_prefix}...")

    logger.info(
        f"API key expiration check completed: "
        f"{len(expiring_keys)} expiring, {len(expired_keys)} expired"
    )
