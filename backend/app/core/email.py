"""
邮件服务模块
基于站点设置发送邮件
"""

import logging
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import aiosmtplib

from app.core.i18n import t, normalize_language
from app.core.redis import get_redis
from app.models.site_setting import SiteSetting

logger = logging.getLogger(__name__)

# Redis key 前缀
VERIFICATION_CODE_PREFIX = "verify:code:"
VERIFICATION_TOKEN_PREFIX = "verify:token:"
EMAIL_COOLDOWN_PREFIX = "email:cooldown:"
# 批量邮件防刷前缀
BULK_EMAIL_RATE_PREFIX = "email:rate:bulk:"  # 管理员批量发送速率
RECIPIENT_EMAIL_RATE_PREFIX = "email:rate:recipient:"  # 单个收件人速率


async def get_smtp_config() -> dict:
    """获取 SMTP 配置"""
    return {
        "enabled": await SiteSetting.get_value("smtp_enabled", False),
        "host": await SiteSetting.get_value("smtp_host", ""),
        "port": await SiteSetting.get_value("smtp_port", 587),
        "encryption": await SiteSetting.get_value("smtp_encryption", "tls"),
        "username": await SiteSetting.get_value("smtp_username", ""),
        "password": await SiteSetting.get_value("smtp_password", ""),
        "from_name": await SiteSetting.get_value("email_from_name", "Clouisle"),
        "from_address": await SiteSetting.get_value("email_from_address", ""),
    }


async def send_email(
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> bool:
    """
    发送邮件

    Args:
        to_email: 收件人邮箱
        subject: 邮件主题
        body_text: 纯文本内容
        body_html: HTML 内容（可选）

    Returns:
        bool: 是否发送成功
    """
    config = await get_smtp_config()

    if not config["enabled"]:
        logger.warning("SMTP is not enabled, skipping email send")
        return False

    if not config["host"] or not config["from_address"]:
        logger.error("SMTP configuration incomplete")
        return False

    try:
        # 创建邮件
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{config['from_name']} <{config['from_address']}>"
        msg["To"] = to_email

        # 添加纯文本版本
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # 添加 HTML 版本
        if body_html:
            msg.attach(MIMEText(body_html, "html", "utf-8"))

        encryption = config["encryption"]
        use_tls = encryption == "ssl"
        start_tls = encryption == "tls"

        # 发送邮件
        await aiosmtplib.send(
            msg,
            hostname=config["host"],
            port=config["port"],
            username=config["username"] if config["username"] else None,
            password=config["password"] if config["password"] else None,
            use_tls=use_tls,
            start_tls=start_tls,
        )

        logger.info(f"Email sent successfully to {to_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


async def generate_verification_code(
    email: str, purpose: str = "register"
) -> tuple[str, str]:
    """
    生成邮箱验证码和 token

    Args:
        email: 邮箱地址
        purpose: 用途 (register, reset_password, etc.)

    Returns:
        Tuple[str, str]: (6位验证码, UUID token)
    """
    r = await get_redis()

    # 生成 6 位数字验证码
    code = "".join([str(secrets.randbelow(10)) for _ in range(6)])

    # 生成 UUID token（用于链接验证）
    token = secrets.token_urlsafe(32)

    # 存储验证码，10 分钟过期
    code_key = f"{VERIFICATION_CODE_PREFIX}{email}:{purpose}"
    token_key = f"{VERIFICATION_TOKEN_PREFIX}{token}"

    # 存储结构：code -> email:purpose, token -> email:purpose
    await r.setex(code_key, 600, f"{code}:{token}")
    await r.setex(token_key, 600, f"{email}:{purpose}")

    return code, token


async def verify_code(email: str, code: str, purpose: str = "register") -> bool:
    """
    验证邮箱验证码

    Returns:
        bool: 验证是否成功
    """
    r = await get_redis()
    code_key = f"{VERIFICATION_CODE_PREFIX}{email}:{purpose}"

    stored = await r.get(code_key)
    if not stored:
        return False

    stored_code, _ = stored.split(":")
    if stored_code != code:
        return False

    # 验证成功，删除验证码
    await r.delete(code_key)
    return True


async def verify_token(token: str) -> Optional[tuple[str, str]]:
    """
    验证 token

    Returns:
        Optional[Tuple[str, str]]: (email, purpose) 或 None
    """
    r = await get_redis()
    token_key = f"{VERIFICATION_TOKEN_PREFIX}{token}"

    stored = await r.get(token_key)
    if not stored:
        return None

    email, purpose = stored.split(":")

    # 删除 token 和对应的 code
    code_key = f"{VERIFICATION_CODE_PREFIX}{email}:{purpose}"
    await r.delete(token_key)
    await r.delete(code_key)

    return email, purpose


async def check_email_cooldown(
    email: str, purpose: str = "register"
) -> tuple[bool, int]:
    """
    检查邮件发送冷却时间

    Returns:
        Tuple[bool, int]: (是否可以发送, 剩余冷却秒数)
    """
    r = await get_redis()
    cooldown_key = f"{EMAIL_COOLDOWN_PREFIX}{email}:{purpose}"

    ttl = await r.ttl(cooldown_key)
    if ttl > 0:
        return False, ttl

    return True, 0


async def set_email_cooldown(email: str, purpose: str = "register", seconds: int = 60):
    """
    设置邮件发送冷却时间
    """
    r = await get_redis()
    cooldown_key = f"{EMAIL_COOLDOWN_PREFIX}{email}:{purpose}"
    await r.setex(cooldown_key, seconds, "1")


async def send_verification_email(
    email: str,
    code: str,
    token: str,
    purpose: str = "register",
    locale: str | None = None,
):
    """
    发送验证码邮件
    """
    from app.core.email_templates import (
        render_reset_password_email,
        render_verification_email,
    )

    site_name = await SiteSetting.get_value("site_name", "Clouisle")
    site_url = await SiteSetting.get_value("site_url", "")
    locale = normalize_language(
        locale or await SiteSetting.get_value("default_language", "en")
    )

    # 根据用途选择模板
    if purpose == "register":
        subject = t("email_verification_subject", lang=locale, site_name=site_name)
        verify_url = f"{site_url}/verify?token={token}" if site_url else None
        body_text, body_html = render_verification_email(
            site_name,
            code,
            verify_url,
            locale=locale,
        )

    elif purpose == "reset_password":
        subject = t("email_reset_password_subject", lang=locale, site_name=site_name)
        verify_url = f"{site_url}/reset-password?token={token}" if site_url else None
        body_text, body_html = render_reset_password_email(
            site_name,
            code,
            verify_url,
            locale=locale,
        )
    else:
        subject = t("email_code_subject", lang=locale, site_name=site_name)
        body_text = t("email_code_body_text", lang=locale, code=code)
        body_html = None

    await send_email(email, subject, body_text, body_html)


# ============ 批量邮件防刷保护 ============


async def check_bulk_email_rate(
    sender_id: str, max_per_hour: int = 100
) -> tuple[bool, int, int]:
    """
    检查管理员批量发送邮件的速率限制

    Args:
        sender_id: 发送者用户ID
        max_per_hour: 每小时最大发送数量

    Returns:
        Tuple[bool, int, int]: (是否允许发送, 已发送数量, 剩余数量)
    """
    r = await get_redis()
    key = f"{BULK_EMAIL_RATE_PREFIX}{sender_id}"

    # 获取当前计数
    count = await r.get(key)
    current_count = int(count) if count else 0

    if current_count >= max_per_hour:
        return False, current_count, 0

    return True, current_count, max_per_hour - current_count


async def increment_bulk_email_count(sender_id: str, increment: int = 1):
    """
    增加管理员发送邮件计数

    Args:
        sender_id: 发送者用户ID
        increment: 增加的数量
    """
    r = await get_redis()
    key = f"{BULK_EMAIL_RATE_PREFIX}{sender_id}"

    # 使用 INCRBY 增加计数
    new_count = await r.incrby(key, increment)

    # 如果是新创建的 key，设置 1 小时过期
    if new_count == increment:
        await r.expire(key, 3600)


async def check_recipient_email_rate(
    email: str, max_per_day: int = 5
) -> tuple[bool, int]:
    """
    检查单个收件人的邮件接收速率限制（防止对单个用户发送过多邮件）

    Args:
        email: 收件人邮箱
        max_per_day: 每天最大接收数量

    Returns:
        Tuple[bool, int]: (是否允许发送, 已接收数量)
    """
    r = await get_redis()
    key = f"{RECIPIENT_EMAIL_RATE_PREFIX}{email}"

    count = await r.get(key)
    current_count = int(count) if count else 0

    if current_count >= max_per_day:
        return False, current_count

    return True, current_count


async def increment_recipient_email_count(email: str):
    """
    增加收件人邮件接收计数

    Args:
        email: 收件人邮箱
    """
    r = await get_redis()
    key = f"{RECIPIENT_EMAIL_RATE_PREFIX}{email}"

    new_count = await r.incr(key)

    # 如果是新创建的 key，设置 24 小时过期
    if new_count == 1:
        await r.expire(key, 86400)


async def filter_rate_limited_recipients(
    emails: list[str], max_per_day: int = 5
) -> tuple[list[str], list[str]]:
    """
    过滤超出速率限制的收件人

    Args:
        emails: 收件人邮箱列表
        max_per_day: 每天最大接收数量

    Returns:
        Tuple[list[str], list[str]]: (可发送的邮箱列表, 被限制的邮箱列表)
    """
    allowed = []
    limited = []

    for email in emails:
        can_send, _ = await check_recipient_email_rate(email, max_per_day)
        if can_send:
            allowed.append(email)
        else:
            limited.append(email)

    return allowed, limited
