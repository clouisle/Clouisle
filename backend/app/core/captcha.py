"""
验证码服务 - 点击式人机验证实现
"""

import secrets
from typing import Optional, Tuple

from app.core.redis import get_redis

# 验证码 key 前缀
CAPTCHA_PREFIX = "captcha:"
CAPTCHA_TTL = 300  # 5 分钟过期


async def generate_captcha() -> Tuple[str, str, str]:
    """
    生成点击式验证码

    Returns:
        Tuple[captcha_id, challenge, token]: 验证码ID、前端点击令牌、校验令牌
    """
    captcha_id = secrets.token_urlsafe(16)
    token = secrets.token_urlsafe(24)

    r = await get_redis()
    key = f"{CAPTCHA_PREFIX}{captcha_id}"
    await r.setex(key, CAPTCHA_TTL, token)

    return captcha_id, token, token


async def verify_captcha(captcha_id: str, user_token: str) -> bool:
    """
    验证点击式验证码

    Args:
        captcha_id: 验证码 ID
        user_token: 用户点击后提交的令牌

    Returns:
        True 如果验证通过
    """
    if not captcha_id or not user_token:
        return False

    r = await get_redis()
    key = f"{CAPTCHA_PREFIX}{captcha_id}"

    # 获取并删除（一次性使用）
    stored_token = await r.get(key)
    await r.delete(key)

    if stored_token is None:
        return False

    return secrets.compare_digest(user_token.strip(), stored_token.strip())


async def get_captcha_answer(captcha_id: str) -> Optional[str]:
    """
    获取验证码答案（仅用于调试）
    """
    r = await get_redis()
    key = f"{CAPTCHA_PREFIX}{captcha_id}"
    return await r.get(key)
