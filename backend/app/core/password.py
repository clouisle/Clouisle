"""
密码强度验证模块
基于站点设置动态验证密码强度
"""

import re
from typing import List, Tuple, Optional

from app.models.site_setting import SiteSetting


async def validate_password(
    password: str, user: Optional["User"] = None  # noqa: F821
) -> Tuple[bool, List[str]]:
    """
    根据站点设置验证密码强度

    Args:
        password: 待验证的密码
        user: 可选的用户对象，用于检查密码历史

    Returns:
        Tuple[bool, List[str]]: (是否通过验证, 错误消息列表)
    """
    errors = []

    # 获取密码策略设置
    min_length = await SiteSetting.get_value("min_password_length", 8)
    require_uppercase = await SiteSetting.get_value("require_uppercase", True)
    require_number = await SiteSetting.get_value("require_number", True)
    require_special = await SiteSetting.get_value("require_special_char", False)

    # 验证长度
    if len(password) < min_length:
        errors.append(f"password_min_length:{min_length}")

    # 验证大写字母
    if require_uppercase and not re.search(r"[A-Z]", password):
        errors.append("password_require_uppercase")

    # 验证数字
    if require_number and not re.search(r"\d", password):
        errors.append("password_require_number")

    # 验证特殊字符
    if require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("password_require_special")

    # 检查密码历史（如果提供了用户对象）
    if user:
        from app.services.password_expiration import PasswordExpirationService

        is_recently_used = await PasswordExpirationService.check_password_history(
            user, password
        )
        if is_recently_used:
            errors.append("password_recently_used")

    return len(errors) == 0, errors


def get_password_requirements_sync(
    min_length: int = 8,
    require_uppercase: bool = True,
    require_number: bool = True,
    require_special: bool = False,
) -> List[str]:
    """
    获取密码要求列表（同步版本，用于 schema 验证）
    """
    requirements = [f"至少 {min_length} 个字符"]
    if require_uppercase:
        requirements.append("至少一个大写字母")
    if require_number:
        requirements.append("至少一个数字")
    if require_special:
        requirements.append("至少一个特殊字符")
    return requirements
