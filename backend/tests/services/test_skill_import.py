import stat
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call, patch
from uuid import UUID
from zipfile import ZipFile, ZipInfo

import pytest

from app.schemas.response import BusinessError
from app.services import skill_import
from app.models.skill import SkillImportSessionStatus, SkillSourceType
from app.schemas.skill import SkillImportInstallItem, SkillInstallAction
from app.services.skill_import import SkillImportService
from app.services.skill_package import ParsedSkillPackage


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _assert_error(msg_key: str, call) -> None:
    with pytest.raises(BusinessError) as exc_info:
        call()
    assert exc_info.value.msg_key == msg_key


def test_extract_zip_extracts_regular_files(tmp_path: Path):
    zip_path = tmp_path / "skill.zip"
    zip_path.write_bytes(
        _zip_bytes({"skill/SKILL.md": b"instructions", "skill/run.py": b"pass"})
    )
    destination = tmp_path / "extracted"
    destination.mkdir()

    SkillImportService._extract_zip(zip_path, destination)

    assert (destination / "skill" / "SKILL.md").read_bytes() == b"instructions"
    assert (destination / "skill" / "run.py").read_bytes() == b"pass"


def test_extract_zip_rejects_invalid_archive(tmp_path: Path):
    zip_path = tmp_path / "skill.zip"
    zip_path.write_bytes(b"not a zip")

    _assert_error(
        "skill_zip_invalid",
        lambda: SkillImportService._extract_zip(zip_path, tmp_path / "out"),
    )


@pytest.mark.parametrize(
    ("filename", "configure", "msg_key"),
    [
        ("../SKILL.md", None, "skill_zip_path_invalid"),
        ("/SKILL.md", None, "skill_zip_path_invalid"),
        ("bundle.tar", None, "skill_zip_nested_archive_not_allowed"),
        (
            "SKILL.md",
            lambda info: setattr(
                info, "file_size", skill_import._MAX_ZIP_SINGLE_FILE_BYTES + 1
            ),
            "skill_zip_file_too_large",
        ),
        (
            "SKILL.md",
            lambda info: setattr(info, "external_attr", (stat.S_IFLNK | 0o777) << 16),
            "skill_zip_symlink_not_allowed",
        ),
    ],
)
def test_validate_zip_member_rejects_unsafe_entries(filename, configure, msg_key):
    info = ZipInfo(filename)
    if configure:
        configure(info)

    _assert_error(msg_key, lambda: SkillImportService._validate_zip_member(info))


def test_extract_zip_enforces_archive_limits(tmp_path: Path):
    zip_path = tmp_path / "skill.zip"
    zip_path.write_bytes(_zip_bytes({"one": b"12", "two": b"34"}))

    with patch.object(skill_import, "_MAX_ZIP_FILE_COUNT", 1):
        _assert_error(
            "skill_zip_too_many_files",
            lambda: SkillImportService._extract_zip(zip_path, tmp_path / "count"),
        )
    with patch.object(skill_import, "_MAX_ZIP_UNCOMPRESSED_BYTES", 3):
        _assert_error(
            "skill_zip_too_large",
            lambda: SkillImportService._extract_zip(zip_path, tmp_path / "size"),
        )


@pytest.mark.parametrize(
    ("url", "msg_key"),
    [
        ("http://example.com/repo.git", "skill_git_url_invalid"),
        (
            "https://user:secret@example.com/repo.git",
            "skill_git_credentials_not_allowed",
        ),
        ("https://localhost/repo.git", "skill_git_url_invalid"),
        ("https://127.0.0.1/repo.git", "skill_git_url_invalid"),
        ("https://169.254.1.1/repo.git", "skill_git_url_invalid"),
    ],
)
def test_validate_git_url_rejects_unsafe_sources(url: str, msg_key: str):
    _assert_error(msg_key, lambda: SkillImportService._validate_git_url(url))


def test_validate_git_url_accepts_public_https_and_redacts_credentials():
    SkillImportService._validate_git_url("https://example.com/repo.git")

    assert (
        SkillImportService._redact_url(
            "https://user:secret@example.com:8443/repo.git?token=visible"
        )
        == "https://example.com:8443/repo.git?token=visible"
    )


def test_build_private_skill_spec_encodes_files_and_ignores_metadata(tmp_path: Path):
    skill_root = tmp_path / "skill"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_bytes(b"hello")
    (skill_root / ".git").mkdir()
    (skill_root / ".git" / "ignored").write_bytes(b"secret")

    result = SkillImportService._build_private_skill_spec(skill_root)

    assert result == {
        "package_files": [
            {"path": "SKILL.md", "content_base64": "aGVsbG8=", "mode": 0o644}
        ]
    }


@pytest.mark.parametrize(
    ("setup", "msg_key"),
    [
        (
            lambda root: (root / "nested.zip").write_bytes(b"zip"),
            "skill_package_nested_archive_not_allowed",
        ),
        (
            lambda root: (root / "link").symlink_to(root / "SKILL.md"),
            "skill_package_symlink_not_allowed",
        ),
    ],
)
def test_build_private_skill_spec_rejects_unsafe_files(tmp_path: Path, setup, msg_key):
    skill_root = tmp_path / "skill"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_bytes(b"hello")
    setup(skill_root)

    _assert_error(
        msg_key, lambda: SkillImportService._build_private_skill_spec(skill_root)
    )


def test_build_private_skill_spec_enforces_payload_limit(tmp_path: Path):
    skill_root = tmp_path / "skill"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_bytes(b"12")

    with patch.object(skill_import, "_MAX_PACKAGE_PAYLOAD_BYTES", 1):
        _assert_error(
            "skill_zip_too_large",
            lambda: SkillImportService._build_private_skill_spec(skill_root),
        )


@pytest.mark.anyio
async def test_preview_zip_validates_input_before_creating_temp_files():
    user = object()
    with patch.object(
        SkillImportService, "_resolve_import_team", AsyncMock(return_value=None)
    ):
        with pytest.raises(BusinessError) as extension_error:
            await SkillImportService.preview_zip(
                team_id=None, user=user, filename="skill.tar", content=b""
            )
        assert extension_error.value.msg_key == "skill_zip_required"

        with (
            patch.object(skill_import, "_MAX_ZIP_UPLOAD_BYTES", 1),
            pytest.raises(BusinessError) as size_error,
        ):
            await SkillImportService.preview_zip(
                team_id=None, user=user, filename="skill.zip", content=b"12"
            )
        assert size_error.value.msg_key == "skill_zip_too_large"


@pytest.mark.anyio
async def test_preview_zip_extracts_and_hands_off_session(tmp_path: Path):
    user = object()
    team = object()
    expected = object()
    create_preview = AsyncMock(return_value=expected)

    with (
        patch.object(skill_import.tempfile, "mkdtemp", return_value=str(tmp_path)),
        patch.object(
            SkillImportService, "_resolve_import_team", AsyncMock(return_value=team)
        ),
        patch.object(SkillImportService, "_create_preview_session", create_preview),
    ):
        result = await SkillImportService.preview_zip(
            team_id=None,
            user=user,
            filename="skills.ZIP",
            content=_zip_bytes({"echo/SKILL.md": b"instructions"}),
        )

    assert result is expected
    assert (tmp_path / "source" / "echo" / "SKILL.md").read_bytes() == b"instructions"
    create_preview.assert_awaited_once_with(
        team_id=None,
        team=team,
        user=user,
        source_type=skill_import.SkillSourceType.ZIP,
        source_uri="skills.ZIP",
        source_ref=None,
        source_subdir=None,
        source_root=tmp_path / "source",
        temp_storage_path=tmp_path,
    )


@pytest.mark.anyio
async def test_preview_git_uses_resolved_ref_and_redacted_url(tmp_path: Path):
    user = object()
    expected = object()
    clone = AsyncMock()
    create_preview = AsyncMock(return_value=expected)

    with (
        patch.object(skill_import.tempfile, "mkdtemp", return_value=str(tmp_path)),
        patch.object(
            SkillImportService, "_resolve_import_team", AsyncMock(return_value=None)
        ),
        patch.object(SkillImportService, "_clone_git_repo", clone),
        patch.object(
            SkillImportService, "_resolve_git_ref", AsyncMock(return_value="abc123")
        ),
        patch.object(SkillImportService, "_create_preview_session", create_preview),
    ):
        result = await SkillImportService.preview_git(
            team_id=None,
            user=user,
            repo_url="https://example.com:8443/repo.git",
            ref="main",
        )

    assert result is expected
    clone.assert_awaited_once_with(
        "https://example.com:8443/repo.git", "main", tmp_path / "repo"
    )
    assert create_preview.await_args.kwargs["source_uri"] == (
        "https://example.com:8443/repo.git"
    )
    assert create_preview.await_args.kwargs["source_ref"] == "abc123"


@pytest.mark.anyio
async def test_clone_git_repo_reports_stderr_on_failure(tmp_path: Path):
    process = Mock(returncode=1)
    process.communicate = AsyncMock(return_value=(b"", b"fatal: unavailable"))

    with patch.object(
        skill_import.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    ) as create_process:
        with pytest.raises(BusinessError) as exc_info:
            await SkillImportService._clone_git_repo(
                "https://example.com/repo.git", "stable", tmp_path / "repo"
            )

    assert exc_info.value.msg_key == "skill_git_clone_failed"
    assert exc_info.value.data == {"stderr": "fatal: unavailable"}
    assert create_process.await_args.args[:5] == (
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
    )


@pytest.mark.anyio
async def test_clone_git_repo_kills_timed_out_process(tmp_path: Path):
    process = Mock()
    process.communicate = AsyncMock()

    async def _raise_timeout(awaitable, timeout):
        awaitable.close()
        raise TimeoutError

    with (
        patch.object(
            skill_import.asyncio,
            "create_subprocess_exec",
            AsyncMock(return_value=process),
        ),
        patch.object(
            skill_import.asyncio,
            "wait_for",
            _raise_timeout,
        ),
        pytest.raises(BusinessError) as exc_info,
    ):
        await SkillImportService._clone_git_repo(
            "https://example.com/repo.git", None, tmp_path / "repo"
        )

    assert exc_info.value.msg_key == "skill_git_clone_timeout"
    process.kill.assert_called_once_with()
    assert process.communicate.await_args_list == [call()]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("returncode", "stdout", "expected"),
    [(0, b"abc123\n", "abc123"), (1, b"ignored", None), (0, b"", None)],
)
async def test_resolve_git_ref_handles_process_outcomes(
    tmp_path: Path, returncode: int, stdout: bytes, expected: str | None
):
    process = Mock(returncode=returncode)
    process.communicate = AsyncMock(return_value=(stdout, b""))

    with patch.object(
        skill_import.asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=process),
    ):
        assert await SkillImportService._resolve_git_ref(tmp_path) == expected


def _query_result(value):
    query = Mock()
    query.first = AsyncMock(return_value=value)
    return query


@pytest.mark.anyio
async def test_resolve_import_team_enforces_scope_and_admin_access():
    user = SimpleNamespace(is_superuser=False)
    team_id = UUID("00000000-0000-0000-0000-000000000001")
    team = object()

    with (
        patch.object(skill_import.Team, "filter", return_value=_query_result(None)),
        pytest.raises(BusinessError) as missing,
    ):
        await SkillImportService._resolve_import_team(
            team_id=team_id, user=user, admin_mode=True
        )
    assert missing.value.msg_key == "team_not_found"

    with patch.object(
        skill_import.Team, "filter", return_value=_query_result(team)
    ) as team_filter:
        assert (
            await SkillImportService._resolve_import_team(
                team_id=team_id, user=user, admin_mode=True
            )
            is team
        )
    team_filter.assert_called_once_with(id=team_id)

    check_access = AsyncMock(return_value=team)
    with patch.object(skill_import.SkillService, "check_team_access", check_access):
        assert (
            await SkillImportService._resolve_import_team(team_id=team_id, user=user)
            is team
        )
    check_access.assert_awaited_once_with(team_id, user, require_admin=True)

    with pytest.raises(BusinessError) as denied:
        await SkillImportService._resolve_import_team(team_id=None, user=user)
    assert denied.value.msg_key == "skill_system_admin_required"
    assert (
        await SkillImportService._resolve_import_team(
            team_id=None, user=SimpleNamespace(is_superuser=True)
        )
        is None
    )


@pytest.mark.anyio
async def test_create_preview_session_classifies_conflicts_duplicates_and_invalid(
    tmp_path: Path,
):
    existing = object()
    valid = ParsedSkillPackage(
        package_path="one",
        name="echo",
        display_name="Echo",
        package_manifest={"file_count": 2},
        package_hash="hash-one",
    )
    duplicate = ParsedSkillPackage(package_path="two", name="echo")
    invalid = ParsedSkillPackage(
        package_path="bad", name=None, errors=["skill_name_required"]
    )
    created = SimpleNamespace(id=UUID("00000000-0000-0000-0000-000000000002"))
    create_session = AsyncMock(return_value=created)

    with (
        patch.object(
            skill_import.SkillPackageService,
            "find_skill_roots",
            return_value=[tmp_path / "one", tmp_path / "two", tmp_path / "bad"],
        ),
        patch.object(
            skill_import.SkillPackageService,
            "parse_skill_root",
            side_effect=[valid, duplicate, invalid],
        ),
        patch.object(
            skill_import.Skill,
            "filter",
            side_effect=[_query_result(existing), _query_result(existing)],
        ) as skill_filter,
        patch.object(skill_import.SkillImportSession, "create", create_session),
    ):
        result = await SkillImportService._create_preview_session(
            team_id=None,
            team=None,
            user=object(),
            source_type=SkillSourceType.ZIP,
            source_uri="skills.zip",
            source_ref=None,
            source_subdir=None,
            source_root=tmp_path,
            temp_storage_path=tmp_path.parent,
        )

    assert [item.package_path for item in result.skills] == ["one", "two"]
    assert [item.package_path for item in result.invalid] == ["bad"]
    assert result.skills[0].conflict.type == "existing_team_skill"
    assert result.skills[1].warnings == [
        "skill_name_conflict",
        "skill_duplicate_name_in_source",
    ]
    assert skill_filter.call_args_list == [
        call(team_id=None, name="echo"),
        call(team_id=None, name="echo"),
    ]
    preview = create_session.await_args.kwargs["preview"]
    assert preview["skills"][0]["file_count"] == 2
    assert preview["invalid"][0]["errors"] == ["skill_name_required"]
    assert create_session.await_args.kwargs["temp_storage_path"] == str(tmp_path.parent)


@pytest.mark.anyio
async def test_install_rejects_missing_and_expired_sessions():
    with (
        patch.object(
            skill_import.SkillImportSession,
            "filter",
            return_value=_query_result(None),
        ),
        pytest.raises(BusinessError) as missing,
    ):
        await SkillImportService.install_from_session(
            session_id=UUID("00000000-0000-0000-0000-000000000003"),
            items=[],
            is_enabled=True,
            user=object(),
        )
    assert missing.value.msg_key == "skill_import_session_not_found"

    session = SimpleNamespace(
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        status=SkillImportSessionStatus.PREVIEWED,
        save=AsyncMock(),
    )
    with (
        patch.object(
            skill_import.SkillImportSession,
            "filter",
            return_value=_query_result(session),
        ),
        pytest.raises(BusinessError) as expired,
    ):
        await SkillImportService.install_from_session(
            session_id=UUID("00000000-0000-0000-0000-000000000003"),
            items=[],
            is_enabled=True,
            user=object(),
        )
    assert expired.value.msg_key == "skill_import_session_expired"
    assert session.status == SkillImportSessionStatus.EXPIRED
    session.save.assert_awaited_once_with(update_fields=["status", "updated_at"])


@pytest.mark.anyio
async def test_install_processes_skip_validation_conflict_update_and_create(
    tmp_path: Path,
):
    team_id = UUID("00000000-0000-0000-0000-000000000004")
    old_id = UUID("00000000-0000-0000-0000-000000000005")
    new_id = UUID("00000000-0000-0000-0000-000000000006")
    session = SimpleNamespace(
        team_id=team_id,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        source_type=SkillSourceType.ZIP,
        temp_storage_path=str(tmp_path),
        preview={
            "skills": [
                {"package_path": path}
                for path in ["skip", "escape", "invalid", "exists", "update", "new"]
            ]
        },
        status=SkillImportSessionStatus.PREVIEWED,
        save=AsyncMock(),
    )
    source_root = tmp_path / "source"
    source_root.mkdir()
    roots = {
        item["package_path"]: source_root / item["package_path"]
        for item in session.preview["skills"][1:]
    }
    parsed = {
        "invalid": ParsedSkillPackage(
            package_path="invalid", name="bad", errors=["bad"]
        ),
        "exists": ParsedSkillPackage(package_path="exists", name="taken"),
        "update": ParsedSkillPackage(
            package_path="update", name="old", package_hash="u"
        ),
        "new": ParsedSkillPackage(package_path="new", name="fresh", package_hash="n"),
    }
    existing = SimpleNamespace(id=old_id)
    installed = SimpleNamespace(id=new_id)

    def resolve_path(_root, package_path):
        if package_path == "source":
            return source_root
        return None if package_path == "escape" else roots[package_path]

    def parse_root(_source, root):
        return parsed[root.name]

    with (
        patch.object(
            skill_import.SkillImportSession,
            "filter",
            return_value=_query_result(session),
        ),
        patch.object(
            SkillImportService, "_resolve_import_team", AsyncMock(return_value=object())
        ) as resolve_team,
        patch.object(skill_import, "resolve_child_path", side_effect=resolve_path),
        patch.object(
            skill_import.SkillPackageService,
            "parse_skill_root",
            side_effect=parse_root,
        ),
        patch.object(
            skill_import.Skill,
            "filter",
            side_effect=[
                _query_result(object()),
                _query_result(None),
                _query_result(existing),
                _query_result(None),
            ],
        ),
        patch.object(
            SkillImportService,
            "_save_to_private_storage",
            AsyncMock(side_effect=["update.zip", "new.zip"]),
        ) as save_storage,
        patch.object(
            SkillImportService,
            "_build_private_skill_spec",
            side_effect=[{"kind": "update"}, {"kind": "new"}],
        ),
        patch.object(
            SkillImportService,
            "_upsert_skill",
            AsyncMock(side_effect=[existing, installed]),
        ) as upsert,
    ):
        result = await SkillImportService.install_from_session(
            session_id=UUID("00000000-0000-0000-0000-000000000007"),
            items=[
                SkillImportInstallItem(
                    package_path="skip", action=SkillInstallAction.SKIP
                ),
                SkillImportInstallItem(package_path="outside"),
                SkillImportInstallItem(package_path="escape"),
                SkillImportInstallItem(package_path="invalid"),
                SkillImportInstallItem(package_path="exists"),
                SkillImportInstallItem(
                    package_path="update", action=SkillInstallAction.UPDATE
                ),
                SkillImportInstallItem(package_path="new"),
            ],
            is_enabled=False,
            user=object(),
        )

    assert result.skipped == ["skip"]
    assert result.errors == [
        "outside: skill_package_not_in_session",
        "escape: skill_package_path_invalid",
        "invalid: skill_package_invalid",
        "exists: skill_name_exists",
    ]
    assert result.updated == [old_id]
    assert result.installed == [new_id]
    assert save_storage.await_count == 2
    assert upsert.await_args_list[0].kwargs["existing"] is existing
    assert upsert.await_args_list[1].kwargs["existing"] is None
    assert upsert.await_args_list[1].kwargs["is_enabled"] is False
    resolve_team.assert_awaited_once_with(
        team_id=team_id, user=upsert.await_args_list[0].kwargs["user"], admin_mode=False
    )
    assert session.status == SkillImportSessionStatus.INSTALLED
    session.save.assert_awaited_once_with(update_fields=["status", "updated_at"])


def test_session_source_and_storage_keys_are_scope_safe(tmp_path: Path):
    with pytest.raises(BusinessError) as missing:
        SkillImportService._source_root_for_session(
            SimpleNamespace(temp_storage_path=None)
        )
    assert missing.value.msg_key == "skill_import_session_missing_source"

    git_session = SimpleNamespace(
        temp_storage_path=str(tmp_path), source_type=SkillSourceType.GIT
    )
    with patch.object(
        skill_import, "resolve_child_path", return_value=tmp_path / "repo"
    ) as resolve_path:
        assert (
            SkillImportService._source_root_for_session(git_session)
            == tmp_path / "repo"
        )
    resolve_path.assert_called_once_with(tmp_path.resolve(), "repo")

    team_id = UUID("00000000-0000-0000-0000-000000000008")
    assert (
        SkillImportService._package_storage_key(
            team_id=team_id, skill_name="../../Echo Skill", package_hash="abc/def"
        )
        == f"skills/{team_id}/Echo-Skill/abc-def.zip"
    )
    assert (
        SkillImportService._package_storage_key(
            team_id=None, skill_name="echo", package_hash="1234567890abcdef-more"
        )
        == "skills/system/echo/1234567890abcdef.zip"
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("s3://bucket/skills/system/echo/hash.zip", "skills/system/echo/hash.zip"),
        ("s3://bucket", None),
        ("skills/team/echo/hash.zip", "skills/team/echo/hash.zip"),
        ("/outside/hash.zip", None),
    ],
)
def test_storage_key_from_path_normalizes_supported_locations(value, expected):
    assert SkillImportService._storage_key_from_path(value) == expected


@pytest.mark.anyio
async def test_private_storage_save_and_delete_use_backend(tmp_path: Path):
    skill_root = tmp_path / "skill"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_text("hello")
    storage = SimpleNamespace(
        save=AsyncMock(return_value="saved/path.zip"),
        exists=AsyncMock(side_effect=[True, False]),
        delete=AsyncMock(),
    )

    with patch.object(
        skill_import, "get_upload_storage_backend", AsyncMock(return_value=storage)
    ):
        saved = await SkillImportService._save_to_private_storage(
            skill_root=skill_root,
            team_id=None,
            skill_name="echo",
            package_hash="abcdef",
        )
        await SkillImportService.delete_private_storage("skills/system/echo/abcdef.zip")
        await SkillImportService.delete_private_storage(
            "skills/system/echo/missing.zip"
        )
        await SkillImportService.delete_private_storage("/outside/not-owned.zip")

    assert saved == "saved/path.zip"
    key, content = storage.save.await_args.args
    assert key == "skills/system/echo/abcdef.zip"
    with ZipFile(BytesIO(content)) as archive:
        assert archive.namelist() == ["SKILL.md"]
        assert archive.read("SKILL.md") == b"hello"
    assert storage.save.await_args.kwargs == {"content_type": "application/zip"}
    storage.delete.assert_awaited_once_with("skills/system/echo/abcdef.zip")


def test_build_package_archive_ignores_metadata_and_rejects_symlink(tmp_path: Path):
    skill_root = tmp_path / "skill"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_text("hello")
    (skill_root / ".git").mkdir()
    (skill_root / ".git" / "secret").write_text("ignored")

    with ZipFile(
        BytesIO(SkillImportService._build_package_archive(skill_root))
    ) as archive:
        assert archive.namelist() == ["SKILL.md"]

    (skill_root / "link").symlink_to(skill_root / "SKILL.md")
    _assert_error(
        "skill_package_symlink_not_allowed",
        lambda: SkillImportService._build_package_archive(skill_root),
    )


@pytest.mark.anyio
async def test_resolve_update_target_is_team_scoped_and_requires_match():
    team_id = UUID("00000000-0000-0000-0000-000000000009")
    skill_id = UUID("00000000-0000-0000-0000-000000000010")
    expected = object()
    with patch.object(
        skill_import.Skill,
        "filter",
        side_effect=[_query_result(expected), _query_result(None)],
    ) as skill_filter:
        assert (
            await SkillImportService._resolve_update_target(team_id, "echo", skill_id)
            is expected
        )
        with pytest.raises(BusinessError) as missing:
            await SkillImportService._resolve_update_target(team_id, "echo", None)
    assert missing.value.msg_key == "skill_not_found"
    assert skill_filter.call_args_list == [
        call(id=skill_id, team_id=team_id),
        call(team_id=team_id, name="echo"),
    ]


@pytest.mark.anyio
async def test_upsert_skill_updates_existing_and_creates_with_session_scope():
    parsed = ParsedSkillPackage(
        package_path="echo",
        name="echo",
        display_name=None,
        description="description",
        skill_md="raw",
        instructions="run",
        package_hash="hash",
        package_manifest={"file_count": 1},
        warnings=["warning"],
    )
    session = SimpleNamespace(
        team_id=None,
        source_type=SkillSourceType.GIT,
        source_uri="https://example.com/repo.git",
        source_ref="abc",
        source_subdir=None,
    )
    existing = SimpleNamespace(save=AsyncMock())

    assert (
        await SkillImportService._upsert_skill(
            existing=existing,
            parsed=parsed,
            session=session,
            storage_path="old.zip",
            skill_spec={"package_files": []},
            is_enabled=False,
            user=object(),
        )
        is existing
    )
    assert existing.display_name == "echo"
    assert existing.package_storage_path == "old.zip"
    assert existing.is_enabled is False
    existing.save.assert_awaited_once_with()

    created = object()
    with patch.object(
        skill_import.Skill, "create", AsyncMock(return_value=created)
    ) as create_skill:
        assert (
            await SkillImportService._upsert_skill(
                existing=None,
                parsed=parsed,
                session=session,
                storage_path="new.zip",
                skill_spec={"package_files": []},
                is_enabled=True,
                user="creator",
            )
            is created
        )
    assert create_skill.await_args.kwargs["team_id"] is None
    assert create_skill.await_args.kwargs["name"] == "echo"
    assert create_skill.await_args.kwargs["source_ref"] == "abc"
    assert create_skill.await_args.kwargs["created_by"] == "creator"
