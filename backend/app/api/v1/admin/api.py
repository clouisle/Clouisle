from fastapi import APIRouter

from app.api.v1.admin.endpoints import (
    dashboard,
    audit_logs,
    conversations,
    users,
    roles,
    permissions,
    site_settings,
    models,
    sso,
    notifications,
    teams,
    memories,
)

admin_router = APIRouter()

admin_router.include_router(dashboard.router, prefix="/dashboard", tags=["admin-dashboard"])
admin_router.include_router(audit_logs.router, prefix="/audit-logs", tags=["admin-audit-logs"])
admin_router.include_router(conversations.router, prefix="/conversations", tags=["admin-conversations"])
admin_router.include_router(users.router, prefix="/users", tags=["admin-users"])
admin_router.include_router(roles.router, prefix="/roles", tags=["admin-roles"])
admin_router.include_router(permissions.router, prefix="/permissions", tags=["admin-permissions"])
admin_router.include_router(site_settings.router, prefix="/site-settings", tags=["admin-site-settings"])
admin_router.include_router(models.router, prefix="/models", tags=["admin-models"])
admin_router.include_router(sso.router, prefix="/sso", tags=["admin-sso"])
admin_router.include_router(notifications.router, prefix="/notifications", tags=["admin-notifications"])
admin_router.include_router(teams.router, prefix="/teams", tags=["admin-teams"])
admin_router.include_router(memories.router, prefix="/memories", tags=["admin-memories"])
