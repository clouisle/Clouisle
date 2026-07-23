from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipInfo

import pytest

from app.models.skill import SkillSourceType
from app.schemas.response import BusinessError
from app.services.skill_import import SkillImportService
from app.services.skill_package import ParsedSkillPackage


@pytest.mark.parametrize(
    ("url", "message_key"),
    [
        ("http://example.com/repo.git", "skill_git_url_invalid"),
        ("https:///repo.git", "skill_git_url_invalid"),
        (
            "https://user:secret@example.com/repo.git",
            "skill_git_credentials_not_allowed",
        ),
        ("https://localhost/repo.git", "skill_git_url_invalid"),
        ("https://127.0.0.1/repo.git", "skill_git_url_invalid"),
        ("https://10.0.0.1/repo.git", "skill_git_url_invalid"),
        ("https://169.254.1.1/repo.git", "skill_git_url_invalid"),
    ],
)
def test_validate_git_url_rejects_unsafe_sources(url: str, message_key: str) -> None:
    with pytest.raises(BusinessError) as exc_info:
        SkillImportService._validate_git_url(url)

    assert exc_info.value.msg_key == message_key


def test_validate_git_url_accepts_public_https_host() -> None:
    SkillImportService._validate_git_url("https://github.com/example/skills.git")
    SkillImportService._validate_git_url("https://8.8.8.8/example/skills.git")


@pytest.mark.parametrize(
    ("filename", "file_size", "mode", "message_key"),
    [
        ("../SKILL.md", 1, 0, "skill_zip_path_invalid"),
        ("/SKILL.md", 1, 0, "skill_zip_path_invalid"),
        ("large.bin", 10 * 1024 * 1024 + 1, 0, "skill_zip_file_too_large"),
        ("link", 1, 0o120777, "skill_zip_symlink_not_allowed"),
        ("nested.zip", 1, 0, "skill_zip_nested_archive_not_allowed"),
    ],
)
def test_validate_zip_member_rejects_unsafe_entries(
    filename: str, file_size: int, mode: int, message_key: str
) -> None:
    info = ZipInfo(filename)
    info.file_size = file_size
    info.external_attr = mode << 16

    with pytest.raises(BusinessError) as exc_info:
        SkillImportService._validate_zip_member(info)

    assert exc_info.value.msg_key == message_key


def test_duplicate_warnings_and_preview_conflict_cover_named_packages() -> None:
    unnamed = ParsedSkillPackage(package_path="invalid", errors=["missing_name"])
    first = ParsedSkillPackage(
        package_path="first", name="echo", package_manifest={"file_count": "2"}
    )
    duplicate = ParsedSkillPackage(package_path="second", name="echo")
    existing = ParsedSkillPackage(
        package_path="existing", name="other", warnings=["skill_name_conflict"]
    )

    SkillImportService._attach_duplicate_warnings([unnamed, first, duplicate, existing])

    assert unnamed.warnings == []
    assert first.warnings == []
    assert duplicate.warnings == ["skill_duplicate_name_in_source"]
    preview = SkillImportService._to_preview_item(first)
    assert preview.file_count == 2
    assert preview.conflict is None
    assert SkillImportService._to_preview_item(existing).conflict.type == (
        "existing_team_skill"
    )


def test_source_root_and_url_helpers_normalize_or_reject_input(tmp_path: Path) -> None:
    assert (
        SkillImportService._redact_url(
            "https://user:secret@example.com:8443/repo.git?token=visible"
        )
        == "https://example.com:8443/repo.git?token=visible"
    )
    assert (
        SkillImportService._source_root_for_session(
            SimpleNamespace(
                temp_storage_path=str(tmp_path), source_type=SkillSourceType.GIT
            )
        )
        == (tmp_path / "repo").resolve()
    )
    assert (
        SkillImportService._source_root_for_session(
            SimpleNamespace(
                temp_storage_path=str(tmp_path), source_type=SkillSourceType.ZIP
            )
        )
        == (tmp_path / "source").resolve()
    )

    with pytest.raises(BusinessError) as exc_info:
        SkillImportService._source_root_for_session(
            SimpleNamespace(temp_storage_path=None, source_type=SkillSourceType.ZIP)
        )
    assert exc_info.value.msg_key == "skill_import_session_missing_source"
