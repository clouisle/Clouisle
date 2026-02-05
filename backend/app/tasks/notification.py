"""
通知相关的异步任务
"""

import logging
from uuid import UUID

import markdown

from app.core.celery import celery_app
from app.core.email import send_email
from app.core.dingtalk import send_dingtalk_notification
from app.core.wechat import send_wechat_notification
from app.core.feishu import send_feishu_notification
from app.core.webhook import send_webhook_notification
from app.core.slack import send_slack_notification
from app.core.timezone import now_utc
from app.models.notification import (
    Notification,
    NotificationScope,
    NotificationDelivery,
    NotificationChannel,
    NotificationDeliveryStatus,
)
from app.models.site_setting import SiteSetting
from app.models.user import User, TeamMember, Team

logger = logging.getLogger(__name__)

# Markdown 转换器
md = markdown.Markdown(extensions=["extra", "nl2br", "sane_lists"])


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


async def _update_delivery_status(
    notification_id: UUID,
    channel: NotificationChannel,
    status: NotificationDeliveryStatus,
    error_message: str | None = None,
) -> None:
    """更新发送状态"""
    delivery = await NotificationDelivery.filter(
        notification_id=notification_id,
        channel=channel,
    ).first()

    if delivery:
        delivery.status = status
        if error_message:
            delivery.error_message = error_message
        if status == NotificationDeliveryStatus.FAILED:
            delivery.retry_count += 1
        if status == NotificationDeliveryStatus.SUCCESS:
            delivery.sent_at = now_utc()
        await delivery.save()


async def _build_notification_message(
    notification: Notification,
    site_name: str,
) -> tuple[str, str]:
    """
    根据通知范围构建消息标题和内容

    Args:
        notification: 通知对象
        site_name: 站点名称

    Returns:
        tuple[str, str]: (标题, 内容)
    """
    # 基础标题
    title = f"【{site_name}】{notification.title}"
    content = notification.content

    # 根据 scope 添加上下文信息
    if notification.scope == NotificationScope.TEAM and notification.team_id:
        team = await Team.filter(id=notification.team_id).first()
        if team:
            title = f"【{site_name}】[{team.name}] {notification.title}"
            content = f"**团队**: {team.name}\n\n{notification.content}"

    elif notification.scope == NotificationScope.USER and notification.user_id:
        user = await User.filter(id=notification.user_id).first()
        if user:
            title = f"【{site_name}】[@{user.username}] {notification.title}"
            content = f"**用户**: {user.username}\n\n{notification.content}"

    return title, content


@celery_app.task(name="send_notification_email", bind=True, max_retries=3)
def send_notification_email_task(self, notification_id: str):
    """
    发送通知邮件的异步任务

    Args:
        notification_id: 通知ID
    """
    loop = _get_event_loop()
    try:
        loop.run_until_complete(_send_notification_email(UUID(notification_id)))
    except Exception as exc:
        # 更新状态为失败
        loop.run_until_complete(
            _update_delivery_status(
                UUID(notification_id),
                NotificationChannel.EMAIL,
                NotificationDeliveryStatus.FAILED,
                str(exc),
            )
        )
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _send_notification_email(notification_id: UUID):
    """
    发送通知邮件的实际逻辑
    """
    # 更新状态为发送中
    await _update_delivery_status(
        notification_id,
        NotificationChannel.EMAIL,
        NotificationDeliveryStatus.SENDING,
    )

    # 获取通知
    notification = await Notification.filter(id=notification_id).first()
    if not notification:
        logger.error(f"Notification {notification_id} not found")
        raise ValueError(f"Notification {notification_id} not found")

    # 获取站点信息
    site_name = await SiteSetting.get_value("site_name", "Clouisle")

    # 根据通知范围获取收件人
    recipients = await _get_notification_recipients(notification)

    if not recipients:
        logger.warning(f"No recipients found for notification {notification_id}")
        await _update_delivery_status(
            notification_id,
            NotificationChannel.EMAIL,
            NotificationDeliveryStatus.SUCCESS,
        )
        return

    # 构建邮件内容
    subject = f"【{site_name}】{notification.title}"

    # 将 Markdown 转换为 HTML
    md.reset()
    content_html = md.convert(notification.content)

    # 纯文本版本（去除 Markdown 语法的简单处理）
    body_text = f"""{notification.title}

{notification.content}
"""
    if notification.link_url:
        body_text += f"\n查看详情：{notification.link_url}"

    body_text += f"\n\n---\n此邮件由 {site_name} 系统自动发送，请勿回复。"

    # HTML 版本
    body_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        .content h1, .content h2, .content h3 {{ color: #333; margin-top: 1em; margin-bottom: 0.5em; }}
        .content p {{ margin: 0.5em 0; }}
        .content ul, .content ol {{ padding-left: 1.5em; }}
        .content li {{ margin: 0.25em 0; }}
        .content code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: monospace; }}
        .content pre {{ background: #f4f4f4; padding: 12px; border-radius: 6px; overflow-x: auto; }}
        .content blockquote {{ border-left: 4px solid #ddd; margin: 1em 0; padding-left: 1em; color: #666; }}
        .content a {{ color: #0066ff; }}
        .content strong {{ font-weight: 600; }}
        .content em {{ font-style: italic; }}
    </style>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
        <h2 style="color: #333; margin: 0;">{notification.title}</h2>
    </div>

    <div class="content" style="padding: 20px 0; color: #333; line-height: 1.6;">
        {content_html}
    </div>
"""

    if notification.link_url:
        body_html += f"""
    <div style="text-align: center; margin: 30px 0;">
        <a href="{notification.link_url}" style="display: inline-block; background: #0066ff; color: white; padding: 12px 32px; text-decoration: none; border-radius: 6px;">查看详情</a>
    </div>
"""

    body_html += f"""
    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
    <p style="color: #999; font-size: 12px; text-align: center;">
        此邮件由 {site_name} 系统自动发送，请勿回复。
    </p>
</body>
</html>
"""

    # 发送邮件给所有收件人
    success_count = 0
    failed_emails = []
    for email in recipients:
        try:
            result = await send_email(email, subject, body_text, body_html)
            if result:
                success_count += 1
            else:
                failed_emails.append(email)
        except Exception as e:
            logger.error(f"Failed to send notification email to {email}: {e}")
            failed_emails.append(email)

    logger.info(
        f"Sent notification email to {success_count}/{len(recipients)} recipients"
    )

    # 更新发送状态
    if success_count == len(recipients):
        await _update_delivery_status(
            notification_id,
            NotificationChannel.EMAIL,
            NotificationDeliveryStatus.SUCCESS,
        )
    elif success_count > 0:
        # 部分成功
        await _update_delivery_status(
            notification_id,
            NotificationChannel.EMAIL,
            NotificationDeliveryStatus.SUCCESS,
            f"Partial success: {success_count}/{len(recipients)} sent, failed: {', '.join(failed_emails[:5])}",
        )
    else:
        raise RuntimeError(f"Failed to send email to all {len(recipients)} recipients")


async def _get_notification_recipients(notification: Notification) -> list[str]:
    """
    根据通知范围获取收件人邮箱列表

    Args:
        notification: 通知对象

    Returns:
        收件人邮箱列表
    """
    recipients = []

    if notification.scope == NotificationScope.GLOBAL:
        # 全局通知：发送给所有激活用户
        users = await User.filter(is_active=True, email__not="").all()
        recipients = [user.email for user in users if user.email]

    elif notification.scope == NotificationScope.TEAM:
        # 团队通知：发送给团队所有成员
        if notification.team_id:
            members = await TeamMember.filter(
                team_id=notification.team_id
            ).prefetch_related("user")
            recipients = [
                member.user.email
                for member in members
                if member.user.is_active and member.user.email
            ]

    elif notification.scope == NotificationScope.USER:
        # 个人通知：发送给指定用户
        if notification.user_id:
            user = await User.filter(id=notification.user_id, is_active=True).first()
            if user and user.email:
                recipients = [user.email]

    return recipients


@celery_app.task(name="send_notification_dingtalk", bind=True, max_retries=3)
def send_notification_dingtalk_task(self, notification_id: str):
    """
    发送钉钉通知的异步任务

    Args:
        notification_id: 通知ID
    """
    loop = _get_event_loop()
    try:
        loop.run_until_complete(_send_notification_dingtalk(UUID(notification_id)))
    except Exception as exc:
        # 更新状态为失败
        loop.run_until_complete(
            _update_delivery_status(
                UUID(notification_id),
                NotificationChannel.DINGTALK,
                NotificationDeliveryStatus.FAILED,
                str(exc),
            )
        )
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _send_notification_dingtalk(notification_id: UUID) -> bool:
    """
    发送钉钉通知的实际逻辑

    Returns:
        bool: 是否发送成功
    """
    # 更新状态为发送中
    await _update_delivery_status(
        notification_id,
        NotificationChannel.DINGTALK,
        NotificationDeliveryStatus.SENDING,
    )

    # 获取通知
    notification = await Notification.filter(id=notification_id).first()
    if not notification:
        logger.error(f"Notification {notification_id} not found")
        raise ValueError(f"Notification {notification_id} not found")

    # 获取站点信息
    site_name = await SiteSetting.get_value("site_name", "Clouisle")

    # 构建消息标题和内容（根据 scope 区分）
    title, content = await _build_notification_message(notification, site_name)

    # 发送钉钉通知
    result = await send_dingtalk_notification(
        title=title,
        content=content,
        link_url=notification.link_url,
    )

    if result:
        logger.info(f"DingTalk notification sent successfully for {notification_id}")
        await _update_delivery_status(
            notification_id,
            NotificationChannel.DINGTALK,
            NotificationDeliveryStatus.SUCCESS,
        )
        return True
    else:
        raise RuntimeError(
            f"Failed to send DingTalk notification for {notification_id}"
        )


@celery_app.task(name="send_notification_wechat", bind=True, max_retries=3)
def send_notification_wechat_task(self, notification_id: str):
    """
    发送企业微信通知的异步任务

    Args:
        notification_id: 通知ID
    """
    loop = _get_event_loop()
    try:
        loop.run_until_complete(_send_notification_wechat(UUID(notification_id)))
    except Exception as exc:
        loop.run_until_complete(
            _update_delivery_status(
                UUID(notification_id),
                NotificationChannel.WECHAT,
                NotificationDeliveryStatus.FAILED,
                str(exc),
            )
        )
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _send_notification_wechat(notification_id: UUID) -> bool:
    """
    发送企业微信通知的实际逻辑
    """
    await _update_delivery_status(
        notification_id,
        NotificationChannel.WECHAT,
        NotificationDeliveryStatus.SENDING,
    )

    notification = await Notification.filter(id=notification_id).first()
    if not notification:
        logger.error(f"Notification {notification_id} not found")
        raise ValueError(f"Notification {notification_id} not found")

    site_name = await SiteSetting.get_value("site_name", "Clouisle")
    title, content = await _build_notification_message(notification, site_name)

    result = await send_wechat_notification(
        title=title,
        content=content,
        link_url=notification.link_url,
    )

    if result:
        logger.info(f"WeChat Work notification sent successfully for {notification_id}")
        await _update_delivery_status(
            notification_id,
            NotificationChannel.WECHAT,
            NotificationDeliveryStatus.SUCCESS,
        )
        return True
    else:
        raise RuntimeError(
            f"Failed to send WeChat Work notification for {notification_id}"
        )


@celery_app.task(name="send_notification_feishu", bind=True, max_retries=3)
def send_notification_feishu_task(self, notification_id: str):
    """
    发送飞书通知的异步任务

    Args:
        notification_id: 通知ID
    """
    loop = _get_event_loop()
    try:
        loop.run_until_complete(_send_notification_feishu(UUID(notification_id)))
    except Exception as exc:
        loop.run_until_complete(
            _update_delivery_status(
                UUID(notification_id),
                NotificationChannel.FEISHU,
                NotificationDeliveryStatus.FAILED,
                str(exc),
            )
        )
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _send_notification_feishu(notification_id: UUID) -> bool:
    """
    发送飞书通知的实际逻辑
    """
    await _update_delivery_status(
        notification_id,
        NotificationChannel.FEISHU,
        NotificationDeliveryStatus.SENDING,
    )

    notification = await Notification.filter(id=notification_id).first()
    if not notification:
        logger.error(f"Notification {notification_id} not found")
        raise ValueError(f"Notification {notification_id} not found")

    site_name = await SiteSetting.get_value("site_name", "Clouisle")
    title, content = await _build_notification_message(notification, site_name)

    result = await send_feishu_notification(
        title=title,
        content=content,
        link_url=notification.link_url,
    )

    if result:
        logger.info(f"Feishu notification sent successfully for {notification_id}")
        await _update_delivery_status(
            notification_id,
            NotificationChannel.FEISHU,
            NotificationDeliveryStatus.SUCCESS,
        )
        return True
    else:
        raise RuntimeError(f"Failed to send Feishu notification for {notification_id}")


@celery_app.task(name="send_notification_webhook", bind=True, max_retries=3)
def send_notification_webhook_task(self, notification_id: str):
    """
    发送通用 Webhook 通知的异步任务

    Args:
        notification_id: 通知ID
    """
    loop = _get_event_loop()
    try:
        loop.run_until_complete(_send_notification_webhook(UUID(notification_id)))
    except Exception as exc:
        loop.run_until_complete(
            _update_delivery_status(
                UUID(notification_id),
                NotificationChannel.WEBHOOK,
                NotificationDeliveryStatus.FAILED,
                str(exc),
            )
        )
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _send_notification_webhook(notification_id: UUID) -> bool:
    """
    发送通用 Webhook 通知的实际逻辑
    """
    await _update_delivery_status(
        notification_id,
        NotificationChannel.WEBHOOK,
        NotificationDeliveryStatus.SENDING,
    )

    notification = await Notification.filter(id=notification_id).first()
    if not notification:
        logger.error(f"Notification {notification_id} not found")
        raise ValueError(f"Notification {notification_id} not found")

    site_name = await SiteSetting.get_value("site_name", "Clouisle")
    title, content = await _build_notification_message(notification, site_name)

    result = await send_webhook_notification(
        title=title,
        content=content,
        link_url=notification.link_url,
    )

    if result:
        logger.info(f"Webhook notification sent successfully for {notification_id}")
        await _update_delivery_status(
            notification_id,
            NotificationChannel.WEBHOOK,
            NotificationDeliveryStatus.SUCCESS,
        )
        return True
    else:
        raise RuntimeError(f"Failed to send Webhook notification for {notification_id}")


@celery_app.task(name="send_notification_slack", bind=True, max_retries=3)
def send_notification_slack_task(self, notification_id: str):
    """
    发送 Slack 通知的异步任务

    Args:
        notification_id: 通知ID
    """
    loop = _get_event_loop()
    try:
        loop.run_until_complete(_send_notification_slack(UUID(notification_id)))
    except Exception as exc:
        loop.run_until_complete(
            _update_delivery_status(
                UUID(notification_id),
                NotificationChannel.SLACK,
                NotificationDeliveryStatus.FAILED,
                str(exc),
            )
        )
        raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))


async def _send_notification_slack(notification_id: UUID) -> bool:
    """
    发送 Slack 通知的实际逻辑
    """
    await _update_delivery_status(
        notification_id,
        NotificationChannel.SLACK,
        NotificationDeliveryStatus.SENDING,
    )

    notification = await Notification.filter(id=notification_id).first()
    if not notification:
        logger.error(f"Notification {notification_id} not found")
        raise ValueError(f"Notification {notification_id} not found")

    site_name = await SiteSetting.get_value("site_name", "Clouisle")
    title, content = await _build_notification_message(notification, site_name)

    result = await send_slack_notification(
        title=title,
        content=content,
        link_url=notification.link_url,
    )

    if result:
        logger.info(f"Slack notification sent successfully for {notification_id}")
        await _update_delivery_status(
            notification_id,
            NotificationChannel.SLACK,
            NotificationDeliveryStatus.SUCCESS,
        )
        return True
    else:
        raise RuntimeError(f"Failed to send Slack notification for {notification_id}")
