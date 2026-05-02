"""
System Permissions Definition

All system permissions are defined here as the single source of truth.
These permissions are automatically synced to the database on startup.
"""

from typing import TypedDict


class PermissionDefinition(TypedDict):
    """Permission definition structure"""

    code: str
    scope: str
    description: str


class SystemPermissions:
    """
    System Permission Constants

    All permissions used in the application must be defined here.
    Format: SCOPE_RESOURCE_ACTION (e.g., ADMIN_USER_CREATE)
    """

    # ============ Admin Dashboard ============
    ADMIN_DASHBOARD_ACCESS = "admin:dashboard:access"

    # ============ Admin User Management ============
    ADMIN_USER_READ = "admin:user:read"
    ADMIN_USER_CREATE = "admin:user:create"
    ADMIN_USER_UPDATE = "admin:user:update"
    ADMIN_USER_DELETE = "admin:user:delete"

    # ============ Admin Role Management ============
    ADMIN_ROLE_READ = "admin:role:read"
    ADMIN_ROLE_CREATE = "admin:role:create"
    ADMIN_ROLE_UPDATE = "admin:role:update"
    ADMIN_ROLE_DELETE = "admin:role:delete"

    # ============ Admin Permission Management ============
    ADMIN_PERMISSION_READ = "admin:permission:read"
    ADMIN_PERMISSION_CREATE = "admin:permission:create"
    ADMIN_PERMISSION_UPDATE = "admin:permission:update"
    ADMIN_PERMISSION_DELETE = "admin:permission:delete"

    # ============ Admin Team Management ============
    ADMIN_TEAM_READ = "admin:team:read"
    ADMIN_TEAM_CREATE = "admin:team:create"
    ADMIN_TEAM_UPDATE = "admin:team:update"
    ADMIN_TEAM_DELETE = "admin:team:delete"

    # ============ Admin Model Management ============
    ADMIN_MODEL_READ = "admin:model:read"
    ADMIN_MODEL_CREATE = "admin:model:create"
    ADMIN_MODEL_UPDATE = "admin:model:update"
    ADMIN_MODEL_DELETE = "admin:model:delete"

    # ============ Admin Capability Management ============
    ADMIN_CAPABILITY_READ = "admin:capability:read"
    ADMIN_CAPABILITY_CREATE = "admin:capability:create"
    ADMIN_CAPABILITY_UPDATE = "admin:capability:update"
    ADMIN_CAPABILITY_DELETE = "admin:capability:delete"
    ADMIN_CAPABILITY_EXECUTE = "admin:capability:execute"

    # ============ Admin Settings Management ============
    ADMIN_SETTINGS_READ = "admin:settings:read"
    ADMIN_SETTINGS_UPDATE = "admin:settings:update"

    # ============ Admin SSO Management ============
    ADMIN_SSO_READ = "admin:sso:read"
    ADMIN_SSO_UPDATE = "admin:sso:update"

    # ============ Admin Conversation Management ============
    ADMIN_CONVERSATION_READ = "admin:conversation:read"
    ADMIN_CONVERSATION_DELETE = "admin:conversation:delete"

    # ============ Admin Memory Management ============
    ADMIN_MEMORY_READ = "admin:memory:read"
    ADMIN_MEMORY_UPDATE = "admin:memory:update"
    ADMIN_MEMORY_DELETE = "admin:memory:delete"

    # ============ Admin Notification Management ============
    ADMIN_NOTIFICATION_CREATE = "admin:notification:create"
    ADMIN_NOTIFICATION_DELETE = "admin:notification:delete"

    # ============ Audit Log Management ============
    ADMIN_AUDIT_READ = "audit:read"
    ADMIN_AUDIT_EXPORT = "audit:export"

    # ============ Platform Team Management ============
    TEAM_READ = "team:read"
    TEAM_CREATE = "team:create"
    TEAM_UPDATE = "team:update"
    TEAM_DELETE = "team:delete"
    TEAM_MANAGE = "team:manage"

    # ============ Platform Agent Management ============
    AGENT_READ = "agent:read"
    AGENT_CREATE = "agent:create"
    AGENT_UPDATE = "agent:update"
    AGENT_DELETE = "agent:delete"
    AGENT_PUBLISH = "agent:publish"
    AGENT_CHAT = "agent:chat"

    # ============ Platform Workflow Management ============
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_UPDATE = "workflow:update"
    WORKFLOW_DELETE = "workflow:delete"
    WORKFLOW_PUBLISH = "workflow:publish"
    WORKFLOW_RUN = "workflow:run"
    WORKFLOW_EXECUTE = "workflow:execute"

    # ============ Platform Knowledge Base Management ============
    KB_READ = "kb:read"
    KB_CREATE = "kb:create"
    KB_UPDATE = "kb:update"
    KB_DELETE = "kb:delete"

    # ============ Platform Tool Management ============
    TOOL_READ = "tool:read"
    TOOL_CREATE = "tool:create"
    TOOL_UPDATE = "tool:update"
    TOOL_DELETE = "tool:delete"
    TOOL_EXECUTE = "tool:execute"

    # ============ Platform Skill Management ============
    SKILL_READ = "skill:read"
    SKILL_CREATE = "skill:create"
    SKILL_UPDATE = "skill:update"
    SKILL_DELETE = "skill:delete"
    SKILL_EXECUTE = "skill:execute"

    # ============ Platform API Key Management ============
    APIKEY_READ = "apikey:read"
    APIKEY_CREATE = "apikey:create"
    APIKEY_UPDATE = "apikey:update"
    APIKEY_DELETE = "apikey:delete"

    # ============ Platform Conversation Management ============
    CONVERSATION_READ = "conversation:read"
    CONVERSATION_DELETE = "conversation:delete"

    # ============ Platform Memory Management ============
    MEMORY_READ = "memory:read"
    MEMORY_CREATE = "memory:create"
    MEMORY_UPDATE = "memory:update"
    MEMORY_DELETE = "memory:delete"

    @classmethod
    def get_all_definitions(cls) -> list[PermissionDefinition]:
        """
        Get all permission definitions

        Returns:
            List of permission definitions with code, scope, and description
        """
        return [
            # Admin Dashboard
            {
                "code": cls.ADMIN_DASHBOARD_ACCESS,
                "scope": "admin",
                "description": "Access admin dashboard and view system statistics",
            },
            # Admin User Management
            {
                "code": cls.ADMIN_USER_READ,
                "scope": "admin",
                "description": "View all users in system",
            },
            {
                "code": cls.ADMIN_USER_CREATE,
                "scope": "admin",
                "description": "Create new users",
            },
            {
                "code": cls.ADMIN_USER_UPDATE,
                "scope": "admin",
                "description": "Update user information and activate/deactivate users",
            },
            {
                "code": cls.ADMIN_USER_DELETE,
                "scope": "admin",
                "description": "Delete users from system",
            },
            # Admin Role Management
            {
                "code": cls.ADMIN_ROLE_READ,
                "scope": "admin",
                "description": "View all roles in system",
            },
            {
                "code": cls.ADMIN_ROLE_CREATE,
                "scope": "admin",
                "description": "Create new roles",
            },
            {
                "code": cls.ADMIN_ROLE_UPDATE,
                "scope": "admin",
                "description": "Update role information and permissions",
            },
            {
                "code": cls.ADMIN_ROLE_DELETE,
                "scope": "admin",
                "description": "Delete roles from system",
            },
            # Admin Permission Management
            {
                "code": cls.ADMIN_PERMISSION_READ,
                "scope": "admin",
                "description": "View all permissions in system",
            },
            {
                "code": cls.ADMIN_PERMISSION_CREATE,
                "scope": "admin",
                "description": "Create new permissions",
            },
            {
                "code": cls.ADMIN_PERMISSION_UPDATE,
                "scope": "admin",
                "description": "Update permission information",
            },
            {
                "code": cls.ADMIN_PERMISSION_DELETE,
                "scope": "admin",
                "description": "Delete permissions from system",
            },
            # Admin Team Management
            {
                "code": cls.ADMIN_TEAM_READ,
                "scope": "admin",
                "description": "View all teams in system",
            },
            {
                "code": cls.ADMIN_TEAM_CREATE,
                "scope": "admin",
                "description": "Create new teams",
            },
            {
                "code": cls.ADMIN_TEAM_UPDATE,
                "scope": "admin",
                "description": "Update any team in system",
            },
            {
                "code": cls.ADMIN_TEAM_DELETE,
                "scope": "admin",
                "description": "Delete teams from system",
            },
            # Admin Model Management
            {
                "code": cls.ADMIN_MODEL_READ,
                "scope": "admin",
                "description": "View all AI models in system",
            },
            {
                "code": cls.ADMIN_MODEL_CREATE,
                "scope": "admin",
                "description": "Add new AI models",
            },
            {
                "code": cls.ADMIN_MODEL_UPDATE,
                "scope": "admin",
                "description": "Update model configuration and test connections",
            },
            {
                "code": cls.ADMIN_MODEL_DELETE,
                "scope": "admin",
                "description": "Delete AI models from system",
            },
            # Admin Capability Management
            {
                "code": cls.ADMIN_CAPABILITY_READ,
                "scope": "admin",
                "description": "View all capabilities in system",
            },
            {
                "code": cls.ADMIN_CAPABILITY_CREATE,
                "scope": "admin",
                "description": "Create tools and import skills for any scope",
            },
            {
                "code": cls.ADMIN_CAPABILITY_UPDATE,
                "scope": "admin",
                "description": "Update tools and skills across the system",
            },
            {
                "code": cls.ADMIN_CAPABILITY_DELETE,
                "scope": "admin",
                "description": "Delete tools and skills across the system",
            },
            {
                "code": cls.ADMIN_CAPABILITY_EXECUTE,
                "scope": "admin",
                "description": "Test and execute tools and skills from admin",
            },
            # Admin Settings Management
            {
                "code": cls.ADMIN_SETTINGS_READ,
                "scope": "admin",
                "description": "View system settings",
            },
            {
                "code": cls.ADMIN_SETTINGS_UPDATE,
                "scope": "admin",
                "description": "Update system settings and test integrations",
            },
            # Admin SSO Management
            {
                "code": cls.ADMIN_SSO_READ,
                "scope": "admin",
                "description": "View SSO providers and configuration",
            },
            {
                "code": cls.ADMIN_SSO_UPDATE,
                "scope": "admin",
                "description": "Manage SSO providers and user SSO connections",
            },
            # Admin Conversation Management
            {
                "code": cls.ADMIN_CONVERSATION_READ,
                "scope": "admin",
                "description": "View all conversations in system",
            },
            {
                "code": cls.ADMIN_CONVERSATION_DELETE,
                "scope": "admin",
                "description": "Delete any conversation in system",
            },
            # Admin Memory Management
            {
                "code": cls.ADMIN_MEMORY_READ,
                "scope": "admin",
                "description": "View all user memories in system",
            },
            {
                "code": cls.ADMIN_MEMORY_UPDATE,
                "scope": "admin",
                "description": "Update user memories",
            },
            {
                "code": cls.ADMIN_MEMORY_DELETE,
                "scope": "admin",
                "description": "Delete user memories",
            },
            # Admin Notification Management
            {
                "code": cls.ADMIN_NOTIFICATION_CREATE,
                "scope": "admin",
                "description": "Create and send notifications to users",
            },
            {
                "code": cls.ADMIN_NOTIFICATION_DELETE,
                "scope": "admin",
                "description": "Delete notifications",
            },
            # Audit Log Management
            {
                "code": cls.ADMIN_AUDIT_READ,
                "scope": "audit",
                "description": "View audit logs",
            },
            {
                "code": cls.ADMIN_AUDIT_EXPORT,
                "scope": "audit",
                "description": "Export and archive audit logs",
            },
            # Platform Team Management
            {
                "code": cls.TEAM_READ,
                "scope": "team",
                "description": "View team information",
            },
            {
                "code": cls.TEAM_CREATE,
                "scope": "team",
                "description": "Create teams",
            },
            {
                "code": cls.TEAM_UPDATE,
                "scope": "team",
                "description": "Update team information",
            },
            {
                "code": cls.TEAM_DELETE,
                "scope": "team",
                "description": "Delete teams",
            },
            {
                "code": cls.TEAM_MANAGE,
                "scope": "team",
                "description": "Manage team members and permissions",
            },
            # Platform Agent Management
            {
                "code": cls.AGENT_READ,
                "scope": "agent",
                "description": "View agents",
            },
            {
                "code": cls.AGENT_CREATE,
                "scope": "agent",
                "description": "Create new agents",
            },
            {
                "code": cls.AGENT_UPDATE,
                "scope": "agent",
                "description": "Update agent configuration",
            },
            {
                "code": cls.AGENT_DELETE,
                "scope": "agent",
                "description": "Delete agents",
            },
            {
                "code": cls.AGENT_PUBLISH,
                "scope": "agent",
                "description": "Publish agents to marketplace",
            },
            {
                "code": cls.AGENT_CHAT,
                "scope": "agent",
                "description": "Chat with agents",
            },
            # Platform Workflow Management
            {
                "code": cls.WORKFLOW_READ,
                "scope": "workflow",
                "description": "View workflows",
            },
            {
                "code": cls.WORKFLOW_CREATE,
                "scope": "workflow",
                "description": "Create new workflows",
            },
            {
                "code": cls.WORKFLOW_UPDATE,
                "scope": "workflow",
                "description": "Update workflow configuration",
            },
            {
                "code": cls.WORKFLOW_DELETE,
                "scope": "workflow",
                "description": "Delete workflows",
            },
            {
                "code": cls.WORKFLOW_PUBLISH,
                "scope": "workflow",
                "description": "Publish workflows",
            },
            {
                "code": cls.WORKFLOW_RUN,
                "scope": "workflow",
                "description": "Run workflows",
            },
            {
                "code": cls.WORKFLOW_EXECUTE,
                "scope": "workflow",
                "description": "Execute workflows",
            },
            # Platform Knowledge Base Management
            {
                "code": cls.KB_READ,
                "scope": "kb",
                "description": "View knowledge bases",
            },
            {
                "code": cls.KB_CREATE,
                "scope": "kb",
                "description": "Create new knowledge bases",
            },
            {
                "code": cls.KB_UPDATE,
                "scope": "kb",
                "description": "Update knowledge base content",
            },
            {
                "code": cls.KB_DELETE,
                "scope": "kb",
                "description": "Delete knowledge bases",
            },
            # Platform Tool Management
            {
                "code": cls.TOOL_READ,
                "scope": "tool",
                "description": "View tools",
            },
            {
                "code": cls.TOOL_CREATE,
                "scope": "tool",
                "description": "Create new tools",
            },
            {
                "code": cls.TOOL_UPDATE,
                "scope": "tool",
                "description": "Update tool configuration",
            },
            {
                "code": cls.TOOL_DELETE,
                "scope": "tool",
                "description": "Delete tools",
            },
            {
                "code": cls.TOOL_EXECUTE,
                "scope": "tool",
                "description": "Execute tools",
            },
            # Platform Skill Management
            {
                "code": cls.SKILL_READ,
                "scope": "skill",
                "description": "View skills",
            },
            {
                "code": cls.SKILL_CREATE,
                "scope": "skill",
                "description": "Import skills",
            },
            {
                "code": cls.SKILL_UPDATE,
                "scope": "skill",
                "description": "Update skill configuration",
            },
            {
                "code": cls.SKILL_DELETE,
                "scope": "skill",
                "description": "Delete skills",
            },
            {
                "code": cls.SKILL_EXECUTE,
                "scope": "skill",
                "description": "Test and execute skills",
            },
            # Platform API Key Management
            {
                "code": cls.APIKEY_READ,
                "scope": "apikey",
                "description": "View API keys",
            },
            {
                "code": cls.APIKEY_CREATE,
                "scope": "apikey",
                "description": "Create API keys",
            },
            {
                "code": cls.APIKEY_UPDATE,
                "scope": "apikey",
                "description": "Update API keys",
            },
            {
                "code": cls.APIKEY_DELETE,
                "scope": "apikey",
                "description": "Delete API keys",
            },
            # Platform Conversation Management
            {
                "code": cls.CONVERSATION_READ,
                "scope": "conversation",
                "description": "View conversations",
            },
            {
                "code": cls.CONVERSATION_DELETE,
                "scope": "conversation",
                "description": "Delete conversations",
            },
            # Platform Memory Management
            {
                "code": cls.MEMORY_READ,
                "scope": "memory",
                "description": "View own memories",
            },
            {
                "code": cls.MEMORY_CREATE,
                "scope": "memory",
                "description": "Create new memories",
            },
            {
                "code": cls.MEMORY_UPDATE,
                "scope": "memory",
                "description": "Update own memories",
            },
            {
                "code": cls.MEMORY_DELETE,
                "scope": "memory",
                "description": "Delete own memories",
            },
        ]

    @classmethod
    def get_all_codes(cls) -> list[str]:
        """Get all permission codes"""
        return [perm["code"] for perm in cls.get_all_definitions()]
