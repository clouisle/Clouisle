from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.api.v1.endpoints import skills
from app.models.skill import SkillCategory, SkillSourceType
from app.schemas.response import BusinessError
from app.schemas.skill import (
    SkillImportInstallOut,
    SkillImportInstallRequest,
    SkillImportPreviewGitRequest,
    SkillImportPreviewOut,
    SkillTestRequest,
    SkillUpdate,
)
from app.services.skill_executor import SkillExecutionResult


class Query:
    def __init__(self, *, first=None, exists=False):
        self.first_result = first
        self.exists_result = exists
        self.prefetched = None

    def prefetch_related(self, relation):
        self.prefetched = relation
        return self

    async def first(self):
        return self.first_result

    async def exists(self):
        return self.exists_result


def request(method="POST"):
    return Request({"type": "http", "method": method, "path": "/", "headers": []})


def user(*, superuser=False):
    return SimpleNamespace(id=uuid4(), is_superuser=superuser)


def skill(*, team_id=None, **overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid4(),
        "team_id": team_id,
        "name": "summarize",
        "display_name": "Summarize",
        "description": "Summarizes text",
        "icon": None,
        "category": SkillCategory.OTHER,
        "version": "1.0.0",
        "source_type": SkillSourceType.ZIP,
        "source_uri": None,
        "source_ref": None,
        "source_subdir": None,
        "package_path": "summarize",
        "package_hash": "hash",
        "package_storage_path": "skills/summarize.zip",
        "input_schema": {},
        "default_config": {},
        "is_enabled": True,
        "import_warnings": None,
        "created_by": None,
        "created_at": now,
        "updated_at": now,
        "skill_md": "# Summarize",
        "instructions": "Summarize the input",
        "frontmatter": None,
        "package_manifest": None,
        "execution_config": None,
        "config_schema": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def preview(*, source_type=SkillSourceType.ZIP, valid=(), invalid=()):
    return SkillImportPreviewOut(
        session_id=uuid4(),
        source_type=source_type,
        skills=list(valid),
        invalid=list(invalid),
    )


@pytest.mark.asyncio
async def test_list_skills_splits_system_and_team_and_forwards_filters(monkeypatch):
    team_id = uuid4()
    system_skill = skill()
    team_skill = skill(team_id=team_id)
    list_available = AsyncMock(return_value=[system_skill, team_skill])
    monkeypatch.setattr(skills.SkillService, "list_available_skills", list_available)

    response = await skills.list_skills(
        team_id=team_id,
        include_system=False,
        enabled=True,
        search="sum",
        category="other",
        current_user=user(),
    )

    assert [item.id for item in response["data"].system] == [system_skill.id]
    assert [item.id for item in response["data"].team] == [team_skill.id]
    assert list_available.await_args.kwargs == {
        "team_id": team_id,
        "user": list_available.await_args.kwargs["user"],
        "include_system": False,
        "enabled": True,
        "search": "sum",
        "category": "other",
    }


@pytest.mark.asyncio
async def test_import_previews_cover_zip_fallback_and_git_team_metadata(monkeypatch):
    zip_preview = preview(
        valid=[{"package_path": "a"}], invalid=[{"package_path": "bad"}]
    )
    git_team_id = uuid4()
    git_preview = preview(
        source_type=SkillSourceType.GIT, valid=[{"package_path": "g"}]
    )
    preview_zip = AsyncMock(return_value=zip_preview)
    preview_git = AsyncMock(return_value=git_preview)
    audit = AsyncMock()
    monkeypatch.setattr(skills.SkillImportService, "preview_zip", preview_zip)
    monkeypatch.setattr(skills.SkillImportService, "preview_git", preview_git)
    monkeypatch.setattr(skills.AuditLogService, "log", audit)
    uploaded = SimpleNamespace(filename=None, read=AsyncMock(return_value=b"zip"))
    current_user = user()

    zip_response = await skills.preview_zip_import(
        request=request(), team_id=None, file=uploaded, current_user=current_user
    )
    git_response = await skills.preview_git_import(
        request=request(),
        preview_in=SkillImportPreviewGitRequest(
            team_id=git_team_id, repo_url="https://example.test/repo.git", ref="main"
        ),
        current_user=current_user,
    )

    assert zip_response["data"] is zip_preview
    assert git_response["data"] is git_preview
    assert preview_zip.await_args.kwargs["filename"] == "skills.zip"
    assert preview_zip.await_args.kwargs["content"] == b"zip"
    assert preview_git.await_args.kwargs["ref"] == "main"
    assert audit.await_args_list[0].kwargs["metadata"] == {
        "team_id": None,
        "source_type": "zip",
        "skill_count": 1,
        "invalid_count": 1,
    }
    assert audit.await_args_list[1].kwargs["metadata"]["team_id"] == str(git_team_id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("errors", "expected_status"), [([], "success"), (["broken"], "failed")]
)
async def test_install_audits_success_and_partial_failure(
    monkeypatch, errors, expected_status
):
    result = SkillImportInstallOut(
        installed=[uuid4()], updated=[uuid4()], skipped=["old"], errors=errors
    )
    install = AsyncMock(return_value=result)
    audit = AsyncMock()
    monkeypatch.setattr(skills.SkillImportService, "install_from_session", install)
    monkeypatch.setattr(skills.AuditLogService, "log", audit)
    session_id = uuid4()

    response = await skills.install_skill_import(
        request=request(),
        session_id=session_id,
        install_in=SkillImportInstallRequest(items=[], is_enabled=False),
        current_user=user(),
    )

    assert response["data"] is result
    assert install.await_args.kwargs["is_enabled"] is False
    assert audit.await_args.kwargs["status"] == expected_status
    assert audit.await_args.kwargs["metadata"] == {
        "installed_count": 1,
        "updated_count": 1,
        "skipped_count": 1,
        "error_count": len(errors),
    }


@pytest.mark.asyncio
async def test_get_skill_not_found_and_access_matrix(monkeypatch):
    skill_id = uuid4()
    monkeypatch.setattr(skills.Skill, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc:
        await skills.get_skill(skill_id, None, user())
    assert exc.value.status_code == 404

    access = AsyncMock()
    monkeypatch.setattr(skills.SkillService, "check_team_access", access)
    system_skill = skill()
    monkeypatch.setattr(
        skills.Skill, "filter", lambda **_kwargs: Query(first=system_skill)
    )
    response = await skills.get_skill(skill_id, None, user())
    assert response["data"].frontmatter == {}
    access.assert_not_awaited()

    context_team_id = uuid4()
    await skills.get_skill(skill_id, context_team_id, user())
    access.assert_awaited_once_with(context_team_id, access.await_args.args[1])

    owned_skill = skill(team_id=uuid4())
    monkeypatch.setattr(
        skills.Skill, "filter", lambda **_kwargs: Query(first=owned_skill)
    )
    await skills.get_skill(skill_id, None, user())
    assert access.await_args.args[0] == owned_skill.team_id


@pytest.mark.asyncio
async def test_update_skill_not_found_and_audits_nullable_team(monkeypatch):
    monkeypatch.setattr(skills.Skill, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc:
        await skills.update_skill(
            request=request("PATCH"),
            skill_id=uuid4(),
            skill_in=SkillUpdate(display_name="New"),
            current_user=user(),
        )
    assert exc.value.status_code == 404

    existing = skill(display_name="Old")
    updated = skill(id=existing.id, display_name="New")
    monkeypatch.setattr(skills.Skill, "filter", lambda **_kwargs: Query(first=existing))
    monkeypatch.setattr(
        skills.SkillService, "update_skill", AsyncMock(return_value=updated)
    )
    audit = AsyncMock()
    monkeypatch.setattr(skills.AuditLogService, "log", audit)

    response = await skills.update_skill(
        request=request("PATCH"),
        skill_id=existing.id,
        skill_in=SkillUpdate(display_name="New"),
        current_user=user(),
    )

    assert response["data"].display_name == "New"
    assert audit.await_args.kwargs["changes"]["before"]["display_name"] == "Old"
    assert audit.await_args.kwargs["changes"]["after"]["display_name"] == "New"
    assert audit.await_args.kwargs["metadata"] == {"team_id": None}


@pytest.mark.asyncio
async def test_delete_skill_rejects_missing_system_user_and_agent_reference(
    monkeypatch,
):
    current_user = user()
    monkeypatch.setattr(skills.Skill, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc:
        await skills.delete_skill(
            request=request("DELETE"), skill_id=uuid4(), current_user=current_user
        )
    assert exc.value.status_code == 404

    system_skill = skill()
    monkeypatch.setattr(
        skills.Skill, "filter", lambda **_kwargs: Query(first=system_skill)
    )
    with pytest.raises(BusinessError) as exc:
        await skills.delete_skill(
            request=request("DELETE"),
            skill_id=system_skill.id,
            current_user=current_user,
        )
    assert exc.value.status_code == 403

    team_skill = skill(team_id=uuid4())
    monkeypatch.setattr(
        skills.Skill, "filter", lambda **_kwargs: Query(first=team_skill)
    )
    monkeypatch.setattr(skills.SkillService, "check_team_access", AsyncMock())
    monkeypatch.setattr(skills.Agent, "filter", lambda **_kwargs: Query(exists=True))
    with pytest.raises(BusinessError) as exc:
        await skills.delete_skill(
            request=request("DELETE"),
            skill_id=team_skill.id,
            current_user=current_user,
        )
    assert exc.value.msg_key == "skill_referenced_by_agent"


@pytest.mark.asyncio
@pytest.mark.parametrize("team_id", [None, uuid4()])
async def test_delete_skill_success_cleans_storage_model_and_audits(
    monkeypatch, team_id
):
    existing = skill(team_id=team_id, delete=AsyncMock())
    current_user = user(superuser=True)
    access = AsyncMock()
    storage_delete = AsyncMock()
    audit = AsyncMock()
    monkeypatch.setattr(skills.Skill, "filter", lambda **_kwargs: Query(first=existing))
    monkeypatch.setattr(skills.SkillService, "check_team_access", access)
    monkeypatch.setattr(skills.Agent, "filter", lambda **_kwargs: Query(exists=False))
    monkeypatch.setattr(
        skills.SkillImportService, "delete_private_storage", storage_delete
    )
    monkeypatch.setattr(skills.AuditLogService, "log", audit)

    response = await skills.delete_skill(
        request=request("DELETE"), skill_id=existing.id, current_user=current_user
    )

    assert response["data"] is None
    storage_delete.assert_awaited_once_with(existing.package_storage_path)
    existing.delete.assert_awaited_once()
    if team_id is None:
        access.assert_not_awaited()
    else:
        access.assert_awaited_once_with(team_id, current_user, require_admin=True)
    assert audit.await_args.kwargs["metadata"] == {
        "team_id": str(team_id) if team_id else None
    }


@pytest.mark.asyncio
async def test_skill_execution_rejections_and_cleanup_on_executor_error(monkeypatch):
    monkeypatch.setattr(skills.Skill, "filter", lambda **_kwargs: Query())
    with pytest.raises(BusinessError) as exc:
        await skills.test_skill(
            request=request(),
            skill_id=uuid4(),
            test_in=SkillTestRequest(),
            current_user=user(),
        )
    assert exc.value.status_code == 404

    system_skill = skill()
    monkeypatch.setattr(
        skills.Skill, "filter", lambda **_kwargs: Query(first=system_skill)
    )
    with pytest.raises(BusinessError) as exc:
        await skills.test_skill(
            request=request(),
            skill_id=system_skill.id,
            test_in=SkillTestRequest(),
            current_user=user(),
        )
    assert exc.value.status_code == 403

    from app.services.sandbox.gateway import sandbox_gateway

    team_skill = skill(team_id=uuid4())
    monkeypatch.setattr(
        skills.Skill, "filter", lambda **_kwargs: Query(first=team_skill)
    )
    monkeypatch.setattr(skills.SkillService, "check_team_access", AsyncMock())
    monkeypatch.setattr(
        sandbox_gateway, "create_session", AsyncMock(return_value="session-1")
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(sandbox_gateway, "cleanup_session", cleanup)
    monkeypatch.setattr(
        skills.SkillExecutor,
        "execute",
        AsyncMock(side_effect=RuntimeError("executor down")),
    )

    with pytest.raises(RuntimeError, match="executor down"):
        await skills.test_skill(
            request=request(),
            skill_id=team_skill.id,
            test_in=SkillTestRequest(arguments={"text": "hello"}),
            current_user=user(),
        )
    cleanup.assert_awaited_once_with("session-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("execution_success", "expected_status"), [(True, "success"), (False, "failed")]
)
async def test_skill_execution_serializes_result_and_audits_status(
    monkeypatch, execution_success, expected_status
):
    from app.services.sandbox.gateway import sandbox_gateway
    from app.services.sandbox.models import SandboxTaskStatus

    existing = skill()
    result = SkillExecutionResult(
        success=execution_success,
        result={"answer": 42},
        error=None if execution_success else "failed",
        stdout="out",
        stderr="err",
        artifacts=[{"path": "/workspace/result.txt", "size": 4}],
        duration_ms=12,
        status=SandboxTaskStatus.COMPLETED,
    )
    monkeypatch.setattr(skills.Skill, "filter", lambda **_kwargs: Query(first=existing))
    monkeypatch.setattr(
        sandbox_gateway, "create_session", AsyncMock(return_value="session-2")
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(sandbox_gateway, "cleanup_session", cleanup)
    execute = AsyncMock(return_value=result)
    monkeypatch.setattr(skills.SkillExecutor, "execute", execute)
    audit = AsyncMock()
    monkeypatch.setattr(skills.AuditLogService, "log", audit)
    current_user = user(superuser=True)

    response = await skills.test_skill(
        request=request(),
        skill_id=existing.id,
        test_in=SkillTestRequest(arguments={"z": 1, "a": 2}, config={"mode": "fast"}),
        current_user=current_user,
    )

    assert response["data"].success is execution_success
    assert response["data"].artifacts[0].path == "/workspace/result.txt"
    assert execute.await_args.kwargs["tenant_id"] is None
    cleanup.assert_awaited_once_with("session-2")
    assert audit.await_args.kwargs["status"] == expected_status
    assert audit.await_args.kwargs["metadata"] == {
        "team_id": None,
        "argument_keys": ["a", "z"],
        "duration_ms": 12,
        "status": SandboxTaskStatus.COMPLETED.value,
    }
