"""Move search credentials to site ownership without promoting private accounts."""

import json
import logging

from tortoise.transactions import in_transaction

from app.core.config import settings
from app.integrations.credentials import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)
SECRET_PREFIX = "enc:v1:"
SEARCH_KEYS = {"TAVILY_API_KEY", "BOCHA_API_KEY", "SEARXNG_AUTH_TOKEN"}


async def migrate_site_web_search() -> None:
    """Serialize startup cutover and retain retired credentials encrypted."""
    async with in_transaction() as conn:
        await conn.execute_query("SELECT pg_advisory_xact_lock(736421091)")
        rows = await conn.execute_query_dict(
            "SELECT id, team_id, credentials FROM tool_configs "
            "WHERE tool_name = 'web_search' FOR UPDATE"
        )
        global_rows = [row for row in rows if row["team_id"] is None]
        if len(global_rows) > 1:
            raise RuntimeError(
                "Multiple global web search configurations; consolidate them before upgrading"
            )
        global_row = global_rows[0] if global_rows else None
        credentials = _json_value(global_row["credentials"]) if global_row else {}
        if credentials.get("_site_config_version") == "1":
            return

        previous_archive = credentials.get("_legacy_credentials", "")
        archived: list[dict] = (
            json.loads(decrypt_secret(previous_archive.removeprefix(SECRET_PREFIX)))
            if previous_archive
            else []
        )
        for row in rows:
            if row["team_id"] is not None:
                archived.append(
                    {
                        "source": "team",
                        "id": str(row["id"]),
                        "team_id": str(row["team_id"]),
                        "credentials": _json_value(row["credentials"]),
                    }
                )

        _, agents = await conn.execute_query(
            "SELECT id, tools_config, tools_credentials FROM agents FOR UPDATE"
        )
        for agent in agents:
            tools = _json_value(agent["tools_config"])
            old_credentials = _json_value(agent["tools_credentials"])
            next_credentials = {
                key: value
                for key, value in old_credentials.items()
                if key not in SEARCH_KEYS
            }
            next_tools = []
            for tool in tools:
                if tool.get("type") == "builtin" and tool.get("name") == "web_search":
                    config = tool.get("config") or {}
                    engine = config.get("engine", "auto")
                    if engine not in {"auto", "tavily", "bocha"}:
                        engine = "auto"
                    next_tool = {**tool, "config": {"engine": engine}}
                    if config != next_tool["config"]:
                        archived.append(
                            {
                                "source": "agent_tool",
                                "id": str(agent["id"]),
                                "config": config,
                            }
                        )
                    next_tools.append(next_tool)
                else:
                    next_tools.append(tool)
            removed = {
                key: value
                for key, value in old_credentials.items()
                if key in SEARCH_KEYS
            }
            if removed:
                archived.append(
                    {
                        "source": "agent_credentials",
                        "id": str(agent["id"]),
                        "credentials": removed,
                    }
                )
            if next_tools != tools or next_credentials != old_credentials:
                await conn.execute_query(
                    "UPDATE agents SET tools_config=$1::jsonb, tools_credentials=$2::jsonb WHERE id=$3",
                    [json.dumps(next_tools), json.dumps(next_credentials), agent["id"]],
                )

        if not credentials.get("TAVILY_API_KEY") and settings.TAVILY_API_KEY:
            credentials["TAVILY_API_KEY"] = settings.TAVILY_API_KEY
        for key in SEARCH_KEYS:
            value = credentials.get(key)
            if value and not value.startswith(SECRET_PREFIX):
                credentials[key] = SECRET_PREFIX + encrypt_secret(value)
        credentials.setdefault(
            "tavily_enabled", "true" if credentials.get("TAVILY_API_KEY") else "false"
        )
        credentials.setdefault(
            "bocha_enabled", "true" if credentials.get("BOCHA_API_KEY") else "false"
        )
        credentials.setdefault(
            "default_engine",
            "bocha"
            if not credentials.get("TAVILY_API_KEY")
            and credentials.get("BOCHA_API_KEY")
            else "tavily",
        )
        if archived:
            credentials["_legacy_credentials"] = SECRET_PREFIX + encrypt_secret(
                json.dumps(archived)
            )
        credentials["_site_config_version"] = "1"
        if global_row:
            await conn.execute_query(
                "UPDATE tool_configs SET credentials=$1::jsonb WHERE id=$2",
                [json.dumps(credentials), global_row["id"]],
            )
        else:
            from uuid import uuid4

            await conn.execute_query(
                "INSERT INTO tool_configs (id, tool_name, team_id, credentials, created_at, updated_at) "
                "VALUES ($1, 'web_search', NULL, $2::jsonb, NOW(), NOW())",
                [uuid4(), json.dumps(credentials)],
            )
        await conn.execute_query(
            "DELETE FROM tool_configs WHERE tool_name='web_search' AND team_id IS NOT NULL"
        )
        if archived:
            logger.warning(
                "Legacy search credentials archived; configure and confirm site search providers before use"
            )


def _json_value(value):
    return json.loads(value) if isinstance(value, str) else value
