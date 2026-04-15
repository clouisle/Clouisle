"""
LLM 调用统一异常定义
"""

from typing import Any


class LLMError(Exception):
    """LLM 调用基础异常"""

    def __init__(
        self,
        message: str,
        code: str = "llm_error",
        provider: str | None = None,
        model: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.code = code
        self.provider = provider
        self.model = model
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "provider": self.provider,
            "model": self.model,
            "details": self.details,
        }


class AuthenticationError(LLMError):
    """认证失败 - API Key 无效或过期"""

    def __init__(
        self,
        message: str = "Authentication failed",
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        super().__init__(
            message=message,
            code="authentication_error",
            provider=provider,
            model=model,
            **kwargs,
        )


class RateLimitError(LLMError):
    """速率限制 - 请求过于频繁"""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        self.retry_after = retry_after
        super().__init__(
            message=message,
            code="rate_limit_error",
            provider=provider,
            model=model,
            details={"retry_after": retry_after} if retry_after else {},
            **kwargs,
        )


class ContextLengthError(LLMError):
    """上下文超长 - 输入 token 超过模型限制"""

    def __init__(
        self,
        message: str = "Context length exceeded",
        max_tokens: int | None = None,
        actual_tokens: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        self.max_tokens = max_tokens
        self.actual_tokens = actual_tokens
        super().__init__(
            message=message,
            code="context_length_error",
            provider=provider,
            model=model,
            details={"max_tokens": max_tokens, "actual_tokens": actual_tokens},
            **kwargs,
        )


class ContentFilterError(LLMError):
    """内容审核拦截"""

    def __init__(
        self,
        message: str = "Content blocked by safety filter",
        filter_type: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        self.filter_type = filter_type
        super().__init__(
            message=message,
            code="content_filter_error",
            provider=provider,
            model=model,
            details={"filter_type": filter_type} if filter_type else {},
            **kwargs,
        )


class ModelNotFoundError(LLMError):
    """模型不存在或未配置"""

    def __init__(
        self,
        message: str = "Model not found",
        model: str | None = None,
        **kwargs,
    ):
        super().__init__(
            message=message,
            code="model_not_found",
            model=model,
            **kwargs,
        )


class ModelDisabledError(LLMError):
    """模型已禁用"""

    def __init__(
        self,
        message: str = "Model is disabled",
        model: str | None = None,
        **kwargs,
    ):
        super().__init__(
            message=message,
            code="model_disabled",
            model=model,
            **kwargs,
        )


class ProviderError(LLMError):
    """供应商服务异常 - 服务端错误"""

    def __init__(
        self,
        message: str = "Provider service error",
        status_code: int | None = None,
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        self.status_code = status_code
        super().__init__(
            message=message,
            code="provider_error",
            provider=provider,
            model=model,
            details={"status_code": status_code} if status_code else {},
            **kwargs,
        )


class TimeoutError(LLMError):
    """请求超时"""

    def __init__(
        self,
        message: str = "Request timeout",
        timeout: float | None = None,
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        self.timeout = timeout
        super().__init__(
            message=message,
            code="timeout_error",
            provider=provider,
            model=model,
            details={"timeout": timeout} if timeout else {},
            **kwargs,
        )


class InvalidRequestError(LLMError):
    """无效请求 - 参数错误"""

    def __init__(
        self,
        message: str = "Invalid request",
        field: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        self.field = field
        super().__init__(
            message=message,
            code="invalid_request",
            provider=provider,
            model=model,
            details={"field": field} if field else {},
            **kwargs,
        )


class InsufficientQuotaError(LLMError):
    """配额不足"""

    def __init__(
        self,
        message: str = "Insufficient quota",
        quota_type: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        self.quota_type = quota_type
        super().__init__(
            message=message,
            code="insufficient_quota",
            provider=provider,
            model=model,
            details={"quota_type": quota_type} if quota_type else {},
            **kwargs,
        )


class QuotaExceededError(LLMError):
    """团队配额超限"""

    def __init__(
        self,
        message: str = "Team quota exceeded",
        quota_type: str | None = None,
        team_id: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        self.quota_type = quota_type
        self.team_id = team_id
        super().__init__(
            message=message,
            code="quota_exceeded",
            model=model,
            details={
                "quota_type": quota_type,
                "team_id": team_id,
            },
            **kwargs,
        )


class TaskNotFoundError(LLMError):
    """异步任务不存在 (视频生成等)"""

    def __init__(
        self,
        message: str = "Task not found",
        task_id: str | None = None,
        provider: str | None = None,
        **kwargs,
    ):
        self.task_id = task_id
        super().__init__(
            message=message,
            code="task_not_found",
            provider=provider,
            details={"task_id": task_id} if task_id else {},
            **kwargs,
        )


class UnsupportedOperationError(LLMError):
    """不支持的操作"""

    def __init__(
        self,
        message: str = "Unsupported operation",
        operation: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        **kwargs,
    ):
        self.operation = operation
        super().__init__(
            message=message,
            code="unsupported_operation",
            provider=provider,
            model=model,
            details={"operation": operation} if operation else {},
            **kwargs,
        )
