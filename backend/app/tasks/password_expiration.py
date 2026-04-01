"""
Password expiration related scheduled tasks
"""

import logging
from datetime import datetime, timedelta, timezone

from app.core.celery import celery_app
from app.core.i18n import t
from app.models.user import User
from app.models.site_setting import SiteSetting
from app.models.notification import AutoNotificationType, NotificationLevel
from app.services.auto_notification import AutoNotificationService
from app.services.password_expiration import PasswordExpirationService

logger = logging.getLogger(__name__)


def _get_event_loop():
    """Get or create event loop"""
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


@celery_app.task(name="tasks.check_password_expiration")
def check_password_expiration_task():
    """
    Scheduled task to check password expiration status

    - Check passwords expiring soon (within warning period) and send reminders
    - Check expired passwords and send notifications
    - Set force_password_change flag for expired passwords
    """
    loop = _get_event_loop()
    try:
        loop.run_until_complete(_check_password_expiration())
    except Exception as e:
        logger.error(f"Failed to check password expiration: {e}")
        raise


async def _check_password_expiration():
    """Actual logic for checking password expiration"""
    # Check if password expiration policy is enabled
    enabled = await SiteSetting.get_value("password_expiration_enabled", False)
    if not enabled:
        logger.info("Password expiration policy is disabled, skipping check")
        return

    now = datetime.now(timezone.utc)

    # Get policy settings
    warning_days = await SiteSetting.get_value("password_expiration_warning_days", 7)

    # Query local auth users (not SSO, not exempt, not superuser)
    # Only check users with password_changed_at set and password_expires_at set
    users = await User.filter(
        auth_source="local",
        is_superuser=False,
        password_expiration_exempt=False,
        password_changed_at__isnull=False,
        password_expires_at__isnull=False,
    ).all()

    expired_count = 0
    expiring_count = 0

    for user in users:
        # Skip if no expiration date (shouldn't happen with the filter above)
        if not user.password_expires_at:
            continue

        # Calculate days until expiration
        delta = user.password_expires_at - now
        days_remaining = delta.days

        # Check if password is expired
        if days_remaining < 0:
            # Password is expired
            if not user.force_password_change:
                user.force_password_change = True
                await user.save()

            # Send expired notification (only once per day to avoid spam)
            # Check if we already sent notification today
            if (
                not user.password_expiration_notified_at
                or (now - user.password_expiration_notified_at).days >= 1
            ):
                user_locale = getattr(user, "locale", "en")

                await AutoNotificationService.send_to_user(
                    notification_type=AutoNotificationType.PASSWORD_EXPIRED,
                    user_id=user.id,
                    title=t("notify_password_expired_title", lang=user_locale),
                    content=t("notify_password_expired_content", lang=user_locale),
                    level=NotificationLevel.HIGH,
                    data={
                        "user_id": str(user.id),
                        "username": user.username,
                        "expired_at": user.password_expires_at.isoformat(),
                    },
                )

                user.password_expiration_notified_at = now
                await user.save()

                logger.info(f"Sent expired notification for user {user.username}")
                expired_count += 1

        elif 0 < days_remaining <= warning_days:
            # Password is expiring soon
            # Send warning notification at specific intervals: 7, 3, 1 days
            if days_remaining not in [7, 3, 1]:
                continue

            # Check if we already sent notification for this day
            if (
                user.password_expiration_notified_at
                and (now - user.password_expiration_notified_at).days < 1
            ):
                continue

            user_locale = getattr(user, "locale", "en")

            await AutoNotificationService.send_to_user(
                notification_type=AutoNotificationType.PASSWORD_EXPIRING,
                user_id=user.id,
                title=t("notify_password_expiring_title", lang=user_locale),
                content=t(
                    "notify_password_expiring_content",
                    lang=user_locale,
                    days=days_remaining,
                ),
                level=NotificationLevel.MEDIUM,
                data={
                    "user_id": str(user.id),
                    "username": user.username,
                    "expires_at": user.password_expires_at.isoformat(),
                    "days_remaining": days_remaining,
                },
            )

            user.password_expiration_notified_at = now
            await user.save()

            logger.info(
                f"Sent expiring notification for user {user.username} "
                f"(expires in {days_remaining} days)"
            )
            expiring_count += 1

    logger.info(
        f"Password expiration check completed: "
        f"{expiring_count} expiring, {expired_count} expired"
    )
