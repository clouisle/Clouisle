import jwt
from typing import Optional
from uuid import UUID
from fastapi import Depends, status, Header
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError

from app.core.config import settings
from app.core.redis import is_token_blacklisted
from app.core.timezone import now_utc
from app.core.i18n import set_language
from app.models.user import User
from app.models.api_key import APIKey
from app.schemas.token import TokenPayload
from app.schemas.response import ResponseCode, BusinessError

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token",
    auto_error=False,  # 不自动抛错，允许 API Key 认证
)


async def get_current_user(token: str = Depends(reusable_oauth2)) -> User:
    """获取当前用户（使用 JWT Token）"""
    return await _authenticate_jwt(token)


async def get_current_user_or_api_key(
    token: Optional[str] = Depends(reusable_oauth2),
    authorization: Optional[str] = Header(None),
) -> tuple[User, Optional[APIKey]]:
    """
    获取当前用户，支持 JWT Token 或 API Key 认证。
    返回: (user, api_key) - api_key 为 None 表示使用 JWT 认证
    """
    # 尝试从 Authorization header 获取 token
    auth_token = token
    if not auth_token and authorization:
        if authorization.startswith("Bearer "):
            auth_token = authorization[7:]

    if not auth_token:
        raise BusinessError(
            code=ResponseCode.UNAUTHORIZED,
            msg_key="not_authenticated",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # 检查是否是 API Key (以 clou_ 开头)
    user: User | None
    api_key: Optional[APIKey] = None

    if auth_token.startswith("clou_"):
        user, api_key = await _authenticate_api_key(auth_token)
    else:
        # 否则尝试 JWT 认证
        user = await _authenticate_jwt(auth_token)

    # Set language from user's locale preference
    if hasattr(user, "locale") and user.locale:
        set_language(user.locale)

    return user, api_key


async def _authenticate_api_key(api_key_str: str) -> tuple[User, APIKey]:
    """通过 API Key 认证"""
    # 获取 key prefix 来快速查找
    key_prefix = api_key_str[:12]

    # 查找可能匹配的 API Key
    api_keys = await APIKey.filter(
        key_prefix=key_prefix,
        is_active=True,
    ).prefetch_related("user", "user__roles__permissions", "agents")

    # 验证完整的 key
    matched_api_key = None
    for api_key in api_keys:
        if APIKey.verify_key(api_key_str, api_key.key_hash):
            matched_api_key = api_key
            break

    if not matched_api_key:
        raise BusinessError(
            code=ResponseCode.INVALID_TOKEN,
            msg_key="invalid_api_key",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # 检查是否过期
    if matched_api_key.expires_at and matched_api_key.expires_at < now_utc():
        raise BusinessError(
            code=ResponseCode.TOKEN_EXPIRED,
            msg_key="api_key_expired",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # 获取关联的用户
    user: User | None = matched_api_key.user
    if not user:
        user = (
            await User.filter(id=matched_api_key.user_id)
            .prefetch_related("roles__permissions")
            .first()
        )

    if not user or not user.is_active:
        raise BusinessError(
            code=ResponseCode.INACTIVE_USER,
            msg_key=(
                "pending_approval_user"
                if user and getattr(user, "approval_status", "approved") == "pending"
                else "inactive_user"
            ),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # 更新最后使用时间
    matched_api_key.last_used_at = now_utc()
    await matched_api_key.save(update_fields=["last_used_at"])

    return user, matched_api_key


async def _authenticate_jwt(token: str) -> User:
    """通过 JWT Token 认证"""
    # 检查 token 是否在黑名单中
    if await is_token_blacklisted(token):
        raise BusinessError(
            code=ResponseCode.INVALID_TOKEN,
            msg_key="token_revoked",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (jwt.PyJWTError, ValidationError):
        raise BusinessError(
            code=ResponseCode.INVALID_CREDENTIALS,
            msg_key="could_not_validate_credentials",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if token_data.sub is None:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    user = (
        await User.filter(id=token_data.sub)
        .prefetch_related("roles__permissions")
        .first()
    )
    if not user:
        raise BusinessError(
            code=ResponseCode.USER_NOT_FOUND,
            msg_key="user_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # 检查单一会话模式
    from app.models.site_setting import SiteSetting
    from app.core.redis import get_user_session

    single_session = await SiteSetting.get_value("single_session", False)
    if single_session:
        # 获取用户当前有效的会话 token
        current_session_token = await get_user_session(str(user.id))
        # 如果当前 token 不是最新的会话 token，则拒绝访问
        if current_session_token and current_session_token != token:
            raise BusinessError(
                code=ResponseCode.INVALID_TOKEN,
                msg_key="session_expired_new_login",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise BusinessError(
            code=ResponseCode.INACTIVE_USER,
            msg_key=(
                "pending_approval_user"
                if getattr(current_user, "approval_status", "approved") == "pending"
                else "inactive_user"
            ),
        )
    # Set language from user's locale preference
    if hasattr(current_user, "locale") and current_user.locale:
        set_language(current_user.locale)
    return current_user


async def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_superuser:
        raise BusinessError(
            code=ResponseCode.INSUFFICIENT_PRIVILEGES,
            msg_key="insufficient_privileges",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return current_user


async def get_current_user_optional(
    token: Optional[str] = Depends(reusable_oauth2),
    authorization: Optional[str] = Header(None),
) -> Optional[User]:
    """
    可选的用户认证。如果提供了有效的 token，返回用户；否则返回 None。
    不会抛出认证错误。
    """
    # 尝试从 Authorization header 获取 token
    auth_token = token
    if not auth_token and authorization:
        if authorization.startswith("Bearer "):
            auth_token = authorization[7:]

    if not auth_token:
        return None

    # 检查是否是 API Key
    if auth_token.startswith("clou_"):
        try:
            user, _ = await _authenticate_api_key(auth_token)
            return user
        except BusinessError:
            return None

    # 尝试 JWT 认证
    try:
        return await _authenticate_jwt(auth_token)
    except BusinessError:
        return None


class PermissionChecker:
    def __init__(self, required_permission: str):
        self.required_permission = required_permission

    async def __call__(
        self, current_user: User = Depends(get_current_active_user)
    ) -> User:
        if current_user.is_superuser:
            return current_user

        # Check permissions
        # Since we prefetched roles and permissions, we can check in memory
        # Note: roles__permissions is a list of Permission objects

        has_permission = False
        for role in current_user.roles:
            for permission in role.permissions:
                if (
                    permission.code == self.required_permission
                    or permission.code == "*"
                ):
                    has_permission = True
                    break
            if has_permission:
                break

        if not has_permission:
            raise BusinessError(
                code=ResponseCode.PERMISSION_DENIED,
                msg_key="operation_not_permitted",
                status_code=status.HTTP_403_FORBIDDEN,
                permission=self.required_permission,
            )

        return current_user


async def check_api_key_agent_access(api_key: Optional[APIKey], agent_id: UUID) -> None:
    """
    检查 API Key 是否有权访问指定的 Agent。
    如果 api_key 为 None（JWT 认证），则跳过检查。
    如果 API Key 没有关联任何 Agent，则允许访问所有 Agent。
    """
    if api_key is None:
        return  # JWT 认证，跳过检查

    # 获取 API Key 关联的 Agents
    agents = await api_key.agents.all()

    # 如果没有关联任何 Agent，允许访问所有（向后兼容）
    if not agents:
        return

    # 检查是否有权访问指定的 Agent
    agent_ids = [agent.id for agent in agents]
    if agent_id not in agent_ids:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="api_key_no_agent_access",
            status_code=status.HTTP_403_FORBIDDEN,
        )


async def check_api_key_workflow_access(
    api_key: Optional[APIKey], workflow_id: UUID
) -> None:
    """
    检查 API Key 是否有权访问指定的 Workflow。
    如果 api_key 为 None（JWT 认证），则跳过检查。
    如果 API Key 没有关联任何 Workflow，则允许访问所有 Workflow。
    """
    if api_key is None:
        return  # JWT 认证，跳过检查

    # 获取 API Key 关联的 Workflows
    workflows = await api_key.workflows.all()

    # 如果没有关联任何 Workflow，允许访问所有（向后兼容）
    if not workflows:
        return

    # 检查是否有权访问指定的 Workflow
    workflow_ids = [w.id for w in workflows]
    if workflow_id not in workflow_ids:
        raise BusinessError(
            code=ResponseCode.PERMISSION_DENIED,
            msg_key="api_key_no_workflow_access",
            status_code=status.HTTP_403_FORBIDDEN,
        )
