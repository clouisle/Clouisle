from uuid import uuid4

import pytest
from tortoise import Tortoise

from app.integrations.feishu import FeishuDepartment, FeishuDirectoryUser
from app.models.feishu_department import FeishuDepartment as FeishuDepartmentMapping
from app.models.feishu_user import FeishuUser
from app.models.user import Team, TeamMember, User
from app.services.feishu_directory import sync_department_teams


@pytest.mark.asyncio
async def test_sync_department_teams_end_to_end_is_idempotent_and_supports_multi_department_membership():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
    try:
        await Tortoise.generate_schemas()
        user = await User.create(
            username=f"feishu_smoke_{uuid4().hex[:8]}",
            email=f"{uuid4().hex}@accounts.clouisle.example",
            hashed_password="",
            auth_source="feishu",
            external_id="ou_smoke",
        )
        await FeishuUser.create(user=user, feishu_user_id="ou_smoke")
        departments = [
            FeishuDepartment("dept-a", "Research", None),
            FeishuDepartment("dept-b", "Research", None),
        ]
        members = [
            FeishuDirectoryUser(
                "ou_smoke",
                "open_smoke",
                None,
                "Smoke User",
                None,
                None,
                frozenset({"dept-a", "dept-b"}),
            )
        ]

        assert await sync_department_teams(departments, members) == 2
        assert await sync_department_teams(departments, members) == 0
        assert await FeishuDepartmentMapping.all().count() == 2
        assert (
            await Team.filter(
                feishu_department_mapping__department_id__in=["dept-a", "dept-b"]
            ).count()
            == 2
        )
        assert await TeamMember.filter(user=user).count() == 2
    finally:
        await Tortoise.close_connections()
