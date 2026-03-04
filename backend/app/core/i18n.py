"""
Internationalization (i18n) module for multi-language support.
Currently supports: English (en), Chinese (zh)
"""

from contextvars import ContextVar
from enum import Enum
from typing import Optional

# Context variable to store current language per request
current_language: ContextVar[str] = ContextVar("current_language", default="en")


class Language(str, Enum):
    """Supported languages"""

    EN = "en"
    ZH = "zh"


# Translation messages dictionary
# Format: {message_key: {language_code: translated_message}}
TRANSLATIONS: dict[str, dict[str, str]] = {
    # Success messages
    "success": {
        "en": "Success",
        "zh": "成功",
    },
    "welcome_message": {
        "en": "Welcome to Clouisle API",
        "zh": "欢迎使用 Clouisle API",
    },
    "login_successful": {
        "en": "Login successful",
        "zh": "登录成功",
    },
    "logout_successful": {
        "en": "Logout successful",
        "zh": "登出成功",
    },
    "registration_successful": {
        "en": "Registration successful",
        "zh": "注册成功",
    },
    "registration_pending_approval": {
        "en": "Registration successful. Your account is pending admin approval.",
        "zh": "注册成功。您的账户正在等待管理员审核。",
    },
    "registration_pending_verification": {
        "en": "Registration successful. Please verify your email to activate your account.",
        "zh": "注册成功。请验证您的邮箱以激活账户。",
    },
    "registration_successful_superadmin": {
        "en": "Registration successful. You are the first user and have been promoted to Super Admin!",
        "zh": "注册成功。您是第一个用户，已被提升为超级管理员！",
    },
    "registration_disabled": {
        "en": "Registration is currently disabled",
        "zh": "注册功能已关闭",
    },
    "user_created": {
        "en": "User created successfully",
        "zh": "用户创建成功",
    },
    "user_updated": {
        "en": "User updated successfully",
        "zh": "用户更新成功",
    },
    "user_deleted": {
        "en": "User deleted successfully",
        "zh": "用户删除成功",
    },
    "user_activated": {
        "en": "User activated successfully",
        "zh": "用户激活成功",
    },
    "user_deactivated": {
        "en": "User deactivated successfully",
        "zh": "用户已禁用",
    },
    "user_already_active": {
        "en": "User is already active",
        "zh": "用户已经是激活状态",
    },
    "user_already_inactive": {
        "en": "User is already inactive",
        "zh": "用户已经是禁用状态",
    },
    "cannot_deactivate_superuser": {
        "en": "Cannot deactivate superuser",
        "zh": "不能禁用超级管理员",
    },
    "profile_updated": {
        "en": "Profile updated successfully",
        "zh": "个人资料更新成功",
    },
    "password_changed": {
        "en": "Password changed successfully",
        "zh": "密码修改成功",
    },
    "current_password_incorrect": {
        "en": "Current password is incorrect",
        "zh": "当前密码不正确",
    },
    "password_too_short": {
        "en": "Password must be at least 6 characters",
        "zh": "密码长度至少为 6 个字符",
    },
    "account_deleted": {
        "en": "Account deleted successfully",
        "zh": "账号已删除",
    },
    "cannot_delete_superuser_account": {
        "en": "Super admin cannot delete their own account",
        "zh": "超级管理员不能删除自己的账号",
    },
    "account_deletion_disabled": {
        "en": "Account deletion is disabled by administrator",
        "zh": "管理员已禁用账号自主删除功能",
    },
    "role_created": {
        "en": "Role created successfully",
        "zh": "角色创建成功",
    },
    "role_updated": {
        "en": "Role updated successfully",
        "zh": "角色更新成功",
    },
    "role_deleted": {
        "en": "Role deleted successfully",
        "zh": "角色删除成功",
    },
    "role_permissions_updated": {
        "en": "Role permissions updated successfully",
        "zh": "角色权限更新成功",
    },
    "permission_created": {
        "en": "Permission created successfully",
        "zh": "权限创建成功",
    },
    "permission_updated": {
        "en": "Permission updated successfully",
        "zh": "权限更新成功",
    },
    "permission_deleted": {
        "en": "Permission deleted successfully",
        "zh": "权限删除成功",
    },
    "notification_created": {
        "en": "Notification created successfully",
        "zh": "通知创建成功",
    },
    "notification_deleted": {
        "en": "Notification deleted successfully",
        "zh": "通知删除成功",
    },
    "notification_read_updated": {
        "en": "Notification read status updated",
        "zh": "通知已读状态已更新",
    },
    # Error messages - General
    "unknown_error": {
        "en": "Unknown error",
        "zh": "未知错误",
    },
    "internal_server_error": {
        "en": "Internal Server Error",
        "zh": "服务器内部错误",
    },
    "validation_error": {
        "en": "Validation error",
        "zh": "验证错误",
    },
    "invalid_notification_type": {
        "en": "Invalid notification type: {type_key}",
        "zh": "无效的通知类型：{type_key}",
    },
    "setting_not_found": {
        "en": "Setting '{key}' not found",
        "zh": "设置 '{key}' 未找到",
    },
    "archive_failed": {
        "en": "Archive failed",
        "zh": "归档失败",
    },
    # Error messages - Authentication
    "not_authenticated": {
        "en": "Not authenticated",
        "zh": "未登录",
    },
    "unauthorized": {
        "en": "Unauthorized",
        "zh": "未授权",
    },
    "invalid_token": {
        "en": "Invalid token",
        "zh": "无效的令牌",
    },
    "token_expired": {
        "en": "Token expired",
        "zh": "令牌已过期",
    },
    "token_revoked": {
        "en": "Token has been revoked",
        "zh": "令牌已被撤销",
    },
    "session_expired_new_login": {
        "en": "Your session has expired due to a new login from another device",
        "zh": "由于在其他设备登录，您的会话已过期",
    },
    "invalid_credentials": {
        "en": "Invalid credentials",
        "zh": "凭证无效",
    },
    "incorrect_email_or_password": {
        "en": "Incorrect email or password",
        "zh": "邮箱或密码错误",
    },
    "inactive_user": {
        "en": "Inactive user",
        "zh": "用户未激活",
    },
    "could_not_validate_credentials": {
        "en": "Could not validate credentials",
        "zh": "无法验证凭证",
    },
    "notification_not_found": {
        "en": "Notification not found",
        "zh": "通知不存在",
    },
    "invalid_notification_scope": {
        "en": "Invalid notification scope",
        "zh": "通知范围无效",
    },
    "notification_scope_requires_team": {
        "en": "Team scope requires team_id",
        "zh": "团队范围必须提供 team_id",
    },
    "notification_scope_requires_user": {
        "en": "User scope requires user_id",
        "zh": "个人范围必须提供 user_id",
    },
    # Account security messages
    "account_locked": {
        "en": "Account is locked. Please try again later.",
        "zh": "账户已被锁定，请稍后再试。",
    },
    "account_locked_after_attempts": {
        "en": "Too many failed login attempts. Account has been locked.",
        "zh": "登录失败次数过多，账户已被锁定。",
    },
    "email_not_verified": {
        "en": "Please verify your email before logging in",
        "zh": "请先验证您的邮箱",
    },
    "password_too_weak": {
        "en": "Password does not meet security requirements",
        "zh": "密码不符合安全要求",
    },
    # Email verification messages
    "smtp_not_configured": {
        "en": "Email service is not configured",
        "zh": "邮件服务未配置",
    },
    "smtp_not_enabled": {
        "en": "Email service is not enabled",
        "zh": "邮件服务未启用",
    },
    "dingtalk_not_configured": {
        "en": "DingTalk service is not configured",
        "zh": "钉钉服务未配置",
    },
    "dingtalk_not_enabled": {
        "en": "DingTalk service is not enabled",
        "zh": "钉钉服务未启用",
    },
    "dingtalk_send_failed": {
        "en": "Failed to send DingTalk message",
        "zh": "钉钉消息发送失败",
    },
    "test_dingtalk_sent": {
        "en": "Test DingTalk message sent successfully",
        "zh": "测试钉钉消息发送成功",
    },
    # WeChat Work
    "wechat_not_configured": {
        "en": "WeChat Work service is not configured",
        "zh": "企业微信服务未配置",
    },
    "wechat_not_enabled": {
        "en": "WeChat Work service is not enabled",
        "zh": "企业微信服务未启用",
    },
    "wechat_send_failed": {
        "en": "Failed to send WeChat Work message",
        "zh": "企业微信消息发送失败",
    },
    "test_wechat_sent": {
        "en": "Test WeChat Work message sent successfully",
        "zh": "测试企业微信消息发送成功",
    },
    # Feishu
    "feishu_not_configured": {
        "en": "Feishu service is not configured",
        "zh": "飞书服务未配置",
    },
    "feishu_not_enabled": {
        "en": "Feishu service is not enabled",
        "zh": "飞书服务未启用",
    },
    "feishu_send_failed": {
        "en": "Failed to send Feishu message",
        "zh": "飞书消息发送失败",
    },
    "test_feishu_sent": {
        "en": "Test Feishu message sent successfully",
        "zh": "测试飞书消息发送成功",
    },
    # Generic Webhook
    "webhook_not_configured": {
        "en": "Webhook is not configured",
        "zh": "Webhook 未配置",
    },
    "webhook_not_enabled": {
        "en": "Webhook is not enabled",
        "zh": "Webhook 未启用",
    },
    "webhook_send_failed": {
        "en": "Failed to send Webhook notification",
        "zh": "Webhook 通知发送失败",
    },
    "test_webhook_sent": {
        "en": "Test Webhook notification sent successfully",
        "zh": "测试 Webhook 通知发送成功",
    },
    # Slack
    "slack_not_configured": {
        "en": "Slack service is not configured",
        "zh": "Slack 服务未配置",
    },
    "slack_not_enabled": {
        "en": "Slack service is not enabled",
        "zh": "Slack 服务未启用",
    },
    "slack_send_failed": {
        "en": "Failed to send Slack message",
        "zh": "Slack 消息发送失败",
    },
    "test_slack_sent": {
        "en": "Test Slack message sent successfully",
        "zh": "测试 Slack 消息发送成功",
    },
    "email_send_too_frequent": {
        "en": "Please wait before requesting another email",
        "zh": "请稍后再请求发送邮件",
    },
    "email_not_found": {
        "en": "Email not found",
        "zh": "邮箱未找到",
    },
    "email_already_verified": {
        "en": "Email has already been verified",
        "zh": "邮箱已验证",
    },
    "verification_email_sent": {
        "en": "Verification email has been sent",
        "zh": "验证邮件已发送",
    },
    "verification_code_invalid": {
        "en": "Invalid verification code",
        "zh": "验证码无效",
    },
    "verification_token_invalid": {
        "en": "Verification link is invalid or expired",
        "zh": "验证链接无效或已过期",
    },
    "email_verified_success": {
        "en": "Email verified successfully",
        "zh": "邮箱验证成功",
    },
    "reset_password_email_sent": {
        "en": "If the email exists, a password reset link has been sent",
        "zh": "如果邮箱存在，密码重置链接已发送",
    },
    "password_reset_success": {
        "en": "Password has been reset successfully",
        "zh": "密码重置成功",
    },
    "email_send_failed": {
        "en": "Failed to send email",
        "zh": "邮件发送失败",
    },
    "test_email_sent": {
        "en": "Test email sent successfully",
        "zh": "测试邮件发送成功",
    },
    "test_email_subject": {
        "en": "【{site_name}】Test Email",
        "zh": "【{site_name}】测试邮件",
    },
    "test_email_body_text": {
        "en": "This is a test email from {site_name}.\n\nIf you received this email, your SMTP configuration is working correctly.",
        "zh": "这是一封来自 {site_name} 的测试邮件。\n\n如果您收到了这封邮件，说明 SMTP 配置正确。",
    },
    "test_email_body_html": {
        "en": '\n<!DOCTYPE html>\n<html>\n<head>\n    <meta charset="utf-8">\n</head>\n<body style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">\n    <h2 style="color: #333;">✅ SMTP Configuration Test Successful</h2>\n    <p>This is a test email from <strong>{site_name}</strong>.</p>\n    <p style="color: #666;">If you received this email, your SMTP configuration is working correctly.</p>\n</body>\n</html>\n',
        "zh": '\n<!DOCTYPE html>\n<html>\n<head>\n    <meta charset="utf-8">\n</head>\n<body style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">\n    <h2 style="color: #333;">✅ SMTP 配置测试成功</h2>\n    <p>这是一封来自 <strong>{site_name}</strong> 的测试邮件。</p>\n    <p style="color: #666;">如果您收到了这封邮件，说明 SMTP 配置正确。</p>\n</body>\n</html>\n',
    },
    "test_notification_title": {
        "en": "【{site_name}】Test Message",
        "zh": "【{site_name}】测试消息",
    },
    "test_dingtalk_content": {
        "en": "This is a test message. If you received this, your DingTalk configuration is working correctly.",
        "zh": "这是一条测试消息，如果您收到此消息，说明钉钉通知配置正确。",
    },
    "test_wechat_content": {
        "en": "This is a test message. If you received this, your WeChat Work configuration is working correctly.",
        "zh": "这是一条测试消息，如果您收到此消息，说明企业微信通知配置正确。",
    },
    "test_feishu_content": {
        "en": "This is a test message. If you received this, your Feishu configuration is working correctly.",
        "zh": "这是一条测试消息，如果您收到此消息，说明飞书通知配置正确。",
    },
    "test_webhook_content": {
        "en": "This is a test message. If you received this, your Webhook configuration is working correctly.",
        "zh": "这是一条测试消息，如果您收到此消息，说明 Webhook 通知配置正确。",
    },
    "test_slack_content": {
        "en": "This is a test message. If you received this, your Slack configuration is working correctly.",
        "zh": "这是一条测试消息，如果您收到此消息，说明 Slack 通知配置正确。",
    },
    "archive_task_started": {
        "en": "Archive task started successfully",
        "zh": "归档任务已启动",
    },
    "archive_task_completed": {
        "en": "Archive completed successfully",
        "zh": "归档完成",
    },
    "email_queued": {
        "en": "Emails have been queued for sending",
        "zh": "邮件已加入发送队列",
    },
    "email_rate_limit_exceeded": {
        "en": "Email sending rate limit exceeded. Please try again later.",
        "zh": "邮件发送频率超限，请稍后再试",
    },
    "email_quota_insufficient": {
        "en": "Insufficient email quota for this batch. Reduce the number of recipients.",
        "zh": "邮件配额不足，请减少收件人数量",
    },
    # File upload messages
    "file_uploaded": {
        "en": "File uploaded successfully",
        "zh": "文件上传成功",
    },
    "file_deleted": {
        "en": "File deleted successfully",
        "zh": "文件删除成功",
    },
    "file_not_found": {
        "en": "File not found",
        "zh": "文件不存在",
    },
    "invalid_file_type": {
        "en": "Invalid file type",
        "zh": "不支持的文件类型",
    },
    "file_too_large": {
        "en": "File too large",
        "zh": "文件过大",
    },
    # File parsing messages
    "file_required": {
        "en": "File is required",
        "zh": "请上传文件",
    },
    "unsupported_file_type": {
        "en": "Unsupported file type",
        "zh": "不支持的文件类型",
    },
    "invalid_truncate_strategy": {
        "en": "Invalid truncate strategy",
        "zh": "无效的截断策略",
    },
    "file_parse_error": {
        "en": "Failed to parse file",
        "zh": "文件解析失败",
    },
    "file_parsed": {
        "en": "File parsed successfully",
        "zh": "文件解析成功",
    },
    "too_many_files": {
        "en": "Too many files uploaded",
        "zh": "上传文件数量过多",
    },
    "all_files_failed": {
        "en": "All files failed to parse",
        "zh": "所有文件解析失败",
    },
    "files_parsed": {
        "en": "Files parsed successfully",
        "zh": "文件批量解析成功",
    },
    # Captcha messages
    "captcha_required": {
        "en": "Captcha is required",
        "zh": "请输入验证码",
    },
    "captcha_invalid": {
        "en": "Invalid captcha answer",
        "zh": "验证码错误",
    },
    # Error messages - Permission
    "access_denied": {
        "en": "Access denied",
        "zh": "访问被拒绝",
    },
    "permission_denied": {
        "en": "Permission denied",
        "zh": "权限被拒绝",
    },
    "insufficient_privileges": {
        "en": "Insufficient privileges",
        "zh": "权限不足",
    },
    "operation_not_permitted": {
        "en": "Operation not permitted. Required: {permission}",
        "zh": "操作不允许。需要权限：{permission}",
    },
    # Error messages - Resource
    "unknown": {
        "en": "Unknown",
        "zh": "未知",
    },
    "not_found": {
        "en": "Resource not found",
        "zh": "资源未找到",
    },
    "user_not_found": {
        "en": "User not found",
        "zh": "用户未找到",
    },
    "role_not_found": {
        "en": "Role not found",
        "zh": "角色未找到",
    },
    "permission_not_found": {
        "en": "Permission not found",
        "zh": "权限未找到",
    },
    "permission_code_not_found": {
        "en": "Permission '{code}' not found",
        "zh": "权限 '{code}' 未找到",
    },
    # Error messages - Business logic
    "already_exists": {
        "en": "Resource already exists",
        "zh": "资源已存在",
    },
    "username_exists": {
        "en": "Username already exists",
        "zh": "用户名已存在",
    },
    "username_already_registered": {
        "en": "Username already registered",
        "zh": "用户名已被注册",
    },
    "email_exists": {
        "en": "Email already exists",
        "zh": "邮箱已存在",
    },
    "email_already_registered": {
        "en": "Email already registered",
        "zh": "邮箱已被注册",
    },
    "user_with_username_exists": {
        "en": "The user with this username already exists in the system.",
        "zh": "该用户名已存在于系统中。",
    },
    "user_with_email_exists": {
        "en": "The user with this email already exists in the system.",
        "zh": "该邮箱已存在于系统中。",
    },
    "user_with_id_not_exists": {
        "en": "The user with this id does not exist in the system",
        "zh": "该ID的用户不存在于系统中",
    },
    "role_name_exists": {
        "en": "Role name already exists",
        "zh": "角色名已存在",
    },
    "role_with_name_exists": {
        "en": "Role with this name already exists",
        "zh": "该角色名已存在",
    },
    "permission_code_exists": {
        "en": "Permission code already exists",
        "zh": "权限代码已存在",
    },
    "permission_with_code_exists": {
        "en": "Permission with this code already exists",
        "zh": "该权限代码已存在",
    },
    "cannot_delete_system_role": {
        "en": "System roles cannot be deleted",
        "zh": "系统角色不能被删除",
    },
    "cannot_delete_superuser": {
        "en": "Superusers cannot be deleted",
        "zh": "超级管理员不能被删除",
    },
    "cannot_delete_wildcard_permission": {
        "en": "Cannot delete the system wildcard permission",
        "zh": "不能删除系统通配符权限",
    },
    "cannot_modify_system_role": {
        "en": "System roles cannot be modified",
        "zh": "系统角色不能被修改",
    },
    "cannot_modify_system_role_permissions": {
        "en": "System role permissions cannot be modified",
        "zh": "系统角色权限不能被修改",
    },
    "role_in_use": {
        "en": "Cannot delete role: {count} user(s) are assigned to this role",
        "zh": "无法删除角色：有 {count} 个用户分配了此角色",
    },
    # Team messages
    "team_created": {
        "en": "Team created successfully",
        "zh": "团队创建成功",
    },
    "team_updated": {
        "en": "Team updated successfully",
        "zh": "团队更新成功",
    },
    "team_deleted": {
        "en": "Team deleted successfully",
        "zh": "团队删除成功",
    },
    "team_not_found": {
        "en": "Team not found",
        "zh": "团队未找到",
    },
    "team_name_exists": {
        "en": "Team with this name already exists",
        "zh": "该团队名称已存在",
    },
    "not_team_member": {
        "en": "You are not a member of this team",
        "zh": "您不是该团队成员",
    },
    "team_admin_required": {
        "en": "Team owner or admin permission required",
        "zh": "需要团队所有者或管理员权限",
    },
    "team_owner_required": {
        "en": "Team owner permission required",
        "zh": "需要团队所有者权限",
    },
    "cannot_delete_default_team": {
        "en": "Cannot delete the default team",
        "zh": "不能删除默认团队",
    },
    # Team member messages
    "team_member_added": {
        "en": "Team member added successfully",
        "zh": "团队成员添加成功",
    },
    "team_member_updated": {
        "en": "Team member updated successfully",
        "zh": "团队成员更新成功",
    },
    "team_member_removed": {
        "en": "Team member removed successfully",
        "zh": "团队成员移除成功",
    },
    "team_member_not_found": {
        "en": "Team member not found",
        "zh": "团队成员未找到",
    },
    "already_team_member": {
        "en": "User is already a member of this team",
        "zh": "用户已是该团队成员",
    },
    "cannot_add_as_owner": {
        "en": "Cannot add member as owner",
        "zh": "不能将成员添加为所有者",
    },
    "cannot_change_owner_role": {
        "en": "Cannot change the owner's role",
        "zh": "不能更改所有者角色",
    },
    "cannot_promote_to_owner": {
        "en": "Cannot promote to owner. Use transfer ownership instead",
        "zh": "不能提升为所有者，请使用转让所有权功能",
    },
    "cannot_remove_owner": {
        "en": "Cannot remove team owner. Transfer ownership first or delete the team",
        "zh": "不能移除团队所有者，请先转让所有权或删除团队",
    },
    "owner_cannot_leave": {
        "en": "Team owner cannot leave. Transfer ownership first or delete the team",
        "zh": "团队所有者不能离开，请先转让所有权或删除团队",
    },
    "team_left": {
        "en": "You have left the team",
        "zh": "您已离开团队",
    },
    "ownership_transferred": {
        "en": "Team ownership transferred successfully",
        "zh": "团队所有权转让成功",
    },
    # Model messages
    "model_created": {
        "en": "Model created successfully",
        "zh": "模型创建成功",
    },
    "model_updated": {
        "en": "Model updated successfully",
        "zh": "模型更新成功",
    },
    "model_deleted": {
        "en": "Model deleted successfully",
        "zh": "模型删除成功",
    },
    "model_not_found": {
        "en": "Model not found",
        "zh": "模型未找到",
    },
    "model_already_exists": {
        "en": "Model with this provider and model ID already exists",
        "zh": "该供应商的模型 ID 已存在",
    },
    "model_api_key_required": {
        "en": "API key is required to test connection",
        "zh": "测试连接需要 API Key",
    },
    "model_test_pending": {
        "en": "Connection test pending implementation",
        "zh": "连接测试功能待实现",
    },
    "model_test_success": {
        "en": "Connection test successful",
        "zh": "连接测试成功",
    },
    "model_test_failed": {
        "en": "Connection test failed: {error}",
        "zh": "连接测试失败：{error}",
    },
    "model_set_default": {
        "en": "Model set as default successfully",
        "zh": "已设为默认模型",
    },
    "model_type_not_supported": {
        "en": "Model type is not supported",
        "zh": "不支持的模型类型",
    },
    # Team Model Authorization messages
    "team_model_authorized": {
        "en": "Model authorized to team successfully",
        "zh": "模型授权成功",
    },
    "team_model_updated": {
        "en": "Team model authorization updated successfully",
        "zh": "团队模型授权更新成功",
    },
    "team_model_revoked": {
        "en": "Model authorization revoked successfully",
        "zh": "模型授权已撤销",
    },
    "team_models_authorized": {
        "en": "Models authorized to team successfully",
        "zh": "批量授权成功",
    },
    "team_models_revoked": {
        "en": "Model authorizations revoked successfully",
        "zh": "批量撤销授权成功",
    },
    "team_model_not_found": {
        "en": "Team model authorization not found",
        "zh": "未找到团队模型授权",
    },
    "team_model_already_authorized": {
        "en": "Model is already authorized to this team",
        "zh": "该模型已被授权给此团队",
    },
    "model_not_authorized": {
        "en": "Model is not authorized for this team",
        "zh": "该模型未被授权给此团队",
    },
    "model_quota_exceeded": {
        "en": "Model quota exceeded",
        "zh": "模型配额已用尽",
    },
    # Knowledge Base messages
    "kb_created": {
        "en": "Knowledge base created successfully",
        "zh": "知识库创建成功",
    },
    "kb_updated": {
        "en": "Knowledge base updated successfully",
        "zh": "知识库更新成功",
    },
    "kb_deleted": {
        "en": "Knowledge base deleted successfully",
        "zh": "知识库删除成功",
    },
    "kb_not_found": {
        "en": "Knowledge base not found",
        "zh": "知识库未找到",
    },
    "kb_name_exists": {
        "en": "Knowledge base with this name already exists in the team",
        "zh": "该团队中已存在同名知识库",
    },
    # Document messages
    "document_uploaded": {
        "en": "Document uploaded successfully",
        "zh": "文档上传成功",
    },
    "document_created": {
        "en": "Document created successfully",
        "zh": "文档创建成功",
    },
    "document_updated": {
        "en": "Document updated successfully",
        "zh": "文档更新成功",
    },
    "document_deleted": {
        "en": "Document deleted successfully",
        "zh": "文档删除成功",
    },
    "document_not_found": {
        "en": "Document not found",
        "zh": "文档未找到",
    },
    "document_reprocess_started": {
        "en": "Document reprocessing started",
        "zh": "文档重新处理已开始",
    },
    "invalid_document_type": {
        "en": "Invalid document type. Supported: PDF, DOCX, TXT, MD, HTML, CSV, XLSX, JSON",
        "zh": "不支持的文档类型。支持：PDF、DOCX、TXT、MD、HTML、CSV、XLSX、JSON",
    },
    "file_name_required": {
        "en": "File name is required",
        "zh": "文件名不能为空",
    },
    "source_url_required": {
        "en": "Source URL is required",
        "zh": "源URL不能为空",
    },
    "search_completed": {
        "en": "Search completed",
        "zh": "搜索完成",
    },
    "chunk_preview_generated": {
        "en": "Chunk preview generated successfully",
        "zh": "分块预览生成成功",
    },
    "chunk_preview_failed": {
        "en": "Failed to generate chunk preview",
        "zh": "生成分块预览失败",
    },
    "document_no_source": {
        "en": "Document has no file or URL source",
        "zh": "文档没有文件或URL来源",
    },
    "document_processing_started": {
        "en": "Document processing started",
        "zh": "文档处理已开始",
    },
    "document_processed": {
        "en": "Document processed successfully",
        "zh": "文档处理成功",
    },
    "document_process_failed": {
        "en": "Failed to process document",
        "zh": "文档处理失败",
    },
    "document_not_pending": {
        "en": "Document is not in pending status",
        "zh": "文档不是待处理状态",
    },
    "document_is_processing": {
        "en": "Document is currently being processed, please wait",
        "zh": "文档正在处理中，请稍候",
    },
    "task_dispatch_failed": {
        "en": "Failed to dispatch processing task. Please check if Redis is running.",
        "zh": "任务调度失败。请检查 Redis 是否正常运行。",
    },
    # Chunk messages
    "chunk_not_found": {
        "en": "Chunk not found",
        "zh": "分块未找到",
    },
    "chunk_created": {
        "en": "Chunk created successfully",
        "zh": "分块创建成功",
    },
    "chunk_updated": {
        "en": "Chunk updated successfully",
        "zh": "分块更新成功",
    },
    "chunk_deleted": {
        "en": "Chunk deleted successfully",
        "zh": "分块删除成功",
    },
    "vector_update_failed": {
        "en": "Failed to update vector store",
        "zh": "向量存储更新失败",
    },
    "vector_search_failed": {
        "en": "Vector search failed: {error}",
        "zh": "向量搜索失败：{error}",
    },
    "document_rechunk_started": {
        "en": "Document re-chunking started",
        "zh": "文档重新分块已开始",
    },
    "document_processing": {
        "en": "Document is currently being processed",
        "zh": "文档正在处理中",
    },
    # Agent messages
    "agent_created": {
        "en": "Agent created successfully",
        "zh": "智能体创建成功",
    },
    "agent_updated": {
        "en": "Agent updated successfully",
        "zh": "智能体更新成功",
    },
    "agent_deleted": {
        "en": "Agent deleted successfully",
        "zh": "智能体删除成功",
    },
    "agent_not_found": {
        "en": "Agent not found",
        "zh": "智能体未找到",
    },
    "agent_published": {
        "en": "Agent published successfully",
        "zh": "智能体发布成功",
    },
    "agent_unpublished": {
        "en": "Agent unpublished successfully",
        "zh": "智能体已取消发布",
    },
    "agent_duplicated": {
        "en": "Agent duplicated successfully",
        "zh": "智能体复制成功",
    },
    "agent_not_published": {
        "en": "Agent is not published",
        "zh": "智能体未发布",
    },
    "agent_access_denied": {
        "en": "You don't have access to this agent",
        "zh": "您无权访问此智能体",
    },
    "agent_name_exists": {
        "en": "Agent with this name already exists",
        "zh": "该智能体名称已存在",
    },
    # Workflow messages
    "workflow_created": {
        "en": "Workflow created successfully",
        "zh": "工作流创建成功",
    },
    "workflow_updated": {
        "en": "Workflow updated successfully",
        "zh": "工作流更新成功",
    },
    "workflow_deleted": {
        "en": "Workflow deleted successfully",
        "zh": "工作流删除成功",
    },
    "workflow_not_found": {
        "en": "Workflow not found",
        "zh": "工作流未找到",
    },
    "workflow_name_exists": {
        "en": "Workflow with this name already exists",
        "zh": "该工作流名称已存在",
    },
    "workflow_published": {
        "en": "Workflow published successfully",
        "zh": "工作流发布成功",
    },
    "workflow_unpublished": {
        "en": "Workflow unpublished successfully",
        "zh": "工作流已取消发布",
    },
    "workflow_duplicated": {
        "en": "Workflow duplicated successfully",
        "zh": "工作流复制成功",
    },
    "workflow_not_published": {
        "en": "Workflow is not published",
        "zh": "工作流未发布",
    },
    "workflow_triggered": {
        "en": "Workflow triggered successfully",
        "zh": "工作流触发成功",
    },
    "workflow_run_started": {
        "en": "Workflow run started",
        "zh": "工作流运行已开始",
    },
    "workflow_debug_started": {
        "en": "Workflow debug started",
        "zh": "工作流调试已开始",
    },
    "workflow_execution_error": {
        "en": "Workflow execution error",
        "zh": "工作流执行错误",
    },
    "workflow_run_not_found": {
        "en": "Workflow run not found",
        "zh": "工作流运行记录未找到",
    },
    "workflow_run_cancelled": {
        "en": "Workflow run cancelled",
        "zh": "工作流运行已取消",
    },
    "workflow_run_not_cancellable": {
        "en": "Workflow run cannot be cancelled",
        "zh": "工作流运行无法取消",
    },
    "workflow_run_deleted": {
        "en": "Workflow run deleted successfully",
        "zh": "工作流运行记录删除成功",
    },
    "workflow_version_not_found": {
        "en": "Workflow version not found",
        "zh": "工作流版本未找到",
    },
    "workflow_version_created": {
        "en": "Workflow version created successfully",
        "zh": "工作流版本创建成功",
    },
    "workflow_version_restored": {
        "en": "Workflow version restored successfully",
        "zh": "工作流版本恢复成功",
    },
    "workflow_published_version_desc": {
        "en": "Published version",
        "zh": "发布版本",
    },
    "workflow_auto_saved_before_restore": {
        "en": "Auto-saved before restoring to v{version}",
        "zh": "恢复到 v{version} 前自动保存",
    },
    "workflow_restored_from_version": {
        "en": "Restored from v{version}",
        "zh": "从 v{version} 恢复",
    },
    "workflow_copy_suffix": {
        "en": "{name} (Copy)",
        "zh": "{name} (副本)",
    },
    "node_label_start": {
        "en": "Start",
        "zh": "开始",
    },
    # Workflow node type labels
    "node_type_user_input": {
        "en": "Start",
        "zh": "开始",
    },
    "node_type_trigger": {
        "en": "Trigger",
        "zh": "触发器",
    },
    "node_type_llm": {
        "en": "LLM",
        "zh": "LLM",
    },
    "node_type_answer": {
        "en": "Answer",
        "zh": "回复",
    },
    "node_type_condition": {
        "en": "Condition",
        "zh": "条件分支",
    },
    "node_type_question_classifier": {
        "en": "Question Classifier",
        "zh": "问题分类",
    },
    "node_type_code": {
        "en": "Code Execution",
        "zh": "代码执行",
    },
    "node_type_http_request": {
        "en": "HTTP Request",
        "zh": "HTTP 请求",
    },
    "node_type_tool": {
        "en": "Tool",
        "zh": "工具",
    },
    "node_type_sub_workflow": {
        "en": "Sub Workflow",
        "zh": "子工作流",
    },
    "node_type_variable_assignment": {
        "en": "Variable Assignment",
        "zh": "变量赋值",
    },
    "node_type_variable_aggregator": {
        "en": "Variable Aggregator",
        "zh": "变量聚合",
    },
    "node_type_parameter_extractor": {
        "en": "Parameter Extractor",
        "zh": "参数提取",
    },
    "node_type_iteration": {
        "en": "Iteration",
        "zh": "迭代",
    },
    "node_type_agent": {
        "en": "Agent",
        "zh": "Agent",
    },
    "node_type_end": {
        "en": "End",
        "zh": "结束",
    },
    "webhook_token_regenerated": {
        "en": "Webhook token regenerated successfully",
        "zh": "Webhook 令牌重新生成成功",
    },
    "invalid_webhook_token": {
        "en": "Invalid webhook token",
        "zh": "无效的 Webhook 令牌",
    },
    "webhook_trigger_disabled": {
        "en": "Webhook trigger is not enabled for this workflow",
        "zh": "此工作流未启用 Webhook 触发",
    },
    "workflow_runs_fetched": {
        "en": "Workflow runs fetched successfully",
        "zh": "工作流运行记录获取成功",
    },
    "workflow_run_stats_fetched": {
        "en": "Workflow run statistics fetched successfully",
        "zh": "工作流运行统计获取成功",
    },
    "workflow_run_not_found_after_execution": {
        "en": "Run not found after execution",
        "zh": "执行后未找到运行记录",
    },
    "no_changes": {
        "en": "No changes",
        "zh": "无变更",
    },
    "no_chunks_to_embed": {
        "en": "No chunks to embed",
        "zh": "没有可嵌入的分块",
    },
    # Conversation messages
    "conversation_created": {
        "en": "Conversation created successfully",
        "zh": "对话创建成功",
    },
    "conversation_updated": {
        "en": "Conversation updated successfully",
        "zh": "对话更新成功",
    },
    "conversation_deleted": {
        "en": "Conversation deleted successfully",
        "zh": "对话删除成功",
    },
    "conversations_deleted": {
        "en": "Conversations deleted successfully",
        "zh": "对话批量删除成功",
    },
    "conversation_not_found": {
        "en": "Conversation not found",
        "zh": "对话未找到",
    },
    "message_deleted": {
        "en": "Message deleted successfully",
        "zh": "消息删除成功",
    },
    "message_not_found": {
        "en": "Message not found",
        "zh": "消息未找到",
    },
    "chat_success": {
        "en": "Chat completed successfully",
        "zh": "对话完成",
    },
    "version_not_found": {
        "en": "Message version not found",
        "zh": "消息版本未找到",
    },
    "version_not_in_group": {
        "en": "Message version does not belong to this group",
        "zh": "消息版本不属于此分组",
    },
    "can_only_regenerate_assistant": {
        "en": "Can only regenerate assistant messages",
        "zh": "只能重新生成助手消息",
    },
    "no_user_message_found": {
        "en": "No user message found for regeneration",
        "zh": "未找到可用于重新生成的用户消息",
    },
    # Chat related messages
    "chat_file_upload_instruction": {
        "en": "[The user uploaded the following files, please use the markitdown tool to parse the file content:]",
        "zh": "[用户上传了以下文件，请使用 markitdown 工具解析文件内容:]",
    },
    "tool_knowledge_search": {
        "en": "Knowledge Search",
        "zh": "知识库搜索",
    },
    "tool_create_memory_entity": {
        "en": "Create Memory Entity",
        "zh": "创建记忆实体",
    },
    "tool_create_memory_relation": {
        "en": "Create Memory Relation",
        "zh": "创建记忆关系",
    },
    "tool_update_memory_entity": {
        "en": "Update Memory Entity",
        "zh": "更新记忆实体",
    },
    "tool_search_memory": {
        "en": "Search Memory",
        "zh": "搜索记忆",
    },
    "kb_no_results": {
        "en": "No relevant information found in the knowledge base.",
        "zh": "知识库中未找到相关信息。",
    },
    # File parser messages
    "truncation_marker": {
        "en": "...[content truncated]...",
        "zh": "...[内容已截断]...",
    },
    "truncation_middle_marker": {
        "en": "...[middle content truncated, {count} characters]...",
        "zh": "...[中间内容已截断，共 {count} 字符]...",
    },
    "file_header": {
        "en": "## File: {filename}",
        "zh": "## 文件: {filename}",
    },
    "file_header_indexed": {
        "en": "## File {index}: {filename}",
        "zh": "## 文件 {index}: {filename}",
    },
    "file_header_truncated_suffix": {
        "en": " (truncated, original length: {length} characters)",
        "zh": " (已截断，原始长度: {length} 字符)",
    },
    # Tool messages
    "tool_not_found": {
        "en": "Tool not found",
        "zh": "工具未找到",
    },
    "tool_created": {
        "en": "Tool created successfully",
        "zh": "工具创建成功",
    },
    "tool_updated": {
        "en": "Tool updated successfully",
        "zh": "工具更新成功",
    },
    "tool_deleted": {
        "en": "Tool deleted successfully",
        "zh": "工具删除成功",
    },
    "tool_duplicated": {
        "en": "Tool duplicated successfully",
        "zh": "工具复制成功",
    },
    "tool_name_exists": {
        "en": "Tool with this name already exists",
        "zh": "该工具名称已存在",
    },
    "tool_execute_success": {
        "en": "Tool executed successfully",
        "zh": "工具执行成功",
    },
    "tool_execute_error": {
        "en": "Tool execution failed: {error}",
        "zh": "工具执行失败：{error}",
    },
    "mcp_connection_failed": {
        "en": "Failed to connect to MCP server",
        "zh": "连接 MCP 服务器失败",
    },
    # Tool Configuration messages
    "tool_config_created": {
        "en": "Tool configuration created successfully",
        "zh": "工具配置创建成功",
    },
    "tool_config_updated": {
        "en": "Tool configuration updated successfully",
        "zh": "工具配置更新成功",
    },
    "tool_config_deleted": {
        "en": "Tool configuration deleted successfully",
        "zh": "工具配置删除成功",
    },
    "tool_config_not_found": {
        "en": "Tool configuration not found",
        "zh": "工具配置不存在",
    },
    "tool_config_already_exists": {
        "en": "Tool configuration already exists",
        "zh": "工具配置已存在",
    },
    # Tool sharing messages
    "tool_shared_successfully": {
        "en": "Tool shared successfully",
        "zh": "工具共享成功",
    },
    "tool_unshared_successfully": {
        "en": "Tool sharing revoked successfully",
        "zh": "工具共享已取消",
    },
    "tool_already_shared": {
        "en": "Tool is already shared with this team",
        "zh": "工具已经共享给该团队",
    },
    "tool_share_not_found": {
        "en": "Tool share not found",
        "zh": "工具共享记录不存在",
    },
    "cannot_share_to_own_team": {
        "en": "Cannot share tool to your own team",
        "zh": "不能将工具共享给自己的团队",
    },
    "insufficient_permission": {
        "en": "Insufficient permission to access this tool",
        "zh": "权限不足，无法访问此工具",
    },
    # API Key messages
    "api_key_created": {
        "en": "API key created successfully",
        "zh": "API 密钥创建成功",
    },
    "api_key_updated": {
        "en": "API key updated successfully",
        "zh": "API 密钥更新成功",
    },
    "api_key_deleted": {
        "en": "API key deleted successfully",
        "zh": "API 密钥删除成功",
    },
    "api_key_not_found": {
        "en": "API key not found",
        "zh": "API 密钥未找到",
    },
    "api_key_activated": {
        "en": "API key activated successfully",
        "zh": "API 密钥已激活",
    },
    "api_key_deactivated": {
        "en": "API key deactivated successfully",
        "zh": "API 密钥已禁用",
    },
    "api_key_already_active": {
        "en": "API key is already active",
        "zh": "API 密钥已经是激活状态",
    },
    "api_key_already_inactive": {
        "en": "API key is already inactive",
        "zh": "API 密钥已经是禁用状态",
    },
    "invalid_api_key": {
        "en": "Invalid API key",
        "zh": "无效的 API 密钥",
    },
    "api_key_required": {
        "en": "API key is required for webhook calls",
        "zh": "Webhook 调用需要 API 密钥",
    },
    "invalid_api_key_format": {
        "en": "Invalid API key format. Must start with 'clou_'",
        "zh": "无效的 API 密钥格式。必须以 'clou_' 开头",
    },
    "api_key_authentication_failed": {
        "en": "API key authentication failed",
        "zh": "API 密钥认证失败",
    },
    "api_key_expired": {
        "en": "API key has expired",
        "zh": "API 密钥已过期",
    },
    "api_key_no_agent_access": {
        "en": "This API key does not have access to the requested Agent",
        "zh": "此 API 密钥无权访问请求的 Agent",
    },
    "api_key_no_workflow_access": {
        "en": "This API key does not have access to the requested Workflow",
        "zh": "此 API 密钥无权访问请求的工作流",
    },
    # Audit Log
    "audit_log_not_found": {
        "en": "Audit log not found",
        "zh": "审计日志未找到",
    },
    "audit_log_login_success": {
        "en": "Login successful",
        "zh": "登录成功",
    },
    "audit_log_login_failed": {
        "en": "Login failed",
        "zh": "登录失败",
    },
    "audit_log_logout": {
        "en": "Logout",
        "zh": "登出",
    },
    "audit_log_register": {
        "en": "User registration",
        "zh": "用户注册",
    },
    "audit_log_create_user": {
        "en": "Create user",
        "zh": "创建用户",
    },
    "audit_log_update_user": {
        "en": "Update user",
        "zh": "更新用户",
    },
    "audit_log_delete_user": {
        "en": "Delete user",
        "zh": "删除用户",
    },
    "audit_log_activate_user": {
        "en": "Activate user",
        "zh": "激活用户",
    },
    "audit_log_deactivate_user": {
        "en": "Deactivate user",
        "zh": "停用用户",
    },
    "audit_log_change_password": {
        "en": "Change password",
        "zh": "修改密码",
    },
    "audit_log_reset_password": {
        "en": "Reset password",
        "zh": "重置密码",
    },
    "audit_log_create_role": {
        "en": "Create role",
        "zh": "创建角色",
    },
    "audit_log_update_role": {
        "en": "Update role",
        "zh": "更新角色",
    },
    "audit_log_delete_role": {
        "en": "Delete role",
        "zh": "删除角色",
    },
    "audit_log_create_permission": {
        "en": "Create permission",
        "zh": "创建权限",
    },
    "audit_log_update_permission": {
        "en": "Update permission",
        "zh": "更新权限",
    },
    "audit_log_delete_permission": {
        "en": "Delete permission",
        "zh": "删除权限",
    },
    "audit_log_update_settings": {
        "en": "Update site settings",
        "zh": "更新站点设置",
    },
    "audit_log_create_api_key": {
        "en": "Create API key",
        "zh": "创建 API 密钥",
    },
    "audit_log_delete_api_key": {
        "en": "Delete API key",
        "zh": "删除 API 密钥",
    },
    "audit_log_create_model": {
        "en": "Create model configuration",
        "zh": "创建模型配置",
    },
    "audit_log_update_model": {
        "en": "Update model configuration",
        "zh": "更新模型配置",
    },
    "audit_log_delete_model": {
        "en": "Delete model configuration",
        "zh": "删除模型配置",
    },
    "audit_log_create_team": {
        "en": "Create team",
        "zh": "创建团队",
    },
    "audit_log_update_team": {
        "en": "Update team",
        "zh": "更新团队",
    },
    "audit_log_delete_team": {
        "en": "Delete team",
        "zh": "删除团队",
    },
    "audit_log_create_agent": {
        "en": "Create agent",
        "zh": "创建 Agent",
    },
    "audit_log_update_agent": {
        "en": "Update agent",
        "zh": "更新 Agent",
    },
    "audit_log_delete_agent": {
        "en": "Delete agent",
        "zh": "删除 Agent",
    },
    "audit_log_publish_agent": {
        "en": "Publish agent",
        "zh": "发布 Agent",
    },
    "audit_log_unpublish_agent": {
        "en": "Unpublish agent",
        "zh": "取消发布 Agent",
    },
    "audit_log_create_kb": {
        "en": "Create knowledge base",
        "zh": "创建知识库",
    },
    "audit_log_update_kb": {
        "en": "Update knowledge base",
        "zh": "更新知识库",
    },
    "audit_log_delete_kb": {
        "en": "Delete knowledge base",
        "zh": "删除知识库",
    },
    "audit_log_create_tool": {
        "en": "Create tool",
        "zh": "创建工具",
    },
    "audit_log_update_tool": {
        "en": "Update tool",
        "zh": "更新工具",
    },
    "audit_log_delete_tool": {
        "en": "Delete tool",
        "zh": "删除工具",
    },
    "audit_log_create_workflow": {
        "en": "Create workflow",
        "zh": "创建工作流",
    },
    "audit_log_update_workflow": {
        "en": "Update workflow",
        "zh": "更新工作流",
    },
    "audit_log_delete_workflow": {
        "en": "Delete workflow",
        "zh": "删除工作流",
    },
    # Memory
    "memory_entity_not_found": {
        "en": "Memory entity not found",
        "zh": "记忆实体未找到",
    },
    "memory_relation_not_found": {
        "en": "Memory relation not found",
        "zh": "记忆关系未找到",
    },
    "memory_entity_updated": {
        "en": "Memory entity updated successfully",
        "zh": "记忆实体更新成功",
    },
    "memory_entity_deleted": {
        "en": "Memory entity deleted successfully",
        "zh": "记忆实体删除成功",
    },
    "memory_relation_deleted": {
        "en": "Memory relation deleted successfully",
        "zh": "记忆关系删除成功",
    },
    "audit_log_update_memory_entity": {
        "en": "Update memory entity",
        "zh": "更新记忆实体",
    },
    "audit_log_delete_memory_entity": {
        "en": "Delete memory entity",
        "zh": "删除记忆实体",
    },
    "audit_log_delete_memory_relation": {
        "en": "Delete memory relation",
        "zh": "删除记忆关系",
    },
    "audit_log_agent_create_memory_entity": {
        "en": "Agent created memory entity",
        "zh": "Agent 创建记忆实体",
    },
    "audit_log_agent_create_memory_relation": {
        "en": "Agent created memory relation",
        "zh": "Agent 创建记忆关系",
    },
    "audit_log_agent_update_memory_entity": {
        "en": "Agent updated memory entity",
        "zh": "Agent 更新记忆实体",
    },
    # SSO
    "sso_provider_not_found": {
        "en": "SSO provider not found",
        "zh": "SSO 提供商不存在",
    },
    "sso_connection_not_found": {
        "en": "SSO connection not found",
        "zh": "SSO 连接未找到",
    },
    "cannot_disconnect_only_auth_method": {
        "en": "Cannot disconnect the only authentication method. Please set a password first.",
        "zh": "无法解除唯一的认证方式。请先设置密码。",
    },
    "sso_session_expired": {
        "en": "SSO session expired",
        "zh": "SSO 会话已过期",
    },
    "sso_registration_disabled": {
        "en": "SSO registration is disabled",
        "zh": "SSO 注册已禁用",
    },
    "sso_login_failed": {
        "en": "SSO login failed",
        "zh": "SSO 登录失败",
    },
    "password_login_disabled": {
        "en": "Password login is disabled. Please use SSO to sign in.",
        "zh": "密码登录已禁用。请使用 SSO 登录。",
    },
    "sso_provider_name_exists": {
        "en": "SSO provider name already exists",
        "zh": "SSO 提供商名称已存在",
    },
    "sso_invalid_provider_name": {
        "en": "Provider name must start with a lowercase letter and contain only lowercase letters, numbers, hyphens, and underscores",
        "zh": "提供商名称必须以小写字母开头，且只能包含小写字母、数字、连字符和下划线",
    },
    "sso_invalid_icon_url": {
        "en": "Icon URL must start with http:// or https://",
        "zh": "图标 URL 必须以 http:// 或 https:// 开头",
    },
    "require_superadmin_sso": {
        "en": "At least one super admin must have an SSO connection before disabling password login.",
        "zh": "关闭密码登录前，至少需要一个超级管理员已绑定 SSO。",
    },
    "unsupported_protocol": {
        "en": "Unsupported SSO protocol",
        "zh": "不支持的 SSO 协议",
    },
    "missing_user_id": {
        "en": "Missing user ID from SSO provider",
        "zh": "SSO 提供商未返回用户 ID",
    },
    "email_required": {
        "en": "Email is required for SSO registration",
        "zh": "SSO 注册需要邮箱地址",
    },
    "sso_provider_config_valid": {
        "en": "Provider configuration is valid",
        "zh": "SSO 提供商配置有效",
    },
    "sso_provider_config_error": {
        "en": "Provider configuration error: {error}",
        "zh": "SSO 提供商配置错误：{error}",
    },
    # SSO Audit logs
    "audit_log_sso_login_success": {
        "en": "SSO login",
        "zh": "SSO 登录",
    },
    "audit_log_sso_login_failed": {
        "en": "SSO login failed",
        "zh": "SSO 登录失败",
    },
    "audit_log_create_sso_provider": {
        "en": "Create SSO provider",
        "zh": "创建 SSO 提供商",
    },
    "audit_log_update_sso_provider": {
        "en": "Update SSO provider",
        "zh": "更新 SSO 提供商",
    },
    "audit_log_delete_sso_provider": {
        "en": "Delete SSO provider",
        "zh": "删除 SSO 提供商",
    },
    "audit_log_update_auto_notification_config": {
        "en": "Update auto notification config",
        "zh": "更新自动通知配置",
    },
    # Auto Notification Messages
    "notify_team_member_added_title": {
        "en": "You have joined a team",
        "zh": "您已加入团队",
    },
    "notify_team_member_added_content": {
        "en": "You have been added to team **{team_name}** by **{operator}** with role **{role}**.",
        "zh": "您已被 **{operator}** 添加到团队 **{team_name}**，角色为 **{role}**。",
    },
    "notify_team_member_added_team_title": {
        "en": "New member joined",
        "zh": "新成员加入",
    },
    "notify_team_member_added_team_content": {
        "en": "**{username}** has joined the team with role **{role}**.",
        "zh": "**{username}** 已加入团队，角色为 **{role}**。",
    },
    "notify_team_member_removed_title": {
        "en": "You have left the team",
        "zh": "您已离开团队",
    },
    "notify_team_member_removed_content": {
        "en": "You have been removed from team **{team_name}**.",
        "zh": "您已被从团队 **{team_name}** 中移除。",
    },
    "notify_team_member_removed_team_title": {
        "en": "Member left",
        "zh": "成员离开",
    },
    "notify_team_member_removed_team_content": {
        "en": "**{username}** has left the team.",
        "zh": "**{username}** 已离开团队。",
    },
    "notify_team_role_changed_title": {
        "en": "Team role changed",
        "zh": "团队角色变更",
    },
    "notify_team_role_changed_content": {
        "en": "Your role in team **{team_name}** has been changed from **{old_role}** to **{new_role}**.",
        "zh": "您在团队 **{team_name}** 中的角色已从 **{old_role}** 变更为 **{new_role}**。",
    },
    "notify_user_activated_title": {
        "en": "Account activated",
        "zh": "账户已激活",
    },
    "notify_user_activated_content": {
        "en": "Your account has been activated by the administrator. You can now use the system.",
        "zh": "您的账户已被管理员激活，现在可以正常使用系统了。",
    },
    "notify_user_deactivated_title": {
        "en": "Account deactivated",
        "zh": "账户已停用",
    },
    "notify_user_deactivated_content": {
        "en": "Your account has been deactivated by the administrator. Please contact the administrator if you have any questions.",
        "zh": "您的账户已被管理员停用，如有疑问请联系管理员。",
    },
    "notify_user_password_reset_title": {
        "en": "Password reset",
        "zh": "密码已重置",
    },
    "notify_user_password_reset_content": {
        "en": "Your password has been reset by the administrator. Please log in with your new password.",
        "zh": "您的密码已被管理员重置，请使用新密码登录。",
    },
    "notify_agent_published_title": {
        "en": "Agent published",
        "zh": "Agent 已发布",
    },
    "notify_agent_published_content": {
        "en": "Agent **{agent_name}** has been published and is now available for use.",
        "zh": "Agent **{agent_name}** 已发布，现在可以使用了。",
    },
    "notify_agent_unpublished_title": {
        "en": "Agent unpublished",
        "zh": "Agent 已下线",
    },
    "notify_agent_unpublished_content": {
        "en": "Agent **{agent_name}** has been unpublished.",
        "zh": "Agent **{agent_name}** 已下线。",
    },
    # Knowledge Base Document Notifications
    "notify_kb_doc_indexed_title": {
        "en": "Document indexed successfully",
        "zh": "文档索引成功",
    },
    "notify_kb_doc_indexed_content": {
        "en": "Document **{doc_name}** in knowledge base **{kb_name}** has been indexed successfully. Chunks: {chunk_count}, Tokens: {token_count}.",
        "zh": "知识库 **{kb_name}** 中的文档 **{doc_name}** 已成功索引。分块数：{chunk_count}，Token 数：{token_count}。",
    },
    "notify_kb_doc_failed_title": {
        "en": "Document indexing failed",
        "zh": "文档索引失败",
    },
    "notify_kb_doc_failed_content": {
        "en": "Document **{doc_name}** in knowledge base **{kb_name}** failed to index. Error: {error}",
        "zh": "知识库 **{kb_name}** 中的文档 **{doc_name}** 索引失败。错误：{error}",
    },
    # Workflow Run Notifications
    "notify_workflow_run_success_title": {
        "en": "Workflow run completed",
        "zh": "工作流运行完成",
    },
    "notify_workflow_run_success_content": {
        "en": "Workflow **{workflow_name}** has completed successfully. Duration: {duration}ms, Nodes executed: {node_count}.",
        "zh": "工作流 **{workflow_name}** 已成功完成。耗时：{duration}ms，执行节点数：{node_count}。",
    },
    "notify_workflow_run_failed_title": {
        "en": "Workflow run failed",
        "zh": "工作流运行失败",
    },
    "notify_workflow_run_failed_content": {
        "en": "Workflow **{workflow_name}** has failed. Error: {error}",
        "zh": "工作流 **{workflow_name}** 运行失败。错误：{error}",
    },
    # Team Ownership Transfer Notifications
    "notify_team_ownership_received_title": {
        "en": "Team ownership received",
        "zh": "获得团队所有权",
    },
    "notify_team_ownership_received_content": {
        "en": "You have received ownership of team **{team_name}** from **{old_owner}**.",
        "zh": "您已从 **{old_owner}** 处获得团队 **{team_name}** 的所有权。",
    },
    "notify_team_ownership_transferred_title": {
        "en": "Team ownership transferred",
        "zh": "团队所有权已转让",
    },
    "notify_team_ownership_transferred_content": {
        "en": "You have transferred ownership of team **{team_name}** to **{new_owner}**.",
        "zh": "您已将团队 **{team_name}** 的所有权转让给 **{new_owner}**。",
    },
    # Team Model Authorization Notifications
    "notify_team_model_granted_title": {
        "en": "Model authorized",
        "zh": "模型已授权",
    },
    "notify_team_model_granted_content": {
        "en": "Model **{model_name}** has been authorized for your team **{team_name}**.",
        "zh": "模型 **{model_name}** 已授权给团队 **{team_name}**。",
    },
    "notify_team_model_revoked_title": {
        "en": "Model authorization revoked",
        "zh": "模型授权已撤销",
    },
    "notify_team_model_revoked_content": {
        "en": "Model **{model_name}** authorization has been revoked from your team **{team_name}**.",
        "zh": "团队 **{team_name}** 的模型 **{model_name}** 授权已被撤销。",
    },
    # User Pending Approval Notification
    "notify_user_pending_approval_title": {
        "en": "New user pending approval",
        "zh": "新用户待审批",
    },
    "notify_user_pending_approval_content": {
        "en": "A new user **{username}** ({email}) has registered and is pending approval.",
        "zh": "新用户 **{username}** ({email}) 已注册，等待审批。",
    },
    # Security Notifications
    "notify_account_locked_title": {
        "en": "Account locked",
        "zh": "账户已锁定",
    },
    "notify_account_locked_content": {
        "en": "Your account has been locked due to too many failed login attempts. It will be unlocked in {lockout_minutes} minutes.",
        "zh": "由于登录失败次数过多，您的账户已被锁定。将在 {lockout_minutes} 分钟后解锁。",
    },
    "notify_password_changed_title": {
        "en": "Password changed",
        "zh": "密码已修改",
    },
    "notify_password_changed_content": {
        "en": "Your password has been changed successfully. If you did not make this change, please contact the administrator immediately.",
        "zh": "您的密码已成功修改。如果这不是您本人的操作，请立即联系管理员。",
    },
    # API Key expiration notifications
    "notify_apikey_expiring_title": {
        "en": "API Key expiring soon",
        "zh": "API 密钥即将过期",
    },
    "notify_apikey_expiring_content": {
        "en": "Your API Key **{key_name}** ({key_prefix}...) will expire in {days} days. Please renew it to avoid service interruption.",
        "zh": "您的 API 密钥 **{key_name}** ({key_prefix}...) 将在 {days} 天后过期。请及时续期以避免服务中断。",
    },
    "notify_apikey_expired_title": {
        "en": "API Key expired",
        "zh": "API 密钥已过期",
    },
    "notify_apikey_expired_content": {
        "en": "Your API Key **{key_name}** ({key_prefix}...) has expired and is no longer valid. Please create a new API Key if needed.",
        "zh": "您的 API 密钥 **{key_name}** ({key_prefix}...) 已过期，无法继续使用。如需使用请创建新的 API 密钥。",
    },
    # Login anomaly notification
    "notify_login_anomaly_title": {
        "en": "Unusual login detected",
        "zh": "检测到异常登录",
    },
    "notify_login_anomaly_content": {
        "en": "A login to your account was detected from an unusual location or device.\n\n- **IP Address**: {ip_address}\n- **Time**: {login_time}\n- **User Agent**: {user_agent}\n\nIf this was not you, please change your password immediately.",
        "zh": "检测到您的账户从异常位置或设备登录。\n\n- **IP 地址**: {ip_address}\n- **时间**: {login_time}\n- **设备信息**: {user_agent}\n\n如果这不是您本人的操作，请立即修改密码。",
    },
    # Email notification templates
    "email_view_details": {
        "en": "View Details",
        "zh": "查看详情",
    },
    "email_footer": {
        "en": "This email was sent automatically by {site_name}. Please do not reply.",
        "zh": "此邮件由 {site_name} 系统自动发送，请勿回复。",
    },
    "email_team_prefix": {
        "en": "Team",
        "zh": "团队",
    },
    "email_user_prefix": {
        "en": "User",
        "zh": "用户",
    },
    # Builtin tool display names
    "builtin_tool_get_current_time": {
        "en": "Get Current Time",
        "zh": "获取当前时间",
    },
    "builtin_tool_format_datetime": {
        "en": "Format DateTime",
        "zh": "格式化日期时间",
    },
    "builtin_tool_calculate": {
        "en": "Calculate",
        "zh": "数学计算",
    },
    "builtin_tool_unit_convert": {
        "en": "Unit Convert",
        "zh": "单位转换",
    },
    "builtin_tool_web_search": {
        "en": "Web Search",
        "zh": "网页搜索",
    },
    "builtin_tool_fetch_webpage": {
        "en": "Fetch Webpage",
        "zh": "获取网页内容",
    },
    "builtin_tool_markitdown": {
        "en": "MarkItDown File Parser",
        "zh": "MarkItDown 文件解析",
    },
    # Memory messages
    "memory_entity_created": {
        "en": "Memory entity created successfully",
        "zh": "记忆实体创建成功",
    },
    "memory_entity_updated": {
        "en": "Memory entity updated successfully",
        "zh": "记忆实体更新成功",
    },
    "memory_entity_deleted": {
        "en": "Memory entity deleted successfully",
        "zh": "记忆实体删除成功",
    },
    "memory_entity_not_found": {
        "en": "Memory entity not found",
        "zh": "记忆实体不存在",
    },
    "memory_entity_create_failed": {
        "en": "Failed to create memory entity",
        "zh": "创建记忆实体失败",
    },
    "memory_entity_update_failed": {
        "en": "Failed to update memory entity",
        "zh": "更新记忆实体失败",
    },
    "memory_entity_delete_failed": {
        "en": "Failed to delete memory entity",
        "zh": "删除记忆实体失败",
    },
    "memory_relation_created": {
        "en": "Memory relation created successfully",
        "zh": "记忆关系创建成功",
    },
    "memory_relation_deleted": {
        "en": "Memory relation deleted successfully",
        "zh": "记忆关系删除成功",
    },
    "memory_relation_not_found": {
        "en": "Memory relation not found",
        "zh": "记忆关系不存在",
    },
    "memory_relation_create_failed": {
        "en": "Failed to create memory relation",
        "zh": "创建记忆关系失败",
    },
    "memory_relation_delete_failed": {
        "en": "Failed to delete memory relation",
        "zh": "删除记忆关系失败",
    },
    # Audit log - Memory operations
    "audit_log_create_memory_entity": {
        "en": "Create memory entity",
        "zh": "创建记忆实体",
    },
    "audit_log_update_memory_entity": {
        "en": "Update memory entity",
        "zh": "更新记忆实体",
    },
    "audit_log_delete_memory_entity": {
        "en": "Delete memory entity",
        "zh": "删除记忆实体",
    },
    "audit_log_create_memory_relation": {
        "en": "Create memory relation",
        "zh": "创建记忆关系",
    },
    "audit_log_delete_memory_relation": {
        "en": "Delete memory relation",
        "zh": "删除记忆关系",
    },
}


def get_language() -> str:
    """Get current language from context variable"""
    return current_language.get()


def set_language(lang: str) -> None:
    """Set current language in context variable"""
    # Normalize language code
    lang = lang.lower().split("-")[0]  # "zh-CN" -> "zh"
    if lang not in [lang_enum.value for lang_enum in Language]:
        lang = Language.EN.value
    current_language.set(lang)


async def get_default_language() -> str:
    """Get default language from site settings.

    This is used for system messages when no specific user locale is available,
    such as team notifications, webhook-triggered workflows, etc.
    """
    from app.models.site_setting import SiteSetting

    lang = await SiteSetting.get_value("default_language", "en")
    # Normalize language code
    lang = str(lang).lower().split("-")[0]
    if lang not in [lang_enum.value for lang_enum in Language]:
        lang = Language.EN.value
    return lang


def t(key: str, lang: Optional[str] = None, **kwargs) -> str:
    """
    Translate a message key to the current language.

    Args:
        key: Message key to translate
        lang: Optional language override (defaults to current context language)
        **kwargs: Format arguments for the message

    Returns:
        Translated message string
    """
    if lang is None:
        lang = get_language()

    # Normalize language code
    lang = lang.lower().split("-")[0]
    if lang not in [lang_enum.value for lang_enum in Language]:
        lang = Language.EN.value

    # Get translation
    translations = TRANSLATIONS.get(key, {})
    message = translations.get(lang) or translations.get(Language.EN.value, key)

    # Apply format arguments
    if kwargs:
        try:
            message = message.format(**kwargs)
        except (KeyError, ValueError):
            pass

    return message


def get_code_message(code: int, lang: Optional[str] = None) -> str:
    """
    Get translated message for a ResponseCode.
    Maps ResponseCode values to translation keys.
    """
    from app.schemas.response import ResponseCode

    # Map ResponseCode to translation key
    code_to_key = {
        ResponseCode.SUCCESS: "success",
        ResponseCode.UNKNOWN_ERROR: "unknown_error",
        ResponseCode.VALIDATION_ERROR: "validation_error",
        ResponseCode.UNAUTHORIZED: "unauthorized",
        ResponseCode.INVALID_TOKEN: "invalid_token",
        ResponseCode.TOKEN_EXPIRED: "token_expired",
        ResponseCode.INVALID_CREDENTIALS: "invalid_credentials",
        ResponseCode.INACTIVE_USER: "inactive_user",
        ResponseCode.PERMISSION_DENIED: "permission_denied",
        ResponseCode.INSUFFICIENT_PRIVILEGES: "insufficient_privileges",
        ResponseCode.NOT_FOUND: "not_found",
        ResponseCode.USER_NOT_FOUND: "user_not_found",
        ResponseCode.ROLE_NOT_FOUND: "role_not_found",
        ResponseCode.PERMISSION_NOT_FOUND: "permission_not_found",
        ResponseCode.REGISTRATION_DISABLED: "registration_disabled",
        ResponseCode.ALREADY_EXISTS: "already_exists",
        ResponseCode.USERNAME_EXISTS: "username_exists",
        ResponseCode.EMAIL_EXISTS: "email_exists",
        ResponseCode.EMAIL_NOT_VERIFIED: "email_not_verified",
        ResponseCode.VERIFICATION_CODE_INVALID: "verification_code_invalid",
        ResponseCode.VERIFICATION_CODE_EXPIRED: "verification_token_invalid",
        ResponseCode.EMAIL_SEND_FAILED: "smtp_not_configured",
        ResponseCode.EMAIL_SEND_TOO_FREQUENT: "email_send_too_frequent",
        ResponseCode.ROLE_NAME_EXISTS: "role_name_exists",
        ResponseCode.PERMISSION_CODE_EXISTS: "permission_code_exists",
        ResponseCode.CANNOT_DELETE_SYSTEM_ROLE: "cannot_delete_system_role",
        ResponseCode.CANNOT_DELETE_SUPERUSER: "cannot_delete_superuser",
        ResponseCode.CANNOT_DELETE_WILDCARD_PERMISSION: "cannot_delete_wildcard_permission",
        ResponseCode.CANNOT_MODIFY_SYSTEM_ROLE: "cannot_modify_system_role",
        ResponseCode.ROLE_IN_USE: "role_in_use",
        ResponseCode.ACCOUNT_LOCKED: "account_locked",
        ResponseCode.TOO_MANY_LOGIN_ATTEMPTS: "account_locked_after_attempts",
        ResponseCode.CAPTCHA_REQUIRED: "captcha_required",
        ResponseCode.CAPTCHA_INVALID: "captcha_invalid",
    }

    try:
        response_code = ResponseCode(code)
        key = code_to_key.get(response_code, "unknown_error")
    except ValueError:
        key = "unknown_error"

    return t(key, lang)
