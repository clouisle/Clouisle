"""Create or update local accounts from an administrator-selected Feishu scope."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from uuid import UUID, uuid5

from fastapi import Request
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.integrations.feishu import FeishuDirectoryUser
from app.models.feishu_department import FeishuDepartment as FeishuDepartmentMapping
from app.models.feishu_user import FeishuUser
from app.models.site_setting import SiteSetting
from app.models.user import Team, TeamMember, User
from app.services.audit_log import AuditLogService
from app.services.team_role_sync import assign_default_role, assign_default_team

logger = logging.getLogger(__name__)
FEISHU_TEAM_NAMESPACE = UUID("7292dc54-7f50-4f4b-b602-9622371f86a4")


@dataclass(frozen=True)
class DirectorySyncResult:
    created: int
    updated: int
    skipped: int


def _department_team_name(name: str, department_id: str) -> str:
    normalized = re.sub(r"\s+", " ", name.strip()) or "Department"
    return normalized[:100]


async def _get_or_create_department_team(department, *, connection):
    mapping = (
        await FeishuDepartmentMapping.filter(department_id=department.department_id)
        .using_db(connection)
        .first()
    )
    team_name = _department_team_name(department.name, department.department_id)
    if mapping:
        team = (
            await Team.filter(id=mapping.team_id, is_deleted=False)
            .using_db(connection)
            .first()
        )
        if team:
            collision = (
                await Team.filter(name=team_name)
                .exclude(id=team.id)
                .using_db(connection)
                .first()
            )
            if collision:
                team_name = f"{team_name} ({department.department_id})"[:100]
                collision = (
                    await Team.filter(name=team_name)
                    .exclude(id=team.id)
                    .using_db(connection)
                    .first()
                )
                if collision:
                    raise ValueError(
                        f"Team name collision while syncing Feishu department {department.department_id}"
                    )
            team.name = team_name
            await team.save(using_db=connection, update_fields=["name"])
            return team, False
        await mapping.delete(using_db=connection)

    team_id = uuid5(FEISHU_TEAM_NAMESPACE, department.department_id)
    collision = await Team.filter(name=team_name).using_db(connection).first()
    if collision:
        team_name = f"{team_name} ({department.department_id})"[:100]
        if await Team.filter(name=team_name).using_db(connection).first():
            raise ValueError(
                f"Team name collision while syncing Feishu department {department.department_id}"
            )
    team = await Team.create(
        id=team_id,
        name=team_name,
        description=f"Managed by Feishu department {department.department_id}",
        using_db=connection,
    )
    await FeishuDepartmentMapping.create(
        department_id=department.department_id, team_id=team.id, using_db=connection
    )
    return team, True


async def sync_department_teams(departments, members: list[FeishuDirectoryUser]) -> int:
    """Create/update managed department teams and add linked Feishu members."""
    if not departments:
        return 0

    selected = {department.department_id: department for department in departments}
    teams_created = 0
    async with in_transaction() as connection:
        for department in selected.values():
            team, created = await _get_or_create_department_team(
                department, connection=connection
            )
            teams_created += int(created)
            for member in members:
                if department.department_id not in member.department_ids:
                    continue
                binding = (
                    await FeishuUser.filter(feishu_user_id=member.user_id)
                    .using_db(connection)
                    .first()
                )
                if not binding:
                    continue
                user = (
                    await User.filter(id=binding.user_id).using_db(connection).first()
                )
                if user:
                    await TeamMember.get_or_create(
                        team=team,
                        user=user,
                        defaults={"role": "member"},
                        using_db=connection,
                    )

    return teams_created


PLACEHOLDER_EMAIL_DOMAIN = "@accounts.clouisle.example"
# Older releases used an RFC 2606 `.invalid` domain, which pydantic's EmailStr rejects.
# Keep accepting it so stored placeholders can still be replaced by a real Feishu email.
LEGACY_PLACEHOLDER_EMAIL_DOMAIN = "@accounts.clouisle.invalid"
PLACEHOLDER_EMAIL_DOMAINS = (PLACEHOLDER_EMAIL_DOMAIN, LEGACY_PLACEHOLDER_EMAIL_DOMAIN)


def is_placeholder_email(email: str) -> bool:
    return email.endswith(PLACEHOLDER_EMAIL_DOMAINS)


def _placeholder_email(feishu_user_id: str) -> str:
    digest = hashlib.sha256(feishu_user_id.encode()).hexdigest()[:32]
    return f"feishu-{digest}{PLACEHOLDER_EMAIL_DOMAIN}"


def _username(name: str, feishu_user_id: str, *, suffix: str | None = None) -> str:
    normalized = re.sub(r"[^\w.-]+", "_", name.strip(), flags=re.UNICODE).strip("_.-")
    prefix = normalized or "feishu_user"
    if suffix:
        prefix = prefix[: 50 - len(suffix) - 1]
        return f"{prefix}_{suffix}"
    return prefix[:50]


async def sync_directory_users(
    members: list[FeishuDirectoryUser], *, actor: User, request: Request
) -> DirectorySyncResult:
    created = updated = skipped = 0
    audit_entries: list[tuple[User, str]] = []

    for member in members:
        feishu_user_id = member.user_id.strip()
        if not feishu_user_id:
            skipped += 1
            continue
        email = member.email or _placeholder_email(feishu_user_id)
        try:
            async with in_transaction() as connection:
                binding = (
                    await FeishuUser.filter(feishu_user_id=feishu_user_id)
                    .using_db(connection)
                    .first()
                )
                user = (
                    await User.filter(id=binding.user_id).using_db(connection).first()
                    if binding
                    else None
                )
                if binding and user is None:
                    skipped += 1
                    continue
                if user is None:
                    user = (
                        await User.filter(
                            auth_source="feishu", external_id=feishu_user_id
                        )
                        .using_db(connection)
                        .first()
                    )
                    if user:
                        await FeishuUser.create(
                            user=user,
                            feishu_user_id=feishu_user_id,
                            using_db=connection,
                        )

                if user:
                    email_owner = (
                        await User.filter(email=email)
                        .exclude(id=user.id)
                        .using_db(connection)
                        .exists()
                    )
                    if email_owner:
                        skipped += 1
                        continue
                    if member.email or is_placeholder_email(user.email):
                        user.email = email
                    if member.avatar_url:
                        user.avatar_url = member.avatar_url
                    await user.save(
                        using_db=connection, update_fields=["email", "avatar_url"]
                    )
                    updated += 1
                    continue

                if await User.filter(email=email).using_db(connection).exists():
                    skipped += 1
                    continue
                username = _username(member.name, feishu_user_id)
                if await User.filter(username=username).using_db(connection).exists():
                    suffix = hashlib.sha256(feishu_user_id.encode()).hexdigest()[:10]
                    username = _username(member.name, feishu_user_id, suffix=suffix)
                    if (
                        await User.filter(username=username)
                        .using_db(connection)
                        .exists()
                    ):
                        skipped += 1
                        continue
                locale = await SiteSetting.get_value("default_language", "en")
                user = await User.create(
                    username=username,
                    email=email,
                    hashed_password="",
                    auth_source="feishu",
                    external_id=feishu_user_id,
                    avatar_url=member.avatar_url,
                    is_active=True,
                    approval_status="approved",
                    email_verified=False,
                    locale=locale,
                    using_db=connection,
                )
                await FeishuUser.create(
                    user=user, feishu_user_id=feishu_user_id, using_db=connection
                )
                await assign_default_role(user)
                await assign_default_team(user)
                audit_entries.append((user, feishu_user_id))
                created += 1
        except IntegrityError:
            skipped += 1

    for user, feishu_user_id in audit_entries:
        await AuditLogService.log(
            user=actor,
            action="create_feishu_user",
            resource_type="user",
            resource_id=UUID(str(user.id)),
            resource_name=user.username,
            operation="create",
            status="success",
            request=request,
            changes={
                "after": {
                    "username": user.username,
                    "email": user.email,
                    "auth_source": "feishu",
                    "external_id": feishu_user_id,
                }
            },
        )

    return DirectorySyncResult(created=created, updated=updated, skipped=skipped)
