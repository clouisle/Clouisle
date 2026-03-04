"""
Admin notifications endpoints - re-exports the admin_router from the main notifications module.
"""

from app.api.v1.endpoints.notifications import admin_router as router

__all__ = ["router"]
