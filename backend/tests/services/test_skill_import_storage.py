from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

import pytest

from app.services import skill_import, upload_storage
from app.services.skill_import import SkillImportService


def write_skill(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(
        "---\nname: echo-skill\n---\nUse it.\n", encoding="utf-8"
    )
    (root / "scripts").mkdir()
    (root / "scripts" / "run.py").write_text("print('ok')\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "ignored").write_text("ignore me\n", encoding="utf-8")
    return root


@pytest.mark.anyio
async def test_save_to_private_storage_uses_local_upload_backend(tmp_path: Path):
    skill_root = write_skill(tmp_path / "skill")

    with (
        patch.object(
            skill_import,
            "_UPLOAD_ROOT",
            tmp_path / "uploads",
        ),
        patch.object(
            upload_storage.SiteSetting,
            "get_all_by_category",
            return_value={},
        ),
    ):
        storage_path = await SkillImportService._save_to_private_storage(
            skill_root=skill_root,
            team_id=None,
            skill_name="echo-skill",
            package_hash="abc123def456",
        )

        package_path = Path(storage_path)
        assert (
            package_path
            == tmp_path
            / "uploads"
            / "skills"
            / "system"
            / "echo-skill"
            / "abc123def456.zip"
        )
        assert package_path.exists()
        assert (
            SkillImportService._storage_key_from_path(storage_path)
            == "skills/system/echo-skill/abc123def456.zip"
        )

        with ZipFile(package_path) as archive:
            assert sorted(archive.namelist()) == ["SKILL.md", "scripts/run.py"]

        await SkillImportService.delete_private_storage(storage_path)

    assert not package_path.exists()


@pytest.mark.anyio
async def test_save_to_private_storage_uses_object_upload_backend(
    monkeypatch, tmp_path: Path
):
    calls: list[tuple[str, dict]] = []
    team_id = uuid4()
    skill_root = write_skill(tmp_path / "skill")

    class FakeClient:
        async def put_object(self, **kwargs):
            calls.append(("put_object", kwargs))

        async def head_object(self, **kwargs):
            calls.append(("head_object", kwargs))

        async def delete_object(self, **kwargs):
            calls.append(("delete_object", kwargs))

    class FakeClientContext:
        async def __aenter__(self):
            return FakeClient()

        async def __aexit__(self, exc_type, exc, tb):
            return None

    class FakeSession:
        def create_client(self, *args, **kwargs):
            return FakeClientContext()

    monkeypatch.setattr(upload_storage, "get_session", lambda: FakeSession())

    with patch.object(
        upload_storage.SiteSetting,
        "get_all_by_category",
        return_value={
            "upload_storage_backend": "object",
            "object_storage_endpoint": "minio:9000",
            "object_storage_bucket": "uploads",
            "object_storage_access_key": "access",
            "object_storage_secret_key": "secret",
            "object_storage_secure": False,
            "object_storage_force_path_style": True,
        },
    ):
        storage_path = await SkillImportService._save_to_private_storage(
            skill_root=skill_root,
            team_id=team_id,
            skill_name="echo-skill",
            package_hash="abc123def456",
        )
        await SkillImportService.delete_private_storage(storage_path)

    storage_key = f"skills/{team_id}/echo-skill/abc123def456.zip"
    assert storage_path == f"s3://uploads/{storage_key}"
    assert (
        "put_object",
        {
            "Bucket": "uploads",
            "Key": storage_key,
            "Body": calls[0][1]["Body"],
            "ContentType": "application/zip",
        },
    ) in calls
    assert isinstance(calls[0][1]["Body"], bytes)
    assert ("head_object", {"Bucket": "uploads", "Key": storage_key}) in calls
    assert ("delete_object", {"Bucket": "uploads", "Key": storage_key}) in calls


def test_storage_key_from_path_accepts_opaque_skill_key():
    assert (
        SkillImportService._storage_key_from_path("skills/system/echo/abc.zip")
        == "skills/system/echo/abc.zip"
    )


def test_storage_key_from_path_ignores_legacy_external_paths(tmp_path: Path):
    assert SkillImportService._storage_key_from_path(str(tmp_path / "legacy")) is None
