"""
自动通知服务 - 统一处理系统自动通知的发送
"""

import logging
from typing import Optional
from uuid import UUID

from app.core.timezone import now_utc
from app.models.notification import (
    AutoNotificationType,
    Notification,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationLevel,
    NotificationScope,
    NotificationSource,
)
from app.models.site_setting import SiteSetting
from app.services.notification import create_notification

logger = logging.getLogger(__name__)


class AutoNotificationService:
    """自动通知服务"""

    @classmethod
    async def get_config(cls) -> dict:
        """获取自动通知配置"""
        config = await SiteSetting.get_value("auto_notification_config", {})
        return config or {}

    @classmethod
    async def is_enabled(cls, notification_type: AutoNotificationType) -> bool:
        """检查指定通知类型是否启用"""
        config = await cls.get_config()
        enabled_types = config.get("enabled_types", [])
        return notification_type.value in enabled_types

    @classmethod
    async def get_channels(cls) -> list[NotificationChannel]:
        """获取全局配置的外部渠道"""
        config = await cls.get_config()
        channel_names = config.get("channels", [])
        channels = []
        for name in channel_names:
            try:
                channels.append(NotificationChannel(name))
            except ValueError:
                logger.warning(f"Unknown notification channel: {name}")
        return channels

    @classmethod
    async def _is_channel_enabled(cls, channel: NotificationChannel) -> bool:
        """检查渠道是否已配置并启用"""
        channel_enabled_keys = {
            NotificationChannel.EMAIL: "smtp_enabled",
            NotificationChannel.DINGTALK: "dingtalk_enabled",
            NotificationChannel.WECHAT: "wechat_enabled",
            NotificationChannel.FEISHU: "feishu_enabled",
            NotificationChannel.WEBHOOK: "webhook_enabled",
            NotificationChannel.SLACK: "slack_enabled",
        }
        key = channel_enabled_keys.get(channel)
        if not key:
            return False
        return await SiteSetting.get_value(key, False)

    @classmethod
    async def send(
        cls,
        notification_type: AutoNotificationType,
        scope: NotificationScope,
        title: str,
        content: str,
        user_id: Optional[UUID] = None,
        team_id: Optional[UUID] = None,
        data: Optional[dict] = None,
        link_url: Optional[str] = None,
        level: NotificationLevel = NotificationLevel.MEDIUM,
    ) -> Optional[Notification]:
        """
        发送自动通知

        Args:
            notification_type: 自动通知类型
            scope: 通知范围 (global/team/user)
            title: 通知标题
            content: 通知内容 (支持 Markdown)
            user_id: 目标用户ID (scope=user 时必填)
            team_id: 目标团队ID (scope=team 时必填)
            data: 附加数据
            link_url: 相关链接
            level: 通知级别

        Returns:
            创建的通知对象，如果通知类型未启用则返回 None
        """
        # 检查通知类型是否启用
        if not await cls.is_enabled(notification_type):
            logger.debug(
                f"Auto notification type {notification_type.value} is disabled, skipping"
            )
            return None

        # 创建站内通知
        notification = await Notification.create(
            scope=scope,
            team_id=team_id,
            user_id=user_id,
            type=notification_type.value,
            source=NotificationSource.SYSTEM,
            title=title,
            content=content,
            level=level,
            data=data,
            link_url=link_url,
            created_at=now_utc(),
            updated_at=now_utc(),
        )

        # 创建审计记录
        await create_notification(notification)

        logger.info(
            f"Created auto notification: type={notification_type.value}, "
            f"scope={scope.value}, id={notification.id}"
        )

        # 获取配置的外部渠道并触发发送
        channels = await cls.get_channels()
        if channels:
            await cls._trigger_external_channels(notification, channels)

        return notification

    @classmethod
    async def _trigger_external_channels(
        cls,
        notification: Notification,
        channels: list[NotificationChannel],
    ) -> None:
        """触发外部渠道发送"""
        from app.tasks.notification import (
            send_notification_dingtalk_task,
            send_notification_email_task,
            send_notification_feishu_task,
            send_notification_slack_task,
            send_notification_wechat_task,
            send_notification_webhook_task,
        )

        channel_tasks = {
            NotificationChannel.EMAIL: send_notification_email_task,
            NotificationChannel.DINGTALK: send_notification_dingtalk_task,
            NotificationChannel.WECHAT: send_notification_wechat_task,
            NotificationChannel.FEISHU: send_notification_feishu_task,
            NotificationChannel.WEBHOOK: send_notification_webhook_task,
            NotificationChannel.SLACK: send_notification_slack_task,
        }

        for channel in channels:
            # 检查渠道是否已配置并启用
            if not await cls._is_channel_enabled(channel):
                logger.debug(
                    f"Channel {channel.value} is not enabled, skipping for notification {notification.id}"
                )
                continue

            # 创建发送记录
            delivery = await NotificationDelivery.create(
                notification_id=notification.id,
                channel=channel,
                status=NotificationDeliveryStatus.PENDING,
                created_at=now_utc(),
                updated_at=now_utc(),
            )

            # 触发异步任务
            task_func = channel_tasks.get(channel)
            if task_func:
                try:
                    result = task_func.delay(str(notification.id))
                    delivery.task_id = result.id
                    await delivery.save()
                    logger.info(
                        f"Triggered {channel.value} notification task for {notification.id}, "
                        f"task_id={result.id}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to trigger {channel.value} notification task: {e}"
                    )
                    delivery.status = NotificationDeliveryStatus.FAILED
                    delivery.error_message = "task_dispatch_failed"
                    await delivery.save()

    @classmethod
    async def send_to_user(
        cls,
        notification_type: AutoNotificationType,
        user_id: UUID,
        title: str,
        content: str,
        data: Optional[dict] = None,
        link_url: Optional[str] = None,
        level: NotificationLevel = NotificationLevel.MEDIUM,
    ) -> Optional[Notification]:
        """发送用户级别的自动通知（便捷方法）"""
        return await cls.send(
            notification_type=notification_type,
            scope=NotificationScope.USER,
            user_id=user_id,
            title=title,
            content=content,
            data=data,
            link_url=link_url,
            level=level,
        )

    @classmethod
    async def send_to_team(
        cls,
        notification_type: AutoNotificationType,
        team_id: UUID,
        title: str,
        content: str,
        data: Optional[dict] = None,
        link_url: Optional[str] = None,
        level: NotificationLevel = NotificationLevel.MEDIUM,
    ) -> Optional[Notification]:
        """发送团队级别的自动通知（便捷方法）"""
        return await cls.send(
            notification_type=notification_type,
            scope=NotificationScope.TEAM,
            team_id=team_id,
            title=title,
            content=content,
            data=data,
            link_url=link_url,
            level=level,
        )

    @classmethod
    async def send_global(
        cls,
        notification_type: AutoNotificationType,
        title: str,
        content: str,
        data: Optional[dict] = None,
        link_url: Optional[str] = None,
        level: NotificationLevel = NotificationLevel.MEDIUM,
    ) -> Optional[Notification]:
        """发送全局自动通知（便捷方法）"""
        return await cls.send(
            notification_type=notification_type,
            scope=NotificationScope.GLOBAL,
            title=title,
            content=content,
            data=data,
            link_url=link_url,
            level=level,
        )
