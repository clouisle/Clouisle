from pathlib import Path

import pytest

from app.services.skill_package import SkillPackageService


def write_skill(root: Path, skill_md: str, script: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(skill_md, encoding="utf-8")
    if script:
        script_path = root / script
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text("print('ok')\n", encoding="utf-8")
    return root


def test_parse_skill_accepts_spec_frontmatter(tmp_path: Path):
    skill_root = write_skill(
        tmp_path / "pdf-tools",
        """---
name: pdf-tools
description: Extract text from PDFs. Use when the user mentions PDFs.
license: Apache-2.0
compatibility: Requires Python 3.11
metadata:
  author: example-org
allowed-tools: Bash Read
---
Run scripts/extract.py.
""",
        "scripts/extract.py",
    )

    parsed = SkillPackageService.parse_skill_root(tmp_path, skill_root)

    assert parsed.valid is True
    assert parsed.name == "pdf-tools"
    assert parsed.frontmatter["license"] == "Apache-2.0"
    assert parsed.frontmatter["compatibility"] == "Requires Python 3.11"
    assert parsed.frontmatter["metadata"] == {"author": "example-org"}
    assert parsed.frontmatter["allowed-tools"] == "Bash Read"
    assert parsed.package_manifest["file_count"] == 2
    assert {item["path"] for item in parsed.package_manifest["files"]} == {
        "SKILL.md",
        "scripts/extract.py",
    }


def test_parse_skill_treats_execution_extension_as_deprecated(tmp_path: Path):
    skill_root = write_skill(
        tmp_path / "legacy-skill",
        """---
name: legacy-skill
description: Written before Clouisle dropped the execution extension.
x-clouisle:
  execution:
    mode: script
    runtime: python
    script: scripts/run.py
---
Run it.
""",
        "scripts/run.py",
    )

    parsed = SkillPackageService.parse_skill_root(tmp_path, skill_root)

    assert parsed.valid is True
    assert parsed.execution_config == {}
    assert "skill_execution_extension_deprecated" in parsed.warnings


@pytest.mark.parametrize(
    ("name", "expected_errors"),
    [
        ("PDF-Tools", ["skill_name_invalid"]),
        ("pdf--tools", ["skill_name_invalid"]),
        ("-pdf", ["skill_name_invalid"]),
        ("pdf_tools", ["skill_name_invalid"]),
        ("a" * 65, ["skill_name_too_long"]),
    ],
)
def test_parse_skill_rejects_non_spec_names(tmp_path: Path, name, expected_errors):
    skill_root = write_skill(
        tmp_path / "pdf-tools",
        f"""---
name: {name}
description: Extract text from PDFs.
---
Run it.
""",
    )

    parsed = SkillPackageService.parse_skill_root(tmp_path, skill_root)

    assert parsed.valid is False
    assert parsed.errors == expected_errors


def test_parse_skill_reports_directory_name_mismatch(tmp_path: Path):
    skill_root = write_skill(
        tmp_path / "some-folder",
        """---
name: pdf-tools
description: Extract text from PDFs.
---
Run it.
""",
    )

    parsed = SkillPackageService.parse_skill_root(tmp_path, skill_root)

    # A mismatched directory name is a warning: the Skill name drives the
    # workspace path, so the older folder name cannot break staging.
    assert parsed.valid is True
    assert parsed.errors == []
    assert "skill_name_directory_mismatch" in parsed.warnings


def test_parse_skill_rejects_overlong_description(tmp_path: Path):
    skill_root = write_skill(
        tmp_path / "long-skill",
        f"""---
name: long-skill
description: {"d" * 1025}
---
Run it.
""",
    )

    parsed = SkillPackageService.parse_skill_root(tmp_path, skill_root)

    assert parsed.errors == ["skill_description_too_long"]
