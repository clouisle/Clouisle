import asyncio
import stat
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
from zipfile import ZipFile, ZipInfo

import pytest

from app.schemas.response import BusinessError
from app.services import skill_import
from app.services.skill_import import SkillImportService


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/repo.git",
        "https://user@example.com/repo.git",
        "https://localhost/repo.git",
        "https://127.0.0.1/repo.git",
        "https://10.0.0.1/repo.git",
    ],
)
def test_git_url_rejects_unsafe_sources(url):
    with pytest.raises(BusinessError):
        SkillImportService._validate_git_url(url)


def test_git_url_accepts_public_host_and_redacts_credentials_and_port():
    SkillImportService._validate_git_url("https://example.com/repo.git")

    assert (
        SkillImportService._redact_url(
            "https://user:secret@example.com:8443/org/repo.git?x=1"
        )
        == "https://example.com:8443/org/repo.git?x=1"
    )


@pytest.mark.parametrize(
    ("filename", "size", "mode"),
    [
        ("../escape", 0, 0),
        ("/absolute", 0, 0),
        ("large.txt", skill_import._MAX_ZIP_SINGLE_FILE_BYTES + 1, 0),
        ("link", 0, stat.S_IFLNK << 16),
        ("nested.zip", 0, 0),
    ],
)
def test_zip_member_rejects_unsafe_entries(filename, size, mode):
    info = ZipInfo(filename)
    info.file_size = size
    info.external_attr = mode

    with pytest.raises(BusinessError):
        SkillImportService._validate_zip_member(info)


def test_extract_zip_rejects_invalid_archive_and_extracts_safe_files(tmp_path):
    invalid_archive = tmp_path / "invalid.zip"
    invalid_archive.write_bytes(b"not a zip")
    with pytest.raises(BusinessError):
        SkillImportService._extract_zip(invalid_archive, tmp_path / "bad")

    archive_path = tmp_path / "skills.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("skill/SKILL.md", "instructions")
        archive.writestr("skill/empty/", "")

    extract_root = tmp_path / "extract"
    extract_root.mkdir()
    SkillImportService._extract_zip(archive_path, extract_root)

    assert (extract_root / "skill" / "SKILL.md").read_text() == "instructions"


@pytest.mark.anyio
async def test_clone_git_builds_shallow_command_and_reports_failure(
    monkeypatch, tmp_path
):
    process = SimpleNamespace(
        communicate=AsyncMock(return_value=(b"", b"clone denied")), returncode=1
    )
    create_process = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    with pytest.raises(BusinessError):
        await SkillImportService._clone_git_repo(
            "https://example.com/repo.git", "release", tmp_path / "repo"
        )

    assert create_process.await_args.args == (
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        "release",
        "https://example.com/repo.git",
        str(tmp_path / "repo"),
    )


@pytest.mark.anyio
async def test_clone_git_kills_timed_out_process(monkeypatch, tmp_path):
    async def timeout(awaitable, **_kwargs):
        awaitable.close()
        raise TimeoutError

    process = SimpleNamespace(
        communicate=AsyncMock(return_value=(b"", b"")),
        kill=lambda: None,
        returncode=None,
    )
    wait_for = AsyncMock(side_effect=timeout)
    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", AsyncMock(return_value=process)
    )
    monkeypatch.setattr(asyncio, "wait_for", wait_for)

    with pytest.raises(BusinessError):
        await SkillImportService._clone_git_repo(
            "https://example.com/repo.git", None, tmp_path / "repo"
        )

    assert process.communicate.await_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("returncode", "stdout", "expected"),
    [(1, b"ignored", None), (0, b"abc123\n", "abc123"), (0, b"", None)],
)
async def test_resolve_git_ref_handles_process_results(
    monkeypatch, tmp_path, returncode, stdout, expected
):
    process = SimpleNamespace(
        communicate=AsyncMock(return_value=(stdout, b"")), returncode=returncode
    )
    create_process = AsyncMock(return_value=process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)

    assert await SkillImportService._resolve_git_ref(tmp_path) == expected
    assert create_process.await_args.args[:3] == ("git", "-C", str(tmp_path))


def test_session_source_root_validates_storage_and_source_type(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    session = SimpleNamespace(temp_storage_path=str(tmp_path), source_type="zip")

    assert SkillImportService._source_root_for_session(session) == source

    session.temp_storage_path = None
    with pytest.raises(BusinessError):
        SkillImportService._source_root_for_session(session)


def test_private_skill_spec_encodes_files_ignores_metadata_and_rejects_archive(
    tmp_path,
):
    root = tmp_path / "skill"
    root.mkdir()
    (root / "SKILL.md").write_text("hello", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "ignored").write_text("secret", encoding="utf-8")

    spec = SkillImportService._build_private_skill_spec(root)
    assert spec["package_files"] == [
        {"path": "SKILL.md", "content_base64": "aGVsbG8=", "mode": 0o644}
    ]

    (root / "payload.zip").write_bytes(b"zip")
    with pytest.raises(BusinessError):
        SkillImportService._build_private_skill_spec(root)


def test_storage_path_parsing_and_package_key(monkeypatch, tmp_path):
    monkeypatch.setattr(skill_import, "_UPLOAD_ROOT", tmp_path)
    local = tmp_path / "skills" / "system" / "demo" / "hash.zip"

    assert SkillImportService._storage_key_from_path(None) is None
    assert (
        SkillImportService._storage_key_from_path("s3://bucket/skills/demo.zip")
        == "skills/demo.zip"
    )
    assert SkillImportService._storage_key_from_path(str(local)) == (
        "skills/system/demo/hash.zip"
    )
    assert (
        SkillImportService._package_storage_key(
            team_id=None, skill_name="demo skill", package_hash="abcdef"
        )
        == "skills/system/demo-skill/abcdef.zip"
    )


@pytest.mark.anyio
async def test_delete_private_storage_skips_missing_key_and_deletes_existing(
    monkeypatch,
):
    storage = SimpleNamespace(exists=AsyncMock(return_value=True), delete=AsyncMock())
    backend = AsyncMock(return_value=storage)
    monkeypatch.setattr(skill_import, "get_upload_storage_backend", backend)

    await SkillImportService.delete_private_storage(None)
    backend.assert_not_awaited()

    await SkillImportService.delete_private_storage("skills/system/demo/hash.zip")
    storage.delete.assert_awaited_once_with("skills/system/demo/hash.zip")


@pytest.mark.anyio
async def test_resolve_import_team_enforces_admin_boundaries(monkeypatch):
    user = SimpleNamespace(is_superuser=False)
    access = AsyncMock(return_value="team")
    monkeypatch.setattr(skill_import.SkillService, "check_team_access", access)
    team_id = uuid4()

    assert (
        await SkillImportService._resolve_import_team(team_id=team_id, user=user)
        == "team"
    )
    access.assert_awaited_once_with(team_id, user, require_admin=True)

    with pytest.raises(BusinessError):
        await SkillImportService._resolve_import_team(team_id=None, user=user)
