"""
验证码服务 - 点击式人机验证实现
"""

import json
import math
import random
import secrets
import time
from typing import Any, Optional, Tuple

from app.core.redis import get_redis

MAX_POINTER_POINTS = 80
MIN_POINTER_POINTS = 5
MIN_ELAPSED_MS = 450
MAX_POINTER_SPEED_PX_PER_MS = 5
MIN_POINTER_DISTANCE_PX = 30
MIN_POINTER_SPAN_PX = 12
MIN_DIRECTION_CHANGES = 2
MIN_SPEED_VARIANCE = 0.001
MAX_CLICK_DRIFT_PX = 16
MAX_CAPTCHA_AREA_WIDTH = 800
MAX_CAPTCHA_AREA_HEIGHT = 240

# 验证码 key 前缀
CAPTCHA_PREFIX = "captcha:"
CAPTCHA_PROOF_PREFIX = "captcha-proof:"
CAPTCHA_TTL = 300  # 5 分钟过期
CLICK_OPTIONS = ["human_check"]


def _is_human_pointer_trajectory(
    pointer: list[dict[str, Any]], elapsed_ms: int
) -> bool:
    """Validate a lightweight pointer trace before issuing a captcha proof."""
    if elapsed_ms < MIN_ELAPSED_MS or elapsed_ms > CAPTCHA_TTL * 1000:
        return False
    if len(pointer) < MIN_POINTER_POINTS:
        return False

    points: list[tuple[float, float, int, str]] = []
    for point in pointer[:MAX_POINTER_POINTS]:
        try:
            x = float(point["x"])
            y = float(point["y"])
            t = int(point["t"])
        except (KeyError, TypeError, ValueError):
            return False
        if t < 0 or t > elapsed_ms:
            return False
        event = str(point.get("event", "move"))
        points.append((x, y, t, event))

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    if (
        max(xs) - min(xs) < MIN_POINTER_SPAN_PX
        and max(ys) - min(ys) < MIN_POINTER_SPAN_PX
    ):
        return False

    click_points = [point for point in points if point[3] in {"down", "up", "click"}]
    if len(click_points) < 2:
        return False
    down_x, down_y, _down_t, _down_event = click_points[-2]
    up_x, up_y, _up_t, _up_event = click_points[-1]
    if math.dist((down_x, down_y), (up_x, up_y)) > MAX_CLICK_DRIFT_PX:
        return False
    if not (
        0 <= up_x <= MAX_CAPTCHA_AREA_WIDTH and 0 <= up_y <= MAX_CAPTCHA_AREA_HEIGHT
    ):
        return False

    distance = 0.0
    direction_changes = 0
    previous_angle: float | None = None
    speeds: list[float] = []
    previous = points[0]

    for current in points[1:]:
        x, y, t, _event = current
        px, py, pt, _previous_event = previous
        dt = t - pt
        if dt < 0:
            return False
        step = math.dist((x, y), (px, py))
        if dt == 0:
            previous = current
            continue
        speed = step / dt
        if speed > MAX_POINTER_SPEED_PX_PER_MS:
            return False
        if step > 0:
            angle = math.atan2(y - py, x - px)
            if previous_angle is not None and abs(angle - previous_angle) > 0.25:
                direction_changes += 1
            previous_angle = angle
            speeds.append(speed)
        distance += step
        previous = current

    if distance < MIN_POINTER_DISTANCE_PX:
        return False
    if direction_changes < MIN_DIRECTION_CHANGES:
        return False
    if len(speeds) < 3 or max(speeds) - min(speeds) < MIN_SPEED_VARIANCE:
        return False
    return True


async def generate_captcha() -> Tuple[str, str]:
    """
    生成点击式验证码挑战

    Returns:
        Tuple[captcha_id, challenge]: 验证码ID、公开挑战描述符
    """
    captcha_id = secrets.token_urlsafe(16)
    target_option = CLICK_OPTIONS[random.randrange(len(CLICK_OPTIONS))]
    challenge = json.dumps(
        {
            "type": "click-choice",
            "options": CLICK_OPTIONS,
            "target": target_option,
            "prompt": "select_target",
            "created_at": int(time.time() * 1000),
        },
        separators=(",", ":"),
    )

    r = await get_redis()
    key = f"{CAPTCHA_PREFIX}{captcha_id}"
    await r.setex(key, CAPTCHA_TTL, target_option)

    return captcha_id, challenge


async def create_captcha_proof(
    captcha_id: str,
    challenge: str,
    clicked_option: str,
    elapsed_ms: int,
    pointer: list[dict[str, Any]],
) -> Optional[str]:
    """Issue a private one-time proof after a valid click interaction."""
    if not captcha_id or not challenge or not clicked_option:
        return None
    if not _is_human_pointer_trajectory(pointer, elapsed_ms):
        return None

    try:
        public_challenge: dict[str, Any] = json.loads(challenge)
    except json.JSONDecodeError:
        return None

    if public_challenge.get("type") != "click-choice":
        return None
    options = public_challenge.get("options")
    if not isinstance(options, list) or clicked_option not in options:
        return None

    # Client-reported elapsed_ms is advisory only. Redis TTL/server state is authoritative.
    _ = elapsed_ms

    r = await get_redis()
    key = f"{CAPTCHA_PREFIX}{captcha_id}"
    stored_target_index = await r.get(key)
    await r.delete(key)

    if stored_target_index is None:
        return None
    if not secrets.compare_digest(clicked_option, stored_target_index):
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
