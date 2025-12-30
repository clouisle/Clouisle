from fastapi import APIRouter

from app.api.v1.endpoints import (
    login,
    users,
    permissions,
    roles,
    teams,
    team_models,
    site_settings,
    upload,
    models,
    knowledge_bases,
    agents,
    agent_stats,
    chat,
    tools,
    conversations,
    api_keys,
    prompt_generator,
    workflows,
)

api_router = APIRouter()
api_router.include_router(login.router, tags=["login"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(
    permissions.router, prefix="/permissions", tags=["permissions"]
)
api_router.include_router(roles.router, prefix="/roles", tags=["roles"])
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
api_router.include_router(agent_stats.router, prefix="/agents", tags=["agent-stats"])
api_router.include_router(chat.router, prefix="/agents", tags=["chat"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(
    conversations.router, prefix="/conversations", tags=["conversations"]
)
api_router.include_router(api_keys.router, prefix="/api-keys", tags=["api-keys"])
api_router.include_router(
    prompt_generator.router, prefix="/prompts", tags=["prompt-generator"]
)
api_router.include_router(
    workflows.router, prefix="/workflows", tags=["workflows"]
)
