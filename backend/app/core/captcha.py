"""
验证码服务 - 点击式人机验证实现
"""

import json
import secrets
from typing import Any, Optional, Tuple

from app.core.redis import get_redis

# 验证码 key 前缀
CAPTCHA_PREFIX = "captcha:"
CAPTCHA_PROOF_PREFIX = "captcha-proof:"
CAPTCHA_TTL = 300  # 5 分钟过期
MIN_CLICK_ELAPSED_MS = 250


async def generate_captcha() -> Tuple[str, str]:
    """
    生成点击式验证码挑战

    Returns:
        Tuple[captcha_id, challenge]: 验证码ID、公开挑战描述符
    """
    captcha_id = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    challenge = json.dumps(
        {"type": "click", "nonce": nonce, "min_elapsed_ms": MIN_CLICK_ELAPSED_MS},
        separators=(",", ":"),
    )

    r = await get_redis()
    key = f"{CAPTCHA_PREFIX}{captcha_id}"
    await r.setex(key, CAPTCHA_TTL, nonce)

    return captcha_id, challenge


async def create_captcha_proof(
    captcha_id: str, challenge: str, click_nonce: str, elapsed_ms: int
) -> Optional[str]:
    """Issue a private one-time proof after a valid click interaction."""
    if not captcha_id or not challenge or not click_nonce:
        return None
    if elapsed_ms < MIN_CLICK_ELAPSED_MS:
        return None

    try:
        public_challenge: dict[str, Any] = json.loads(challenge)
    except json.JSONDecodeError:
        return None

    if public_challenge.get("type") != "click":
        return None

    r = await get_redis()
    key = f"{CAPTCHA_PREFIX}{captcha_id}"
    stored_nonce = await r.get(key)
    await r.delete(key)

    if stored_nonce is None:
        return None

    challenge_nonce = str(public_challenge.get("nonce", ""))
    if not challenge_nonce or not secrets.compare_digest(challenge_nonce, stored_nonce):
        return None
    if not secrets.compare_digest(click_nonce, stored_nonce):
        return None

    proof = secrets.token_urlsafe(24)
    proof_key = f"{CAPTCHA_PROOF_PREFIX}{captcha_id}"
    await r.setex(proof_key, CAPTCHA_TTL, proof)
    return proof


async def verify_captcha(captcha_id: str, user_token: str) -> bool:
    """
    验证点击式验证码证明

    Args:
        captcha_id: 验证码 ID
        user_token: 点击验证接口签发的一次性证明

    Returns:
        True 如果验证通过
    """
    if not captcha_id or not user_token:
        return False

    r = await get_redis()
    key = f"{CAPTCHA_PROOF_PREFIX}{captcha_id}"

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
    key = f"{CAPTCHA_PROOF_PREFIX}{captcha_id}"
    return await r.get(key)
