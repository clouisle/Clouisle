import stat
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, Mock, call, patch
from zipfile import ZipFile, ZipInfo

import pytest

from app.schemas.response import BusinessError
from app.services import skill_import
from app.services.skill_import import SkillImportService


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
