"""Startup cutover of legacy web search credentials into site configuration."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core import web_search_migration as subject
from app.integrations.credentials import decrypt_secret, encrypt_secret


class FakeConn:
    """Records the migration's SQL while serving deterministic rows."""

    def __init__(self, config_rows, agents=()):
        self.config_rows = config_rows
        self.agents = list(agents)
        self.queries = []

    async def execute_query_dict(self, sql):
        self.queries.append((sql, None))
        return self.config_rows

    async def execute_query(self, sql, params=None):
        self.queries.append((sql, params))
        if sql.startswith("SELECT id, tools_config"):
            return None, self.agents
        if sql.startswith("UPDATE tool_configs"):
            for row in self.config_rows:
                if row["id"] == params[1]:
                    row["credentials"] = params[0]
        return None

    def statements(self):
        return [sql for sql, _ in self.queries]

    def params_for(self, prefix):
        return [params for sql, params in self.queries if sql.startswith(prefix)]


class FakeTransaction:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


def _install(monkeypatch, conn, tavily_env=""):
    monkeypatch.setattr(subject, "in_transaction", lambda: FakeTransaction(conn))
    monkeypatch.setattr(subject, "settings", SimpleNamespace(TAVILY_API_KEY=tavily_env))
    return conn


def _archive(credentials):
    return json.loads(
        decrypt_secret(credentials["_legacy_credentials"][len(subject.SECRET_PREFIX) :])
    )


@pytest.mark.asyncio
async def test_cutover_archives_legacy_rows_and_preserves_deepseek_choices(monkeypatch):
    agent_id = uuid4()
    conn = _install(
        monkeypatch,
        FakeConn(
            config_rows=[
                {"id": "row-1", "team_id": "team-1", "credentials": {"token": "team"}}
            ],
            agents=[
                {
                    "id": agent_id,
                    "tools_config": json.dumps(
                        [
                            {
                                "type": "builtin",
                                "name": "web_search",
                                "config": {"engine": "deepseek", "api_key": "sk-old"},
                            },
                            {"type": "custom", "name": "kept"},
                        ]
                    ),
                    "tools_credentials": json.dumps(
                        {"DEEPSEEK_API_KEY": "sk-agent", "OTHER_KEY": "kept"}
                    ),
                }
            ],
        ),
    )

    await subject.migrate_site_web_search()

    credentials = json.loads(conn.params_for("INSERT INTO tool_configs")[0][1])
    assert credentials["tavily_enabled"] == "false"
    assert credentials["bocha_enabled"] == "false"
    assert credentials["default_engine"] == "tavily"
    assert credentials["_site_config_version"] == "1"
    archived = _archive(credentials)
    assert {"source": "team", "id": "row-1", "team_id": "team-1"} == {
        key: archived[0][key] for key in ("source", "id", "team_id")
    }
    assert {"source": "agent_tool", "id": str(agent_id)} == {
        key: archived[1][key] for key in ("source", "id")
    }
    assert archived[1]["config"] == {"engine": "deepseek", "api_key": "sk-old"}
    assert {
        "source": "agent_credentials",
        "id": str(agent_id),
        "credentials": {"DEEPSEEK_API_KEY": "sk-agent"},
    } == archived[2]

    update = conn.params_for("UPDATE agents")[0]
    assert json.loads(update[0]) == [
        {"type": "builtin", "name": "web_search", "config": {"engine": "deepseek"}},
        {"type": "custom", "name": "kept"},
    ]
    assert json.loads(update[1]) == {"OTHER_KEY": "kept"}
    assert (
        "DELETE FROM tool_configs WHERE tool_name='web_search' AND team_id IS NOT NULL"
        in conn.statements()
    )


@pytest.mark.asyncio
async def test_cutover_encrypts_global_plaintext_and_keeps_existing_version(
    monkeypatch,
):
    existing_archive = subject.SECRET_PREFIX + encrypt_secret(
        json.dumps([{"source": "agent_tool", "id": "old"}])
    )
    conn = _install(
        monkeypatch,
        FakeConn(
            config_rows=[
                {
                    "id": "row-1",
                    "team_id": None,
                    "credentials": json.dumps(
                        {
                            "TAVILY_API_KEY": "tvly-plain",
                            "SEARXNG_AUTH_TOKEN": subject.SECRET_PREFIX
                            + encrypt_secret("kept-token"),
                            "_legacy_credentials": existing_archive,
                        }
                    ),
                }
            ],
        ),
        tavily_env="tvly-env",
    )

    await subject.migrate_site_web_search()

    credentials = json.loads(conn.params_for("UPDATE tool_configs")[0][0])
    assert credentials["TAVILY_API_KEY"].startswith(subject.SECRET_PREFIX)
    assert (
        decrypt_secret(credentials["TAVILY_API_KEY"][len(subject.SECRET_PREFIX) :])
        == "tvly-plain"
    )
    assert credentials["SEARXNG_AUTH_TOKEN"].startswith(subject.SECRET_PREFIX)
    assert credentials["tavily_enabled"] == "true"
    assert credentials["default_engine"] == "tavily"
    archived = _archive(credentials)
    assert archived[0] == {"source": "agent_tool", "id": "old"}

    conn.queries.clear()
    await subject.migrate_site_web_search()
    assert len(conn.queries) == 2


@pytest.mark.asyncio
async def test_cutover_prefers_bocha_default_and_rejects_duplicate_global_rows(
    monkeypatch,
):
    conn = _install(
        monkeypatch,
        FakeConn(
            config_rows=[
                {
                    "id": "row-1",
                    "team_id": None,
                    "credentials": {"BOCHA_API_KEY": "plain-bocha"},
                }
            ]
        ),
    )

    await subject.migrate_site_web_search()

    credentials = json.loads(conn.params_for("UPDATE tool_configs")[0][0])
    assert credentials["bocha_enabled"] == "true"
    assert credentials["default_engine"] == "bocha"

    duplicate = _install(
        monkeypatch,
        FakeConn(
            config_rows=[
                {"id": "a", "team_id": None, "credentials": {}},
                {"id": "b", "team_id": None, "credentials": {}},
            ]
        ),
    )
    with pytest.raises(RuntimeError, match="Multiple global web search"):
        await subject.migrate_site_web_search()
    assert duplicate.params_for("INSERT INTO tool_configs") == []
