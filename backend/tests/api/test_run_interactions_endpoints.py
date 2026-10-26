"""Endpoint-level checks for the durable run-interaction API.

The route functions are exercised against a real SQLite schema instead of
mocked ORM calls, so audience filtering, DTO projection and response
idempotency are verified end to end without an HTTP server.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from pydantic import ValidationError
from tortoise.context import TortoiseContext

from app.api.v1.endpoints import run_interactions
from app.models.tool_interaction import (
    InteractionKind,
    InteractionStatus,
)
from app.models.user import Team, TeamMember, User
from app.schemas.tool_interaction import RunInteractionResponseIn
from app.services import tool_interactions


@pytest.fixture
def run_orm(tmp_path):
    runner = asyncio.Runner()
    database_url = f"sqlite://{tmp_path / 'interaction-api.sqlite3'}"

    def run(scenario):
        async def _wrapped():
            async with TortoiseContext() as context:
                await context.init(
                    db_url=database_url, modules={"models": ["app.models"]}
                )
                await context.generate_schemas()
                return await scenario()

        return runner.run(_wrapped())

    try:
        yield run
    finally:
        runner.close()


async def _user(label: str) -> User:
    return await User.create(
        id=uuid4(),
        username=f"{label}_{uuid4().hex[:8]}",
        email=f"{label}_{uuid4().hex[:8]}@interaction-api.test",
        hashed_password="x",
    )


async def _team(owner: User) -> Team:
    team = await Team.create(id=uuid4(), name=f"team_{uuid4().hex[:8]}")
    await TeamMember.create(id=uuid4(), team_id=team.id, user_id=owner.id, role="owner")
    return team


def test_list_get_and_respond_round_trip(run_orm):
    async def scenario():
        owner = await _user("owner")
        team = await _team(owner)
        row = await tool_interactions.create_interaction(
            kind=InteractionKind.ELICITATION,
            actor=owner,
            team_id=team.id,
            payload={
                "mode": "form",
                "message": "Name?",
                "requested_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
            audience={"user_ids": [str(owner.id)]},
            ttl_seconds=60,
            run_kind="agent",
            run_id=uuid4(),
            execution_id=uuid4(),
            tool_name="search",
        )

        listed = await run_interactions.list_run_interactions(
            page=1,
            page_size=20,
            kind=InteractionKind.ELICITATION,
            status=InteractionStatus.PENDING,
            run_id=None,
            current_user=owner,
        )
        assert listed["code"] == 0
        assert listed["data"].total == 1
        item = listed["data"].items[0]
        assert item.id == row.id
        assert item.kind == InteractionKind.ELICITATION
        assert item.payload["requested_schema"]["required"] == ["name"]
        assert item.response is None

        fetched = await run_interactions.get_run_interaction(row.id, current_user=owner)
        assert fetched["data"].id == row.id

        answered = await run_interactions.respond_to_run_interaction(
            row.id,
            RunInteractionResponseIn(
                action="accept", content={"name": "Ada"}, idempotency_key="roundtrip1"
            ),
            current_user=owner,
        )
        assert answered["data"].status == InteractionStatus.RESPONDED
        assert answered["data"].outcome.value == "accept"
        assert answered["data"].response == {"name": "Ada"}

        replay = await run_interactions.respond_to_run_interaction(
            row.id,
            RunInteractionResponseIn(
                action="accept", content={"name": "Ada"}, idempotency_key="roundtrip1"
            ),
            current_user=owner,
        )
        assert replay["data"].id == row.id

        # Pending inbox is empty after the decision.
        pending = await run_interactions.list_run_interactions(
            page=1,
            page_size=20,
            kind=None,
            status=InteractionStatus.PENDING,
            run_id=None,
            current_user=owner,
        )
        assert pending["data"].total == 0

    run_orm(scenario)


def test_response_schema_forbids_extra_fields_and_requires_key():
    with pytest.raises(ValidationError):
        RunInteractionResponseIn(
            action="accept",
            content={"name": "Ada"},
            idempotency_key="abcdefgh",
            actor_id=str(uuid4()),
        )
    with pytest.raises(ValidationError):
        RunInteractionResponseIn(action="maybe", idempotency_key="abcdefgh")
    with pytest.raises(ValidationError):
        RunInteractionResponseIn(action="decline", idempotency_key="short")
