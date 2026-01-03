from enum import IntEnum
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ResponseCode(IntEnum):
    """响应状态码枚举"""

    # 成功
    SUCCESS = 0

    # 通用错误 (1000-1999)
    UNKNOWN_ERROR = 1000
    VALIDATION_ERROR = 1001
    BAD_REQUEST = 1002
    INTERNAL_ERROR = 1003
    FORBIDDEN = 1004

    # 认证错误 (2000-2999)
    UNAUTHORIZED = 2000
    INVALID_TOKEN = 2001
    TOKEN_EXPIRED = 2002
    INVALID_CREDENTIALS = 2003
    INACTIVE_USER = 2004

    # 权限错误 (3000-3999)
    PERMISSION_DENIED = 3000
    INSUFFICIENT_PRIVILEGES = 3001
    NOT_TEAM_MEMBER = 3002
    TEAM_ADMIN_REQUIRED = 3003
    TEAM_OWNER_REQUIRED = 3004

    # 资源错误 (4000-4999)
    NOT_FOUND = 4000
    USER_NOT_FOUND = 4001
    ROLE_NOT_FOUND = 4002
    PERMISSION_NOT_FOUND = 4003
    TEAM_NOT_FOUND = 4004
    TEAM_MEMBER_NOT_FOUND = 4005

    # 注册相关错误 (5000-5099)
    REGISTRATION_DISABLED = 5000
    ALREADY_EXISTS = 5001
    USERNAME_EXISTS = 5002
    EMAIL_EXISTS = 5003
    EMAIL_NOT_VERIFIED = 5004
    VERIFICATION_CODE_INVALID = 5005
    VERIFICATION_CODE_EXPIRED = 5006
    EMAIL_SEND_FAILED = 5007
    EMAIL_SEND_TOO_FREQUENT = 5008
    # 资源重复错误 (5100-5199)
    ROLE_NAME_EXISTS = 5100
    PERMISSION_CODE_EXISTS = 5101
    TEAM_NAME_EXISTS = 5102
    ALREADY_TEAM_MEMBER = 5103
    DUPLICATE_NAME = 5104
    # 操作禁止错误 (5200-5299)
    CANNOT_DELETE_SYSTEM_ROLE = 5200
    CANNOT_DELETE_SUPERUSER = 5201
    CANNOT_DELETE_WILDCARD_PERMISSION = 5202
    CANNOT_MODIFY_SYSTEM_ROLE = 5203
    CANNOT_DELETE_DEFAULT_TEAM = 5204
    CANNOT_ADD_AS_OWNER = 5205
    CANNOT_CHANGE_OWNER_ROLE = 5206
    CANNOT_PROMOTE_TO_OWNER = 5207
    CANNOT_REMOVE_OWNER = 5208
    OWNER_CANNOT_LEAVE = 5209
    ROLE_IN_USE = 5210
    USER_ALREADY_ACTIVE = 5211
    USER_ALREADY_INACTIVE = 5212
    CANNOT_DEACTIVATE_SUPERUSER = 5213

    # 登录安全错误 (5300-5399)
    ACCOUNT_LOCKED = 5300
    TOO_MANY_LOGIN_ATTEMPTS = 5301
    CAPTCHA_REQUIRED = 5302
    CAPTCHA_INVALID = 5303

    # 速率限制错误 (5400-5499)
    RATE_LIMITED = 5400

    # 知识库错误 (6000-6099)
    KB_NOT_FOUND = 6000
    KB_NAME_EXISTS = 6001
    DOCUMENT_NOT_FOUND = 6002
    INVALID_DOCUMENT_TYPE = 6003
    DOCUMENT_PROCESSING_FAILED = 6004
    CHUNK_NOT_FOUND = 6005
    DOCUMENT_PROCESSING = 6006

    # 模型相关错误 (6100-6199)
    MODEL_NOT_FOUND = 6100
    TEAM_MODEL_NOT_FOUND = 6101
    TEAM_MODEL_EXISTS = 6102
    MODEL_QUOTA_EXCEEDED = 6103
    MODEL_NOT_AUTHORIZED = 6104
    MODEL_VISION_NOT_SUPPORTED = 6105

    # Agent 相关错误 (6200-6299)
    AGENT_NOT_FOUND = 6200
    AGENT_ACCESS_DENIED = 6201
    AGENT_NOT_PUBLISHED = 6202
    CONVERSATION_NOT_FOUND = 6210
    MESSAGE_NOT_FOUND = 6211


class BusinessError(Exception):
    """
    业务逻辑异常

    用于在接口中抛出业务错误，会被全局异常处理器捕获并转换为统一响应格式。

    Usage:
        raise BusinessError(
            code=ResponseCode.USERNAME_EXISTS,
            msg_key="username_already_registered"
        )
    """

    def __init__(
        self,
        code: ResponseCode | int = ResponseCode.UNKNOWN_ERROR,
        msg: str | None = None,
        msg_key: str | None = None,
        status_code: int = 400,
        data: Any = None,
        **kwargs,
    ):
        self.code = code
        self.msg = msg
        self.msg_key = msg_key
        self.status_code = status_code
        self.data = data
        self.kwargs = kwargs
        super().__init__(msg or msg_key or str(code))


class Response(BaseModel, Generic[T]):
    """统一响应格式"""

    code: int = ResponseCode.SUCCESS
    data: Optional[T] = None
    msg: str = "success"


class PageData(BaseModel, Generic[T]):
    """分页数据"""

    items: list[T]
    total: int
    page: int
    page_size: int


class PageResponse(Response[PageData[T]], Generic[T]):
    """分页响应"""

    pass


# 便捷函数
def success(
    data: Any = None, msg: str | None = None, msg_key: str = "success", **kwargs
) -> dict:
    """
    成功响应

    Args:
        data: 响应数据
        msg: 直接指定消息（优先级高于msg_key）
        msg_key: 翻译消息的key
        **kwargs: 消息格式化参数
    """
    from app.core.i18n import t

    if msg is None:
        msg = t(msg_key, **kwargs)
    return {"code": ResponseCode.SUCCESS, "data": data, "msg": msg}


def error(
    code: ResponseCode | int = ResponseCode.UNKNOWN_ERROR,
    msg: str | None = None,
    msg_key: str | None = None,
    data: Any = None,
    **kwargs,
) -> dict:
    """
    错误响应

    Args:
        code: 错误码
        msg: 直接指定消息（优先级最高）
        msg_key: 翻译消息的key（优先级次之）
        data: 响应数据
        **kwargs: 消息格式化参数
    """
    from app.core.i18n import t, get_code_message

    if msg is None:
        if msg_key:
            msg = t(msg_key, **kwargs)
        elif isinstance(code, ResponseCode):
            msg = get_code_message(code)
        else:
            msg = t("unknown_error")
    return {"code": int(code), "data": data, "msg": msg}
