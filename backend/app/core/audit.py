"""
审计日志装饰器 - 简化审计日志集成
"""
from functools import wraps
from typing import Any, Callable, Optional

from fastapi import Request

from app.models.user import User
from app.services.audit_log import AuditLogService


def audit_log(
    action: str,
    resource_type: str,
    operation: str,
    get_resource_id: Optional[Callable] = None,
    get_resource_name: Optional[Callable] = None,
    capture_changes: bool = False,
):
    """
    审计日志装饰器

    Args:
        action: 操作类型（如 create_user, update_agent）
        resource_type: 资源类型（如 user, agent, role）
        operation: CRUD操作（create, read, update, delete）
        get_resource_id: 从函数参数或返回值获取资源ID的函数
        get_resource_name: 从函数参数或返回值获取资源名称的函数
        capture_changes: 是否捕获变更详情（before/after）

    Example:
        @audit_log(
            action="delete_user",
            resource_type="user",
            operation="delete",
            get_resource_id=lambda kwargs, result: kwargs.get("user_id"),
            get_resource_name=lambda kwargs, result: result.username if result else None,
        )
        async def delete_user(user_id: UUID, ...):
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 提取 request 和 current_user
            request: Optional[Request] = None
            current_user: Optional[User] = None

            # 从参数中查找 request 和 current_user
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                elif isinstance(arg, User):
                    current_user = arg

            for key, value in kwargs.items():
                if key == "request" and isinstance(value, Request):
                    request = value
                elif key == "current_user" and isinstance(value, User):
                    current_user = value

            # 如果没有找到 request，无法记录审计日志
            if not request:
                # 直接执行函数
                return await func(*args, **kwargs)

            # 捕获变更前的状态（如果需要）
            if capture_changes and get_resource_id:
                try:
                    resource_id = get_resource_id(kwargs, None)
                    if resource_id:
                        # 这里可以根据 resource_type 查询当前状态
                        # 为简化实现，暂时不实现
                        pass
                except Exception:
                    pass

            # 执行函数
            result = None
            status = "success"
            error_message = None

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "failed"
                error_message = str(e)
                raise
            finally:
                # 记录审计日志
                try:
                    # 获取资源ID和名称
                    resource_id = None
                    resource_name = None

                    if get_resource_id:
                        try:
                            resource_id = get_resource_id(kwargs, result)
                        except Exception:
                            pass

                    if get_resource_name:
                        try:
                            resource_name = get_resource_name(kwargs, result)
                        except Exception:
                            pass

                    # 记录审计日志
                    await AuditLogService.log(
                        user=current_user,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        resource_name=resource_name,
                        operation=operation,
                        status=status,
                        request=request,
                        error_message=error_message,
                    )
                except Exception:
                    # 审计日志记录失败不应影响主流程
                    pass

        return wrapper

    return decorator
