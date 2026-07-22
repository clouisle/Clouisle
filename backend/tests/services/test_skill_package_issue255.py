from pathlib import Path

import pytest

from app.services.skill_package import SkillPackageService


@pytest.mark.parametrize(
    ("content", "error", "instructions"),
    [
        ("Instructions only", "skill_frontmatter_required", "Instructions only"),
        ("---\nname: demo", "skill_frontmatter_unclosed", "---\nname: demo"),
        ("---\nname: [\n---\nRun it.\n", "skill_frontmatter_invalid", "Run it.\n"),
        ("---\n- item\n---\nRun it.\n", "skill_frontmatter_invalid", "Run it.\n"),
    ],
)
def test_parse_skill_md_rejects_invalid_frontmatter(content, error, instructions):
    frontmatter, parsed_instructions, errors = SkillPackageService.parse_skill_md(
        content
    )

    assert frontmatter == {}
    assert parsed_instructions == instructions
    assert errors == [error]


def test_parse_skill_root_rejects_outside_and_missing_roots(tmp_path: Path):
    outside = tmp_path.parent / "outside-skill"
    missing = tmp_path / "missing-skill"

    outside_result = SkillPackageService.parse_skill_root(tmp_path, outside)
    missing_result = SkillPackageService.parse_skill_root(tmp_path, missing)

    assert outside_result.errors == ["skill_package_path_invalid"]
    assert missing_result.errors == ["skill_md_not_found"]


def test_find_skill_roots_honors_ignored_directories_and_depth(tmp_path: Path):
    visible = tmp_path / "visible"
    ignored = tmp_path / "node_modules" / "ignored"
    too_deep = tmp_path / "one" / "two"
    for root in (visible, ignored, too_deep):
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text("instructions", encoding="utf-8")

    assert SkillPackageService.find_skill_roots(tmp_path, max_depth=1) == [visible]


def test_normalize_script_config_collects_missing_fields_and_artifact_errors(
    tmp_path: Path,
):
    config, errors = SkillPackageService._normalize_execution_config(
        {
            "mode": "script",
            "limits": "invalid",
            "artifacts": [42, {}, "/tmp/result.txt", "output/result.txt"],
        },
        tmp_path,
    )

    assert config["limits"] == "invalid"
    assert config["artifacts"] == [
        {"path": "/workspace/output/result.txt", "optional": False}
    ]
    assert errors == [
        "skill_script_runtime_required",
        "skill_script_required",
        "skill_execution_limits_invalid",
        "skill_execution_artifacts_invalid",
        "skill_execution_artifact_path_invalid",
        "skill_execution_artifact_path_invalid",
    ]


def test_normalize_script_config_accepts_javascript_and_workspace_root(tmp_path: Path):
    script = tmp_path / "run.js"
    script.write_text("console.log('ok')", encoding="utf-8")

    config, errors = SkillPackageService._normalize_execution_config(
        {
            "mode": "script",
            "runtime": "javascript",
            "script": "run.js",
            "artifacts": ["/workspace"],
        },
        tmp_path,
    )

    assert errors == []
    assert config["runtime"] == "node"
    assert config["script"] == "run.js"
    assert config["artifacts"] == [{"path": "/workspace", "optional": False}]


def test_build_manifest_skips_symlinks_and_nested_archives(tmp_path: Path):
    (tmp_path / "SKILL.md").write_text("instructions", encoding="utf-8")
    (tmp_path / "nested.zip").write_bytes(b"archive")
    target = tmp_path / "resource.txt"
    target.write_text("resource", encoding="utf-8")
    link = tmp_path / "resource-link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable")

    manifest, package_hash, errors = SkillPackageService.build_manifest(tmp_path)

    assert manifest == {
        "files": [
            {"path": "SKILL.md", "size": 12},
            {"path": "resource.txt", "size": 8},
        ],
        "file_count": 2,
    }
    assert len(package_hash) == 64
    assert errors == [
        "skill_package_nested_archive_not_allowed",
        "skill_package_symlink_not_allowed",
    ]
