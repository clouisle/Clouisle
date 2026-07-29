import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from zipfile import ZipInfo

import pytest

from app.models.skill import SkillSourceType
from app.schemas.response import BusinessError, ResponseCode
from app.services import skill_import
from app.services.skill_import import SkillImportService


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/repo.git",
        "https://user:secret@example.com/repo.git",
        "https://localhost/repo.git",
        "https://127.0.0.1/repo.git",
        "https://10.0.0.1/repo.git",
    ],
)
def test_validate_git_url_rejects_unsafe_sources(url):
    with pytest.raises(BusinessError) as error:
        SkillImportService._validate_git_url(url)
    assert error.value.code == ResponseCode.BAD_REQUEST


def test_validate_git_url_accepts_public_host_and_redacts_credentials():
    SkillImportService._validate_git_url("https://example.com/repo.git")
    assert (
        SkillImportService._redact_url("https://user:secret@example.com:8443/repo.git")
        == "https://example.com:8443/repo.git"
    )


@pytest.mark.parametrize(
    ("filename", "size", "mode", "message"),
    [
        ("../escape", 1, 0, "skill_zip_path_invalid"),
        (
            "large.txt",
            skill_import._MAX_ZIP_SINGLE_FILE_BYTES + 1,
            0,
            "skill_zip_file_too_large",
        ),
        ("link", 1, stat.S_IFLNK, "skill_zip_symlink_not_allowed"),
        ("nested.zip", 1, 0, "skill_zip_nested_archive_not_allowed"),
    ],
)
def test_validate_zip_member_rejects_unsafe_members(filename, size, mode, message):
    info = ZipInfo(filename)
    info.file_size = size
    info.external_attr = mode << 16

    with pytest.raises(BusinessError) as error:
        SkillImportService._validate_zip_member(info)
    assert error.value.msg_key == message


@pytest.mark.anyio
async def test_resolve_import_team_covers_admin_lookup_and_system_denial():
    team_id = uuid4()
    with (
        patch(
            "app.services.skill_import.Team.filter",
            return_value=SimpleNamespace(first=AsyncMock(return_value=None)),
        ),
        pytest.raises(BusinessError) as error,
    ):
        await SkillImportService._resolve_import_team(
            team_id=team_id, user=SimpleNamespace(), admin_mode=True
        )
    assert error.value.code == ResponseCode.TEAM_NOT_FOUND

    with pytest.raises(BusinessError) as error:
        await SkillImportService._resolve_import_team(
            team_id=None,
            user=SimpleNamespace(is_superuser=False),
            admin_mode=False,
        )
    assert error.value.code == ResponseCode.PERMISSION_DENIED


@pytest.mark.anyio
async def test_clone_git_repo_covers_failure_and_timeout(tmp_path: Path):
    failed = SimpleNamespace(
        communicate=AsyncMock(return_value=(b"", b"clone failed")), returncode=1
    )
    with (
        patch(
            "app.services.skill_import.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=failed),
        ),
        pytest.raises(BusinessError) as error,
    ):
        await SkillImportService._clone_git_repo(
            "https://example.com/repo.git", "main", tmp_path / "repo"
        )
    assert error.value.msg_key == "skill_git_clone_failed"
    assert error.value.data == {"stderr": "clone failed"}

    timed_out = SimpleNamespace(
        communicate=AsyncMock(return_value=(b"", b"")), kill=lambda: None
    )
    with (
        patch(
            "app.services.skill_import.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=timed_out),
        ),
        patch("app.services.skill_import._GIT_TIMEOUT_SECONDS", 0),
        pytest.raises(BusinessError) as error,
    ):
        await SkillImportService._clone_git_repo(
            "https://example.com/repo.git", None, tmp_path / "repo"
        )
    assert error.value.msg_key == "skill_git_clone_timeout"


@pytest.mark.anyio
async def test_resolve_git_ref_and_session_source_branches(tmp_path: Path):
    process = SimpleNamespace(
        communicate=AsyncMock(return_value=(b"abc123\n", b"")), returncode=0
    )
    with patch(
        "app.services.skill_import.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ):
        assert await SkillImportService._resolve_git_ref(tmp_path) == "abc123"
    process.returncode = 1
    with patch(
        "app.services.skill_import.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ):
        assert await SkillImportService._resolve_git_ref(tmp_path) is None

    (tmp_path / "repo").mkdir()
    session = SimpleNamespace(
        temp_storage_path=str(tmp_path), source_type=SkillSourceType.GIT
    )
    assert SkillImportService._source_root_for_session(session) == (tmp_path / "repo")
    with pytest.raises(BusinessError):
        SkillImportService._source_root_for_session(
            SimpleNamespace(temp_storage_path=None, source_type=SkillSourceType.ZIP)
        )
