import stat
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch
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
