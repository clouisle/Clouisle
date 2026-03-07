"""
Password expiration service for managing password lifecycle and history.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from passlib.context import CryptContext

from app.models.user import User
from app.models.password_history import PasswordHistory
from app.models.site_setting import SiteSetting

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class PasswordExpirationService:
    """Service for managing password expiration and history"""

    @staticmethod
    async def is_user_exempt(user: User) -> bool:
        """
        Check if user is exempt from password expiration policy.

        Exemption criteria:
        - SSO users (auth_source != "local")
        - Users with password_expiration_exempt flag
        - Superusers (is_superuser=True)
        """
        if user.auth_source != "local":
            return True
        if user.password_expiration_exempt:
            return True
        if user.is_superuser:
            return True
        return False

    @staticmethod
    async def calculate_expiration_date(user: User) -> Optional[datetime]:
        """
        Calculate password expiration date based on policy.

        Returns None if:
        - Policy is disabled
        - User is exempt
        - password_changed_at is not set
        """
        # Check if policy is enabled
        enabled = await SiteSetting.get_value("password_expiration_enabled", False)
        if not enabled:
            return None

        # Check if user is exempt
        if await PasswordExpirationService.is_user_exempt(user):
            return None

        # Check if password_changed_at is set
        if not user.password_changed_at:
            return None

        # Calculate expiration date
        expiration_days = await SiteSetting.get_value("password_expiration_days", 90)
        expiration_date = user.password_changed_at + timedelta(days=expiration_days)

        return expiration_date

    @staticmethod
    async def is_password_expired(user: User) -> bool:
        """Check if user's password is expired"""
        expiration_date = await PasswordExpirationService.calculate_expiration_date(
            user
        )
        if not expiration_date:
            return False

        return datetime.now(timezone.utc) > expiration_date

    @staticmethod
    async def days_until_expiration(user: User) -> Optional[int]:
        """
        Get days until password expiration.

        Returns:
        - None if user is exempt or policy is disabled
        - Negative number if already expired
        - Positive number for days remaining
        """
        expiration_date = await PasswordExpirationService.calculate_expiration_date(
            user
        )
        if not expiration_date:
            return None

        delta = expiration_date - datetime.now(timezone.utc)
        return delta.days

    @staticmethod
    async def should_warn_user(user: User) -> bool:
        """Check if user should be warned about expiring password"""
        days_remaining = await PasswordExpirationService.days_until_expiration(user)
        if days_remaining is None:
            return False

        warning_days = await SiteSetting.get_value(
            "password_expiration_warning_days", 7
        )
        return 0 < days_remaining <= warning_days

    @staticmethod
    async def add_to_password_history(user: User, hashed_password: str) -> None:
        """
        Add password to history and cleanup old entries.

        Args:
            user: User object
            hashed_password: Already hashed password
        """
        # Add new entry
        await PasswordHistory.create(user=user, hashed_password=hashed_password)

        # Cleanup old entries (keep only the configured count)
        history_count = await SiteSetting.get_value("password_history_count", 5)

        # Get all history entries for this user, ordered by created_at DESC
        all_history = await PasswordHistory.filter(user=user).order_by("-created_at")

        # Delete entries beyond the configured count
        if len(all_history) > history_count:
            entries_to_delete = all_history[history_count:]
            for entry in entries_to_delete:
                await entry.delete()

        logger.info(
            f"Added password to history for user {user.username}, "
            f"keeping {min(len(all_history), history_count)} entries"
        )

    @staticmethod
    async def check_password_history(user: User, new_password: str) -> bool:
        """
        Check if new password was recently used.

        Args:
            user: User object
            new_password: Plain text password to check

        Returns:
            True if password was recently used, False otherwise
        """
        history_count = await SiteSetting.get_value("password_history_count", 5)
        if history_count == 0:
            return False

        # Get recent password history
        history_entries = (
            await PasswordHistory.filter(user=user)
            .order_by("-created_at")
            .limit(history_count)
        )

        # Check against each historical password using bcrypt
        for entry in history_entries:
            if pwd_context.verify(new_password, entry.hashed_password):
                return True

        return False

    @staticmethod
    async def can_change_password(user: User) -> tuple[bool, Optional[int]]:
        """
        Check if user can change password based on minimum age requirement.

        Returns:
            Tuple of (can_change, days_remaining)
            - can_change: True if password can be changed
            - days_remaining: Days until password can be changed (None if can change)
        """
        min_age_days = await SiteSetting.get_value("password_min_age_days", 0)
        if min_age_days == 0:
            return True, None

        if not user.password_changed_at:
            return True, None

        # Calculate when password can be changed
        can_change_at = user.password_changed_at + timedelta(days=min_age_days)
        now = datetime.now(timezone.utc)

        if now >= can_change_at:
            return True, None

        # Calculate days remaining
        delta = can_change_at - now
        days_remaining = delta.days + (1 if delta.seconds > 0 else 0)
        return False, days_remaining

    @staticmethod
    async def update_password_with_expiration(
        user: User, new_hashed_password: str
    ) -> None:
        """
        Update user password with expiration logic.

        This method:
        1. Updates the hashed password
        2. Sets password_changed_at to now
        3. Calculates and sets password_expires_at
        4. Clears force_password_change flag
        5. Adds old password to history

        Args:
            user: User object
            new_hashed_password: Already hashed new password
        """
        # Add current password to history before updating
        if user.hashed_password:
            await PasswordExpirationService.add_to_password_history(
                user, user.hashed_password
            )

        # Update password and timestamps
        user.hashed_password = new_hashed_password
        user.password_changed_at = datetime.now(timezone.utc)
        user.force_password_change = False
        user.password_expiration_notified_at = None

        # Calculate and set expiration date
        user.password_expires_at = (
            await PasswordExpirationService.calculate_expiration_date(user)
        )

        await user.save()

        logger.info(
            f"Updated password for user {user.username}, "
            f"expires_at: {user.password_expires_at}"
        )
