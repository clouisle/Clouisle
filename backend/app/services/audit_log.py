import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from fastapi import Request

from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.api_key import APIKey


class AuditLogService:
    """审计日志服务"""

    # 敏感字段列表
    SENSITIVE_FIELDS = {
        "password",
        "hashed_password",
        "api_key",
        "secret_key",
        "access_token",
        "refresh_token",
        "private_key",
        "secret",
        "token",
    }

    # 审计字段值长度上限（与 chat.py 的 AUDIT_MESSAGE_CONTENT_PREVIEW_LENGTH 一致）
    AUDIT_MAX_FIELD_LENGTH = 500

    # 快照字段注册表：resource_type -> 纳入 before/after 快照的字段
    # 注册表规则（承载性约束）：
    #   - 只允许普通列与原始 `<fk>_id` UUID 列；绝不允许关联描述符（team、
    #     created_by、user 等）——对其 getattr 会触发懒加载数据库查询。
    #     因此 snapshot 对任何端点零额外查询。
    #   - 排除项：id/created_at/updated_at 及所有 *_at 时间戳（噪音）；
    #     计数器（conversation_count、message_count、total_tokens、run_count 等）；
    #     脱敏器 SENSITIVE_FIELDS 键匹配无法覆盖的密钥容器：
    #     Agent.tools_credentials、Tool.credentials/http_config/mcp_config、
    #     SSOProvider.config、Workflow.trigger_config、Model.api_key、
    #     APIKey.key_prefix/key_hash、User.hashed_password/totp_secret/totp_backup_codes_hash。
    SNAPSHOT_FIELDS: dict[str, tuple[str, ...]] = {
        "agent": (
            "name",
            "description",
            "avatar_url",
            "icon",
            "model_id",
            "system_prompt",
            "max_iterations",
            "hide_tool_calls",
            "hide_message_actions",
            "hide_reasoning",
            "tools_config",
            "enable_attachments",
            "attachment_config",
            "enable_user_input_request",
            "enable_memory",
            "memory_config",
            "enable_image_generation",
            "image_generation_config",
            "enable_video_generation",
            "video_generation_config",
            "streaming_config",
            "context_compression_config",
            "embed_config",
            "rag_mode",
            "variables",
            "opening_message",
            "suggested_questions",
            "powered_by_text",
            "status",
            "visibility",
        ),
        "workflow": (
            "name",
            "description",
            "icon",
            "visibility",
            "definition",
            "variables",
            "status",
            "version",
            "trigger_type",
            "webhook_token",
            "embed_config",
            "run_page_config",
        ),
        "knowledge_base": (
            "name",
            "description",
            "icon",
            "status",
            "embedding_model_id",
            "rerank_model_id",
            "embedding_dimension",
            "settings",
        ),
        "conversation": (
            "title",
            "message_count",
            "token_usage",
            "updated_at",
        ),
        "document": (
            "name",
            "doc_type",
            "file_path",
            "file_size",
            "source_url",
            "status",
            "error_message",
            "metadata",
        ),
        "document_chunk": (
            "content",
            "chunk_index",
            "token_count",
            "metadata",
            "status",
            "error_message",
        ),
        "api_key": ("name", "scopes", "rate_limit", "is_active", "expires_at"),
        "team": ("name", "description", "avatar_url"),
        "user": (
            "username",
            "email",
            "is_active",
            "approval_status",
            "is_superuser",
            "email_verified",
            "locale",
            "auth_source",
            "external_id",
            "avatar_url",
            "force_password_change",
            "password_expiration_exempt",
            "totp_enabled",
        ),
        "sso_provider": (
            "name",
            "protocol",
            "display_name",
            "icon_url",
            "button_text",
            "attribute_mapping",
            "is_enabled",
            "allow_signup",
            "require_approval",
            "default_role_id",
        ),
        "memory_entity": ("name", "entity_type", "description", "properties"),
        "memory_relation": ("relation_type", "description", "properties"),
        "tool": (
            "name",
            "display_name",
            "description",
            "icon",
            "category",
            "type",
            "custom_type",
            "code_config",
            "parameters",
            "is_enabled",
        ),
        "team_model": (
            "daily_token_limit",
            "monthly_token_limit",
            "daily_request_limit",
            "monthly_request_limit",
            "is_enabled",
            "priority",
        ),
        "skill": ("name", "display_name", "is_enabled", "version"),
        "team_member": ("team_id", "user_id", "role"),
        "tool_share": ("tool_id", "shared_with_team_id", "permission"),
        "workflow_run": ("status", "trigger_type", "is_debug"),
        "workflow_version": (
            "version",
            "definition",
            "variables",
            "trigger_type",
            "trigger_config",
            "description",
        ),
        "sso_connection": (
            "provider_id",
            "provider_user_id",
            "provider_username",
            "provider_email",
        ),
    }

    @staticmethod
    async def log(
        user: Optional[User],
        action: str,
        resource_type: str,
        resource_id: Optional[UUID],
        resource_name: Optional[str],
        operation: str,
        status: str,
        request: Optional[Request] = None,
        changes: Optional[dict] = None,
        metadata: Optional[dict] = None,
        error_message: Optional[str] = None,
        api_key: Optional[APIKey] = None,
    ) -> AuditLog:
        """
        记录审计日志

        Args:
            user: 操作用户
            action: 操作类型（如 login_success, create_user）
            resource_type: 资源类型（如 user, agent, role）
            resource_id: 资源ID
            resource_name: 资源名称
            operation: CRUD操作（create, read, update, delete）
            status: 状态（success, failed）
            request: FastAPI请求对象（可选，用于获取IP和User-Agent）
            changes: 变更详情（before/after）
            metadata: 额外元数据
            error_message: 错误信息
            api_key: API密钥（如果通过API密钥认证）

        Returns:
            创建的审计日志对象
        """
        # 获取客户端IP
        ip_address = AuditLogService.get_client_ip(request) if request else "system"

        # 获取User-Agent
        user_agent = request.headers.get("user-agent") if request else "system"

        # 脱敏变更数据
        if changes:
            changes = AuditLogService.sanitize_changes(changes)

        # 确定认证方式
        auth_method = "api_key" if api_key else "jwt"

        # 创建审计日志
        audit_log = await AuditLog.create(
            user_id=user.id if user else None,
            username=user.username if user else None,
            team_id=getattr(user, "current_team_id", None) if user else None,
            ip_address=ip_address,
            user_agent=user_agent,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            operation=operation,
            status=status,
            error_message=error_message,
            changes=changes,
            metadata=metadata,
            auth_method=auth_method,
            api_key_id=api_key.id if api_key else None,
        )

        return audit_log

    @staticmethod
    def get_client_ip(request: Request) -> str:
        """
        获取客户端IP地址（支持代理）

        优先级：
        1. X-Forwarded-For（代理）
        2. X-Real-IP（Nginx）
        3. request.client.host（直连）
        """
        # 检查 X-Forwarded-For
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # X-Forwarded-For 可能包含多个IP，取第一个
            return forwarded_for.split(",")[0].strip()

        # 检查 X-Real-IP
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

        # 直连IP
        if request.client:
            return request.client.host

        return "unknown"

    @staticmethod
    def sanitize_changes(changes: dict) -> dict[str, object]:
        """
        清理敏感信息

        对密码、API密钥等敏感字段进行脱敏处理
        """
        sanitized: dict[str, object] = {}

        for key, value in changes.items():
            if key in ("before", "after"):
                # 递归处理 before/after 对象
                if isinstance(value, dict):
                    sanitized[key] = AuditLogService._sanitize_dict(value)
                else:
                    sanitized[key] = value
            else:
                sanitized[key] = value

        return sanitized

    @staticmethod
    def _sanitize_dict(data: dict) -> dict[str, object]:
        """递归脱敏字典中的敏感字段"""
        sanitized: dict[str, Any] = {}

        for key, value in data.items():
            # Conversation token counters are safe numeric metrics, not secrets.
            if (
                key == "token_usage"
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                sanitized[key] = value
            # Check whether this is a sensitive field.
            elif any(
                sensitive in key.lower()
                for sensitive in AuditLogService.SENSITIVE_FIELDS
            ):
                # Mask sensitive values while preserving a short preview for strings.
                if isinstance(value, str) and len(value) > 8:
                    sanitized[key] = value[:8] + "***"
                else:
                    sanitized[key] = "***"
            elif isinstance(value, dict):
                # Recursively sanitize nested dictionaries.
                sanitized[key] = AuditLogService._sanitize_dict(value)
            elif key == "email" and isinstance(value, str):
                # Mask the email local part.
                sanitized[key] = AuditLogService._mask_email(value)
            else:
                sanitized[key] = value

        return sanitized

    @staticmethod
    def _mask_email(email: str) -> str:
        """邮箱部分隐藏"""
        if "@" not in email:
            return email

        local, domain = email.split("@", 1)
        if len(local) <= 2:
            masked_local = local[0] + "***"
        else:
            masked_local = local[0] + "***" + local[-1]

        return f"{masked_local}@{domain}"

    @staticmethod
    def _json_safe(value: Any) -> Any:
        """将值转换为 orjson 可序列化形式，并施加硬性大小上限。

        orjson（tortoise 的 JSONField 编码器）对原始 UUID 会抛错，且不能接受
        Enum/Decimal/datetime。长字符串被截断；整个结构超过上限时在最外层
        替换为前 500 字符的 JSON 预览字符串。嵌套结构在转换过程中先按键名
        脱敏（与 _sanitize_dict 同规则），敏感键不会绕过 sanitize_changes。
        """
        return AuditLogService._json_safe_inner(value, bound=True)

    @staticmethod
    def _json_safe_inner(value: Any, bound: bool) -> Any:
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, str):
            if len(value) > AuditLogService.AUDIT_MAX_FIELD_LENGTH:
                return value[: AuditLogService.AUDIT_MAX_FIELD_LENGTH] + "..."
            return value
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                str_key = str(key)
                # 先按键名脱敏（与 _sanitize_dict 同规则），再递归转换，
                # 保证嵌套结构中的敏感键不会绕过 sanitize_changes。
                if any(
                    sensitive in str_key.lower()
                    for sensitive in AuditLogService.SENSITIVE_FIELDS
                ):
                    if isinstance(item, str) and len(item) > 8:
                        sanitized[str_key] = item[:8] + "***"
                    else:
                        sanitized[str_key] = "***"
                elif str_key == "email" and isinstance(item, str):
                    sanitized[str_key] = AuditLogService._mask_email(item)
                else:
                    sanitized[str_key] = AuditLogService._json_safe_inner(item, False)
            result: Any = sanitized
        elif isinstance(value, (list, tuple)):
            result = [AuditLogService._json_safe_inner(item, False) for item in value]
        else:
            return value
        if bound:
            return AuditLogService._structured_or_preview(result)
        return result

    @staticmethod
    def _structured_or_preview(value: Any) -> Any:
        """结构在大小上限内原样返回，否则返回前 500 字符的 JSON 预览字符串。"""
        compact = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(compact) > AuditLogService.AUDIT_MAX_FIELD_LENGTH:
            return compact[: AuditLogService.AUDIT_MAX_FIELD_LENGTH] + "..."  # 预览
        return value

    @staticmethod
    def snapshot(instance: Any, resource_type: str) -> dict:
        """对模型/服务实例的注册表字段做 JSON 安全的快照。

        仅对普通列 getattr（见注册表规则）——零数据库查询、零懒加载。
        兼容 Tortoise 实例与服务对象；缺失属性返回 None。
        """
        names = AuditLogService.SNAPSHOT_FIELDS.get(resource_type, ())
        out: dict[str, Any] = {}
        for name in names:
            try:
                out[name] = AuditLogService._json_safe(getattr(instance, name, None))
            except Exception:
                continue
        return out

    @staticmethod
    def build_changes(before: dict, after: dict) -> Optional[dict]:
        """生成 {"before": {...}, "after": {...}}，仅包含值发生变化的键。

        完全无变化时返回 None（调用方此时传 changes=None）。
        """
        diff_before: dict[str, Any] = {}
        diff_after: dict[str, Any] = {}
        for key in sorted(set(before) | set(after)):
            b, a = before.get(key, None), after.get(key, None)
            if b != a:
                diff_before[key] = b
                diff_after[key] = a
        if not diff_before and not diff_after:
            return None
        return {"before": diff_before, "after": diff_after}
