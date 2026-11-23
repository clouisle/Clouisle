from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import skill_package
from app.services.skill_package import SkillPackageService


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  My unsafe/package  ", "My-unsafe-package"),
        ("...", "skill"),
    ],
)
def test_safe_package_segment_normalizes_names(value, expected):
    assert skill_package.safe_package_segment(value) == expected


@pytest.mark.parametrize("relative_path", ["/absolute", "../escape"])
def test_resolve_child_path_rejects_unsafe_paths(relative_path):
    assert skill_package.resolve_child_path(Path("/package"), relative_path) is None


def test_find_skill_roots_prunes_ignored_and_deep_directories(monkeypatch):
    seen = []

    def walk(_root):
        root_dirs = ["node_modules", "nested"]
        yield "/package", root_dirs, ["SKILL.md"]
        seen.append(root_dirs)
        deep_dirs = ["deeper"]
        yield "/package/nested", deep_dirs, ["SKILL.md"]
        seen.append(deep_dirs)

    monkeypatch.setattr(skill_package.os, "walk", walk)

    roots = SkillPackageService.find_skill_roots(Path("/package"), max_depth=1)

    assert roots == [Path("/package"), Path("/package/nested")]
    assert seen == [["nested"], []]


def test_parse_skill_root_rejects_path_outside_source():
    parsed = SkillPackageService.parse_skill_root(Path("/source"), Path("/other"))

    assert parsed.errors == ["skill_package_path_invalid"]


@pytest.mark.parametrize(
    ("read_error", "expected"),
    [
        (UnicodeDecodeError("utf-8", b"x", 0, 1, "bad"), "skill_md_must_be_utf8"),
        (OSError(), "skill_md_not_found"),
    ],
)
def test_parse_skill_root_reports_read_failures(monkeypatch, read_error, expected):
    monkeypatch.setattr(
        Path, "read_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(read_error)
    )

    parsed = SkillPackageService.parse_skill_root(
        Path("/source"), Path("/source/skill")
    )

    assert parsed.errors == [expected]


def test_parse_skill_root_validates_metadata_and_extensions(monkeypatch):
    markdown = """---
name: ''
description: ''
category: unknown
x-clouisle: invalid
---
Instructions.
"""
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: markdown)
    monkeypatch.setattr(
        SkillPackageService,
        "build_manifest",
        lambda _root: ({"files": []}, "hash", ["manifest_error"]),
    )

    parsed = SkillPackageService.parse_skill_root(
        Path("/source"), Path("/source/skill")
    )

    assert parsed.category.value == "other"
    assert parsed.errors == [
        "skill_name_required",
        "skill_description_required",
        "skill_clouisle_extension_invalid",
        "manifest_error",
    ]
    assert parsed.package_hash == "hash"


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        ("instructions", "skill_frontmatter_required"),
        ("---\nname: test", "skill_frontmatter_unclosed"),
        ("---\nname: [\n---\nbody", "skill_frontmatter_invalid"),
        ("---\n- item\n---\nbody", "skill_frontmatter_invalid"),
    ],
)
def test_parse_skill_md_reports_invalid_frontmatter(markdown, expected):
    _, _, errors = SkillPackageService.parse_skill_md(markdown)

    assert errors == [expected]


def test_build_manifest_rejects_unsafe_entries(monkeypatch):
    monkeypatch.setattr(
        skill_package.os,
        "walk",
        lambda _root: [
            (
                "/package",
                ["node_modules", "src"],
                ["archive.zip", "escape", "link", "missing", "safe.txt"],
            )
        ],
    )
    monkeypatch.setattr(
        Path,
        "resolve",
        lambda path: Path("/outside") if path.name == "escape" else path,
    )
    monkeypatch.setattr(Path, "is_symlink", lambda path: path.name == "link")
    monkeypatch.setattr(Path, "is_file", lambda path: path.name != "missing")
    monkeypatch.setattr(Path, "stat", lambda _path: SimpleNamespace(st_size=4))
    monkeypatch.setattr(Path, "read_bytes", lambda _path: b"safe")

    manifest, package_hash, errors = SkillPackageService.build_manifest(
        Path("/package")
    )

    assert manifest == {"files": [{"path": "safe.txt", "size": 4}], "file_count": 1}
    assert len(package_hash) == 64
    assert errors == [
        "skill_package_nested_archive_not_allowed",
        "skill_package_path_invalid",
        "skill_package_symlink_not_allowed",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("code", "code"), ("unknown", "other"), (None, "other")],
)
def test_category_field_falls_back_to_other(value, expected):
    assert SkillPackageService._category_field(value).value == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"type": "object", "properties": {}, "required": []}, True),
        ({"type": "array"}, False),
    ],
)
def test_is_object_schema(value, expected):
    assert SkillPackageService._is_object_schema(value) is expected
