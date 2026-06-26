from datetime import timedelta
from typing import Any, Optional

import jwt
from fastapi import APIRouter, Depends, Request, BackgroundTasks, Form

from app.api import deps
from app.core import security
from app.core.config import settings
from app.core.redis import (
    add_token_to_blacklist,
    invalidate_user_session,
    set_user_session,
)
from app.core.password import validate_password
from app.core.login_security import (
    check_account_locked,
    record_failed_login,
    reset_login_attempts,
)
from app.core.login_anomaly import (
    check_login_anomaly,
    record_login,
)
from app.core.email import (
    generate_verification_code,
    verify_code,
    verify_token,
    check_email_cooldown,
    set_email_cooldown,
    send_verification_email,
)
from app.core.captcha import create_captcha_proof, generate_captcha, verify_captcha
from app.core.timezone import now_utc
from app.core.i18n import t, get_default_language
from app.models.user import User
from app.models.site_setting import SiteSetting
from app.schemas.token import Token
from app.schemas.user import UserCreate, User as UserSchema
from app.api.v1.endpoints.users import serialize_user_with_sso
from app.schemas.captcha import (
    CaptchaClickRequest,
    CaptchaProofResponse,
    CaptchaResponse,
)
from app.schemas.verification import (
    SendVerificationRequest,
    VerifyCodeRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    ResetPasswordConfirmRequest,
    VerificationResponse,
)
from app.schemas.response import Response, ResponseCode, BusinessError, success
from app.services.audit_log import AuditLogService
from app.services.auto_notification import AutoNotificationService
from app.services.password_expiration import PasswordExpirationService
from app.models.notification import AutoNotificationType, NotificationLevel
from app.core import totp_security
from app.services import totp as totp_service

router = APIRouter()


@router.get("/captcha", response_model=Response[CaptchaResponse])
async def get_captcha() -> Any:
    """
    Get a new click captcha for human verification
    """
    captcha_id, challenge = await generate_captcha()
    return success(data=CaptchaResponse(captcha_id=captcha_id, challenge=challenge))


@router.post("/captcha/click", response_model=Response[CaptchaProofResponse])
async def complete_captcha_click(payload: CaptchaClickRequest) -> Any:
    """Exchange a valid click interaction for a private one-time proof."""
    proof = await create_captcha_proof(
        payload.captcha_id,
        payload.challenge,
        payload.clicked_option,
        payload.elapsed_ms,
    )
    if not proof:
        raise BusinessError(
            code=ResponseCode.CAPTCHA_INVALID,
            msg_key="captcha_invalid",
        )
    return success(
        data=CaptchaProofResponse(
            captcha_id=payload.captcha_id,
            captcha_token=proof,
        )
    )


async def validate_human_verification(
    captcha_id: Optional[str], captcha_token: Optional[str]
) -> None:
    """Validate the one-time click captcha token."""
    if not captcha_id or not captcha_token:
        raise BusinessError(
            code=ResponseCode.CAPTCHA_REQUIRED,
            msg_key="captcha_required",
        )

    is_valid = await verify_captcha(captcha_id, captcha_token)
    if not is_valid:
        raise BusinessError(
            code=ResponseCode.CAPTCHA_INVALID,
            msg_key="captcha_invalid",
        )


@router.post("/login/access-token", response_model=Response[Token])
async def login_access_token(
    request: Request,
    identifier: str = Form(..., alias="username"),
    password: str = Form(...),
    captcha_id: Optional[str] = Form(None),
    captcha_token: Optional[str] = Form(None),
    captcha_answer: Optional[str] = Form(None),
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    # Check if password login is allowed when SSO is enabled
    sso_enabled = await SiteSetting.get_value("sso_enabled", False)
    allow_password = await SiteSetting.get_value("sso_allow_password_login", True)

    if sso_enabled and not allow_password:
        raise BusinessError(
            code=ResponseCode.PASSWORD_LOGIN_DISABLED,
            msg_key="password_login_disabled",
        )

    # Check if captcha is enabled and verify it
    enable_captcha = await SiteSetting.get_value("enable_captcha", False)
    if enable_captcha:
        await validate_human_verification(captcha_id, captcha_token or captcha_answer)

    # Allow login by username or email
    if "@" in identifier:
        user = await User.filter(email__iexact=identifier).first()
    else:
        user = await User.filter(username=identifier).first()

    if not user:
        # 记录失败的登录（用户不存在）
        await AuditLogService.log(
            user=None,
            action="login_failed",
            resource_type="user",
            resource_id=None,
            resource_name=identifier,
            operation="read",
            status="failed",
            request=request,
            error_message="user_not_found",
        )
        raise BusinessError(
            code=ResponseCode.INVALID_CREDENTIALS,
            msg_key="incorrect_email_or_password",
        )

    # Check if account is locked
    is_locked, remaining_seconds = await check_account_locked(user)
    if is_locked:
        raise BusinessError(
            code=ResponseCode.ACCOUNT_LOCKED,
            msg_key="account_locked",
            data={"remaining_seconds": remaining_seconds},
        )

    # Check if user has a password set (SSO users may not have passwords)
    if not user.hashed_password or user.hashed_password == "":
        # 记录失败的登录（SSO 用户尝试密码登录）
        await AuditLogService.log(
            user=user,
            action="login_failed",
            resource_type="user",
            resource_id=user.id,
            resource_name=user.username,
            operation="read",
            status="failed",
            request=request,
            error_message="sso_user_no_password",
        )
        raise BusinessError(
            code=ResponseCode.INVALID_CREDENTIALS,
            msg_key="incorrect_email_or_password",
        )

    if not security.verify_password(password, user.hashed_password):
        # Record failed attempt
        locked, remaining_attempts, lockout_seconds = await record_failed_login(user)

        # 记录失败的登录（密码错误）
        await AuditLogService.log(
            user=user,
            action="login_failed",
            resource_type="user",
            resource_id=user.id,
            resource_name=user.username,
            operation="read",
            status="failed",
            request=request,
            error_message="incorrect_password",
            metadata={"remaining_attempts": remaining_attempts},
        )

        if locked:
            # 发送账户锁定通知
            await AutoNotificationService.send_to_user(
                notification_type=AutoNotificationType.SECURITY_ACCOUNT_LOCKED,
                user_id=user.id,
                title=t("notify_account_locked_title", lang=user.locale),
                content=t(
                    "notify_account_locked_content",
                    lang=user.locale,
                    lockout_minutes=(lockout_seconds or 0) // 60,
                ),
                level=NotificationLevel.HIGH,
            )
            raise BusinessError(
                code=ResponseCode.ACCOUNT_LOCKED,
                msg_key="account_locked_after_attempts",
                data={"lockout_seconds": lockout_seconds},
            )

        raise BusinessError(
            code=ResponseCode.INVALID_CREDENTIALS,
            msg_key="incorrect_email_or_password",
            data={"remaining_attempts": remaining_attempts},
        )

    if not user.is_active:
        raise BusinessError(
            code=ResponseCode.INACTIVE_USER,
            msg_key=(
                "pending_approval_user"
                if getattr(user, "approval_status", "approved") == "pending"
                else "inactive_user"
            ),
        )

    # Check if TOTP is enabled for this user
    if user.totp_enabled:
        # Create temporary token (5-minute expiration) for TOTP verification
        temp_token = security.create_access_token(
            user.id, expires_delta=timedelta(minutes=5)
        )
        return success(
            data={
                "requires_totp": True,
                "temp_token": temp_token,
            },
            msg_key="totp_required",
        )

    # Check if TOTP is required by system settings
    require_totp = await SiteSetting.get_value("require_totp", False)
    if require_totp and not user.totp_enabled:
        # Create temporary token for TOTP setup
        temp_token = security.create_access_token(
            user.id, expires_delta=timedelta(minutes=30)
        )
        return success(
            data={
                "requires_totp_setup": True,
                "temp_token": temp_token,
            },
            msg_key="totp_setup_required",
        )

    # Check email verification if required
    email_verification = await SiteSetting.get_value("email_verification", True)
    if email_verification and not user.email_verified and not user.is_superuser:
        raise BusinessError(
            code=ResponseCode.EMAIL_NOT_VERIFIED,
            msg_key="email_not_verified",
            data={"email": user.email},
        )

    # Check password expiration and force password change
    is_exempt = await PasswordExpirationService.is_user_exempt(user)
    is_expired = await PasswordExpirationService.is_password_expired(user)
    force_change_required = user.force_password_change and not is_exempt

    if is_expired and not is_exempt:
        # Set force_password_change flag if not already set
        if not user.force_password_change:
            user.force_password_change = True
            await user.save()
        force_change_required = True

    # Reset failed login attempts on successful login
    await reset_login_attempts(user)

    # Check for login anomaly (new IP or device)
    client_ip = AuditLogService.get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    is_anomaly, anomaly_details = await check_login_anomaly(
        user_id=user.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # Record this login for future anomaly detection
    await record_login(
        user_id=user.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # Send anomaly notification if detected
    if is_anomaly:
        await AutoNotificationService.send_to_user(
            notification_type=AutoNotificationType.SECURITY_LOGIN_ANOMALY,
            user_id=user.id,
            title=t("notify_login_anomaly_title", lang=user.locale),
            content=t(
                "notify_login_anomaly_content",
                lang=user.locale,
                ip_address=anomaly_details.get("ip_address", "unknown"),
                login_time=anomaly_details.get("login_time", ""),
                user_agent=anomaly_details.get("user_agent", "Unknown")[:100],
            ),
            level=NotificationLevel.HIGH,
            data=anomaly_details,
        )

    # Update last login time
    user.last_login = now_utc()
    await user.save()

    # Get session timeout from settings
    session_timeout_days = await SiteSetting.get_value("session_timeout_days", 7)
    access_token_expires = timedelta(days=session_timeout_days)
    expires_in_seconds = int(access_token_expires.total_seconds())

    # Check single session mode
    single_session = await SiteSetting.get_value("single_session", False)
    if single_session:
        # Invalidate previous session (kick out old login)
        # 只需要短暂保存在黑名单中（5秒），因为主要通过 Redis 会话检查来拦截
        await invalidate_user_session(str(user.id), token_expires_in=5)

    # Create new token
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )

    # Store session if single session mode is enabled
    if single_session:
        await set_user_session(str(user.id), access_token, expires_in_seconds)

    # 记录成功的登录
    await AuditLogService.log(
        user=user,
        action="login_success",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        operation="read",
        status="success",
        request=request,
    )

    # Check if password is expiring soon
    should_warn = await PasswordExpirationService.should_warn_user(user)
    days_remaining = await PasswordExpirationService.days_until_expiration(user)

    token_data: dict[str, str | bool] = {
        "access_token": access_token,
        "token_type": "bearer",
    }

    # Add force password change flag if needed
    if force_change_required:
        token_data["force_password_change"] = True
        token_data["reason"] = "expired" if is_expired else "force"
        return success(
            data=token_data,
            msg_key="login_successful_change_password_required",
        )

    # Add password expiration warning to response metadata if needed
    if should_warn and days_remaining is not None:
        return success(
            data=token_data,
            msg_key="login_successful",
        )
    else:
        return success(data=token_data, msg_key="login_successful")


@router.post("/login/verify-totp", response_model=Response[Token])
async def verify_totp(
    request: Request,
    temp_token: str = Form(...),
    code: str = Form(...),
    is_backup_code: bool = Form(False),
) -> Any:
    """
    Verify TOTP code or backup code and exchange temp token for full access token
    """
    # Verify temp token
    try:
        payload = jwt.decode(
            temp_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get("sub")
        if not user_id:
            raise BusinessError(
                code=ResponseCode.INVALID_TOKEN,
                msg_key="invalid_token",
            )
    except jwt.ExpiredSignatureError:
        raise BusinessError(
            code=ResponseCode.TOKEN_EXPIRED,
            msg_key="totp_setup_expired",
        )
    except jwt.PyJWTError:
        raise BusinessError(
            code=ResponseCode.INVALID_TOKEN,
            msg_key="invalid_token",
        )

    # Get user
    user = await User.get_or_none(id=user_id)
    if not user or not user.totp_enabled:
        raise BusinessError(
            code=ResponseCode.TOTP_NOT_ENABLED,
            msg_key="totp_not_enabled",
        )

    # Check rate limiting
    is_locked, remaining_seconds = await totp_security.check_totp_rate_limit(
        str(user.id)
    )
    if is_locked:
        raise BusinessError(
            code=ResponseCode.TOTP_RATE_LIMITED,
            msg_key="totp_rate_limited",
            data={"seconds": remaining_seconds},
        )

    # Verify code
    is_valid = False
    remaining_codes = 0

    if is_backup_code:
        # Verify backup code
        is_valid, remaining_codes = totp_service.verify_backup_code(user, code)
        if is_valid:
            await user.save()  # Save updated backup codes
            # Log backup code usage
            await AuditLogService.log(
                user=user,
                action="use_backup_code",
                resource_type="user",
                resource_id=user.id,
                resource_name=user.username,
                operation="read",
                status="success",
                request=request,
                metadata={"remaining_codes": remaining_codes},
            )
    else:
        # Verify TOTP code
        if user.totp_secret is None:
            raise BusinessError(
                code=ResponseCode.TOTP_NOT_ENABLED,
                msg_key="totp_not_enabled",
            )
        secret = totp_service.decrypt_secret(user.totp_secret)
        is_valid = totp_service.verify_totp_code(secret, code)

    if not is_valid:
        # Record failed attempt
        (
            locked,
            remaining_attempts,
            lockout_seconds,
        ) = await totp_security.record_totp_failure(str(user.id))

        # Log failed verification
        await AuditLogService.log(
            user=user,
            action="verify_totp_failed",
            resource_type="user",
            resource_id=user.id,
            resource_name=user.username,
            operation="read",
            status="failed",
            request=request,
            metadata={"remaining_attempts": remaining_attempts},
        )

        if locked:
            raise BusinessError(
                code=ResponseCode.TOTP_RATE_LIMITED,
                msg_key="totp_rate_limited",
                data={"seconds": lockout_seconds},
            )

        raise BusinessError(
            code=ResponseCode.TOTP_INVALID,
            msg_key="totp_invalid",
        )

    # Reset TOTP attempts on success
    await totp_security.reset_totp_attempts(str(user.id))

    # Reset login attempts
    await reset_login_attempts(user)

    # Check password expiration and force password change
    is_exempt = await PasswordExpirationService.is_user_exempt(user)
    is_expired = await PasswordExpirationService.is_password_expired(user)
    force_change_required = user.force_password_change and not is_exempt

    if is_expired and not is_exempt:
        if not user.force_password_change:
            user.force_password_change = True
            await user.save()
        force_change_required = True

    # Check for login anomaly
    client_ip = AuditLogService.get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    is_anomaly, anomaly_details = await check_login_anomaly(
        user_id=user.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # Record this login
    await record_login(
        user_id=user.id,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # Send anomaly notification if detected
    if is_anomaly:
        await AutoNotificationService.send_to_user(
            notification_type=AutoNotificationType.SECURITY_LOGIN_ANOMALY,
            user_id=user.id,
            title=t("notify_login_anomaly_title", lang=user.locale),
            content=t(
                "notify_login_anomaly_content",
                lang=user.locale,
                ip_address=anomaly_details.get("ip_address", "unknown"),
                login_time=anomaly_details.get("login_time", ""),
                user_agent=anomaly_details.get("user_agent", "Unknown")[:100],
            ),
            level=NotificationLevel.HIGH,
            data=anomaly_details,
        )

    # Update last login time
    user.last_login = now_utc()
    await user.save()

    # Get session timeout from settings
    session_timeout_days = await SiteSetting.get_value("session_timeout_days", 7)
    access_token_expires = timedelta(days=session_timeout_days)
    expires_in_seconds = int(access_token_expires.total_seconds())

    # Check single session mode
    single_session = await SiteSetting.get_value("single_session", False)
    if single_session:
        await invalidate_user_session(str(user.id), token_expires_in=5)

    # Create new token
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )

    # Store session if single session mode is enabled
    if single_session:
        await set_user_session(str(user.id), access_token, expires_in_seconds)

    # Log successful TOTP verification
    await AuditLogService.log(
        user=user,
        action="verify_totp_success",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        operation="read",
        status="success",
        request=request,
    )

    # Log successful login
    await AuditLogService.log(
        user=user,
        action="login_success",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        operation="read",
        status="success",
        request=request,
    )

    # Check if password is expiring soon
    should_warn = await PasswordExpirationService.should_warn_user(user)
    days_remaining = await PasswordExpirationService.days_until_expiration(user)

    token_data: dict[str, str | bool] = {
        "access_token": access_token,
        "token_type": "bearer",
    }

    # Add force password change flag if needed
    if force_change_required:
        token_data["force_password_change"] = True
        token_data["reason"] = "expired" if is_expired else "force"
        return success(
            data=token_data,
            msg_key="login_successful_change_password_required",
        )

    # Add password expiration warning to response metadata if needed
    if should_warn and days_remaining is not None:
        return success(
            data=token_data,
            msg_key="login_successful",
        )
    else:
        return success(data=token_data, msg_key="totp_verification_success")


@router.post("/logout", response_model=Response[None])
async def logout(
    request: Request,
    token: str = Depends(deps.reusable_oauth2),
) -> Any:
    """
    Logout - invalidate the current token by adding it to blacklist
    """
    from app.core.redis import clear_user_session

    user = None
    try:
        # 解析 token 获取过期时间和用户 ID
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        exp = payload.get("exp", 0)
        user_id = payload.get("sub")

        # 获取用户信息用于审计日志
        if user_id:
            user = await User.get_or_none(id=user_id)

        # 计算剩余有效期（秒）
        import time

        remaining = max(0, exp - int(time.time()))

        # 添加到黑名单，但只需要短暂保存（5秒）
        # 因为主要通过会话记录清除来拦截，黑名单只是辅助保护
        if remaining > 0:
            await add_token_to_blacklist(token, 5)  # 只保存5秒

        # 清除用户会话记录（如果是单一会话模式）
        if user_id:
            await clear_user_session(user_id)

        # 记录登出
        if user:
            await AuditLogService.log(
                user=user,
                action="logout",
                resource_type="user",
                resource_id=user.id,
                resource_name=user.username,
                operation="read",
                status="success",
                request=request,
            )
    except jwt.PyJWTError:
        # token 无效也返回成功（用户体验）
        pass

    return success(msg_key="logout_successful")


@router.post("/register", response_model=Response[UserSchema])
async def register(
    *,
    request: Request,
    user_in: UserCreate,
) -> Any:
    """
    Register a new user (open registration).
    The first registered user will be automatically promoted to Super Admin.
    """
    from app.models.user import Role
    from app.core.init_data import SUPER_ADMIN_ROLE

    # Check if this is the first user (first user bypasses all restrictions)
    user_count = await User.all().count()
    is_first_user = user_count == 0

    # Check if registration is allowed (skip for first user)
    if not is_first_user:
        allow_registration = await SiteSetting.get_value("allow_registration", True)
        if not allow_registration:
            raise BusinessError(
                code=ResponseCode.REGISTRATION_DISABLED,
                msg_key="registration_disabled",
            )
        enable_captcha = await SiteSetting.get_value("enable_captcha", False)
        if enable_captcha:
            await validate_human_verification(user_in.captcha_id, user_in.captcha_token)
        require_terms_acceptance = await SiteSetting.get_value(
            "require_terms_acceptance_on_register", False
        )
        if require_terms_acceptance and not user_in.terms_accepted:
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="terms_acceptance_required",
                data={"errors": {"terms_accepted": ["terms_acceptance_required"]}},
            )

    # Validate password strength
    password_valid, password_errors = await validate_password(user_in.password)
    if not password_valid:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="password_too_weak",
            data={"errors": {"password": password_errors}},
        )

    # Check if username exists
    existing_user = await User.filter(username=user_in.username).first()
    if existing_user:
        raise BusinessError(
            code=ResponseCode.USERNAME_EXISTS,
            msg_key="username_already_registered",
        )

    # Check if email exists
    existing_email = await User.filter(email=user_in.email).first()
    if existing_email:
        raise BusinessError(
            code=ResponseCode.EMAIL_EXISTS,
            msg_key="email_already_registered",
        )

    # Get registration settings
    require_approval = await SiteSetting.get_value("require_approval", False)
    email_verification = await SiteSetting.get_value("email_verification", True)
    default_language = await SiteSetting.get_value("default_language", "en")
    force_first_login = await SiteSetting.get_value(
        "force_password_change_first_login", False
    )

    # Create user
    hashed_password = security.get_password_hash(user_in.password)
    user = await User.create(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hashed_password,
        # First user is active and superuser
        # Others depend on require_approval setting
        is_active=is_first_user or not require_approval,
        approval_status="approved"
        if is_first_user or not require_approval
        else "pending",
        is_superuser=is_first_user,
        # First user auto-verified, or if email verification is disabled
        email_verified=is_first_user or not email_verification,
        locale=default_language,
        # Initialize password expiration fields
        password_changed_at=now_utc(),
        force_password_change=force_first_login and not is_first_user,
    )

    # Calculate and set password expiration date
    user.password_expires_at = (
        await PasswordExpirationService.calculate_expiration_date(user)
    )
    await user.save()

    # If first user, assign Super Admin role
    if is_first_user:
        super_admin_role = await Role.filter(name=SUPER_ADMIN_ROLE).first()
        if super_admin_role:
            await user.roles.add(super_admin_role)

        # Reload user with roles and sso_connections
        user = await User.get(id=user.id).prefetch_related(
            "roles__permissions", "sso_connections"
        )

        # 记录首个超级管理员注册
        await AuditLogService.log(
            user=user,
            action="register",
            resource_type="user",
            resource_id=user.id,
            resource_name=user.username,
            operation="create",
            status="success",
            request=request,
            metadata={"is_first_user": True, "is_superuser": True},
        )

        return success(
            data=await serialize_user_with_sso(user),
            msg_key="registration_successful_superadmin",
        )

    # Assign default role and team to new user
    from app.services.team_role_sync import assign_default_role, assign_default_team

    await assign_default_role(user)
    default_team_assigned = await assign_default_team(user)

    # Reload user with roles and sso_connections (empty but need to be lists)
    user = await User.get(id=user.id).prefetch_related(
        "roles__permissions", "sso_connections"
    )

    # 记录普通用户注册
    await AuditLogService.log(
        user=user,
        action="register",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        operation="create",
        status="success",
        request=request,
        metadata={
            "require_approval": require_approval,
            "email_verification": email_verification,
            "default_team_assigned": default_team_assigned,
        },
    )

    # Determine response message
    if require_approval:
        # 发送待审批通知给管理员（全局通知）
        default_lang = await get_default_language()
        await AutoNotificationService.send_global(
            notification_type=AutoNotificationType.USER_PENDING_APPROVAL,
            title=t("notify_user_pending_approval_title", lang=default_lang),
            content=t(
                "notify_user_pending_approval_content",
                lang=default_lang,
                username=user.username,
                email=user.email,
            ),
        )
        return success(
            data=await serialize_user_with_sso(user),
            msg_key="registration_pending_approval",
        )
    elif email_verification:
        return success(
            data=await serialize_user_with_sso(user),
            msg_key="registration_pending_verification",
        )
    else:
        return success(
            data=await serialize_user_with_sso(user), msg_key="registration_successful"
        )


@router.post("/send-verification", response_model=Response[None])
async def send_verification(
    *,
    data: SendVerificationRequest,
    background_tasks: BackgroundTasks,
) -> Any:
    """
    Send verification email
    """
    # Check SMTP is enabled
    smtp_enabled = await SiteSetting.get_value("smtp_enabled", False)
    if not smtp_enabled:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_FAILED,
            msg_key="smtp_not_configured",
        )

    # Check cooldown
    can_send, remaining = await check_email_cooldown(data.email, data.purpose)
    if not can_send:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_TOO_FREQUENT,
            msg_key="email_send_too_frequent",
            data={"remaining_seconds": remaining},
        )

    # Check if email exists (for register purpose, email should belong to a user)
    user = await User.filter(email=data.email).first()
    if data.purpose == "register":
        if not user:
            raise BusinessError(
                code=ResponseCode.NOT_FOUND,
                msg_key="email_not_found",
            )

        if user.email_verified:
            raise BusinessError(
                code=ResponseCode.VALIDATION_ERROR,
                msg_key="email_already_verified",
            )

    # Generate code and token
    code, token = await generate_verification_code(data.email, data.purpose)

    # Set cooldown
    await set_email_cooldown(data.email, data.purpose, 60)

    # Send email in background
    background_tasks.add_task(
        send_verification_email, data.email, code, token, data.purpose
    )

    return success(msg_key="verification_email_sent")


@router.post("/verify-email", response_model=Response[VerificationResponse])
async def verify_email_by_code(
    *,
    data: VerifyCodeRequest,
) -> Any:
    """
    Verify email by code
    """
    # Verify code
    is_valid = await verify_code(data.email, data.code, data.purpose)
    if not is_valid:
        raise BusinessError(
            code=ResponseCode.VERIFICATION_CODE_INVALID,
            msg_key="verification_code_invalid",
        )

    # Update user
    user = await User.filter(email=data.email).first()
    if user and data.purpose == "register":
        user.email_verified = True
        await user.save()

    return success(
        data=VerificationResponse(verified=True, email=data.email),
        msg_key="email_verified_success",
    )


@router.get("/verify", response_model=Response[VerificationResponse])
async def verify_email_by_token(
    token: str,
) -> Any:
    """
    Verify email by token (from email link)
    """
    result = await verify_token(token)
    if not result:
        raise BusinessError(
            code=ResponseCode.VERIFICATION_CODE_EXPIRED,
            msg_key="verification_token_invalid",
        )

    email, purpose = result

    # Update user
    user = await User.filter(email=email).first()
    if user and purpose == "register":
        user.email_verified = True
        await user.save()

    return success(
        data=VerificationResponse(verified=True, email=email),
        msg_key="email_verified_success",
    )


@router.post("/resend-verification", response_model=Response[None])
async def resend_verification(
    *,
    data: ResendVerificationRequest,
    background_tasks: BackgroundTasks,
) -> Any:
    """
    Resend verification email for registration
    """
    # Check SMTP is enabled
    smtp_enabled = await SiteSetting.get_value("smtp_enabled", False)
    if not smtp_enabled:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_FAILED,
            msg_key="smtp_not_configured",
        )

    # Check cooldown
    can_send, remaining = await check_email_cooldown(data.email, "register")
    if not can_send:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_TOO_FREQUENT,
            msg_key="email_send_too_frequent",
            data={"remaining_seconds": remaining},
        )

    # Find user
    user = await User.filter(email=data.email).first()
    if not user:
        # Don't reveal if email exists
        return success(msg_key="verification_email_sent")

    if user.email_verified:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="email_already_verified",
        )

    # Generate code and token
    code, token = await generate_verification_code(data.email, "register")

    # Set cooldown
    await set_email_cooldown(data.email, "register", 60)

    # Send email in background
    background_tasks.add_task(
        send_verification_email, data.email, code, token, "register"
    )

    return success(msg_key="verification_email_sent")


@router.post("/forgot-password", response_model=Response[None])
async def forgot_password(
    *,
    data: ResetPasswordRequest,
    background_tasks: BackgroundTasks,
) -> Any:
    """
    Send password reset email
    """
    # Check SMTP is enabled
    smtp_enabled = await SiteSetting.get_value("smtp_enabled", False)
    if not smtp_enabled:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_FAILED,
            msg_key="smtp_not_configured",
        )

    # Check cooldown
    can_send, remaining = await check_email_cooldown(data.email, "reset_password")
    if not can_send:
        raise BusinessError(
            code=ResponseCode.EMAIL_SEND_TOO_FREQUENT,
            msg_key="email_send_too_frequent",
            data={"remaining_seconds": remaining},
        )

    # Find user (don't reveal if email exists for security)
    user = await User.filter(email=data.email).first()
    if user:
        # Generate code and token
        code, token = await generate_verification_code(data.email, "reset_password")

        # Set cooldown
        await set_email_cooldown(data.email, "reset_password", 60)

        # Send email in background
        background_tasks.add_task(
            send_verification_email, data.email, code, token, "reset_password"
        )

    # Always return success to prevent email enumeration
    return success(msg_key="reset_password_email_sent")


@router.post("/reset-password", response_model=Response[None])
async def reset_password(
    *,
    request: Request,
    data: ResetPasswordConfirmRequest,
) -> Any:
    """
    Reset password with verification code or token
    """
    # Determine email based on auth method
    if data.token:
        # Token-based reset
        result = await verify_token(data.token)
        if not result:
            raise BusinessError(
                code=ResponseCode.VERIFICATION_CODE_INVALID,
                msg_key="verification_token_invalid",
            )
        email, purpose = result
        if purpose != "reset_password":
            raise BusinessError(
                code=ResponseCode.VERIFICATION_CODE_INVALID,
                msg_key="verification_token_invalid",
            )
    else:
        # Code-based reset
        assert data.email is not None and data.code is not None
        email = data.email
        is_valid = await verify_code(data.email, data.code, "reset_password")
        if not is_valid:
            raise BusinessError(
                code=ResponseCode.VERIFICATION_CODE_INVALID,
                msg_key="verification_code_invalid",
            )

    # Validate new password
    password_valid, password_errors = await validate_password(data.new_password)
    if not password_valid:
        raise BusinessError(
            code=ResponseCode.VALIDATION_ERROR,
            msg_key="password_too_weak",
            data={"errors": {"password": password_errors}},
        )

    # Find and update user
    user = await User.filter(email=email).first()
    if not user:
        raise BusinessError(
            code=ResponseCode.NOT_FOUND,
            msg_key="user_not_found",
        )

    # Update password with expiration logic
    new_hashed_password = security.get_password_hash(data.new_password)
    await PasswordExpirationService.update_password_with_expiration(
        user, new_hashed_password
    )

    # Reset login attempts
    user.failed_login_attempts = 0
    user.locked_until = None  # type: ignore[assignment]
    await user.save()

    # 记录密码重置
    await AuditLogService.log(
        user=user,
        action="reset_password",
        resource_type="user",
        resource_id=user.id,
        resource_name=user.username,
        operation="update",
        status="success",
        request=request,
    )

    return success(msg_key="password_reset_success")
