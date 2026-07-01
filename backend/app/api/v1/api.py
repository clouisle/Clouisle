from fastapi import APIRouter

from app.api.v1.endpoints import (
    login,
    users,
    teams,
    team_models,
    site_settings,
    upload,
    models,
    knowledge_bases,
    agents,
    conversations,
    agent_stats,
    chat,
    tools,
    packages,
    skills,
    api_keys,
    prompt_generator,
    workflows,
    notifications,
    sso,
    memories,
    totp,
    embed,
)
from app.api.v1 import workflow_metrics
from app.api.v1 import workflow_versions
from app.api.v1.admin.api import admin_router

api_router = APIRouter()
api_router.include_router(login.router, tags=["login"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(teams.router, prefix="/teams", tags=["teams"])
api_router.include_router(team_models.router, prefix="/teams", tags=["team-models"])
api_router.include_router(
    site_settings.router, prefix="/site-settings", tags=["site-settings"]
)
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(
    knowledge_bases.router, prefix="/knowledge-bases", tags=["knowledge-bases"]
)
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(
    conversations.router, prefix="/conversations", tags=["conversations"]
)
api_router.include_router(agent_stats.router, prefix="/agents", tags=["agent-stats"])
api_router.include_router(chat.router, prefix="/agents", tags=["chat"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(packages.router, prefix="/packages", tags=["packages"])
api_router.include_router(skills.router, prefix="/skills", tags=["skills"])
api_router.include_router(api_keys.router, prefix="/api-keys", tags=["api-keys"])
api_router.include_router(
    prompt_generator.router, prefix="/prompts", tags=["prompt-generator"]
)
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(workflow_metrics.router, tags=["workflow-metrics"])
api_router.include_router(workflow_versions.router, tags=["workflow-versions"])
api_router.include_router(
    workflow_versions.template_router, tags=["workflow-templates"]
)
api_router.include_router(
    notifications.router, prefix="/notifications", tags=["notifications"]
)
api_router.include_router(sso.router, prefix="/sso", tags=["sso"])
api_router.include_router(memories.router, prefix="/memories", tags=["memories"])
api_router.include_router(totp.router, prefix="/totp", tags=["totp"])
api_router.include_router(embed.router, prefix="/embed", tags=["embed"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
