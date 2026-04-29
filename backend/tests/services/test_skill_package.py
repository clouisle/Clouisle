from pathlib import Path

from app.models.skill import SkillExecutionMode
from app.services.skill_package import SkillPackageService


def write_skill(root: Path, skill_md: str, script: str | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "SKILL.md").write_text(skill_md, encoding="utf-8")
    if script:
        script_path = root / script
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text("print('ok')\n", encoding="utf-8")
    return root


def test_parse_script_skill_normalizes_execution_config(tmp_path: Path):
    skill_root = write_skill(
        tmp_path / "echo-skill",
        """---
name: echo-skill
description: Echo input.
x-clouisle:
  execution:
    mode: script
    runtime: python
    script: scripts/run.py
    limits:
      timeout_seconds: 10
    artifacts:
      - path: output/result.json
        optional: true
---
Run the script.
""",
        "scripts/run.py",
    )

    parsed = SkillPackageService.parse_skill_root(tmp_path, skill_root)

    assert parsed.valid is True
    assert parsed.execution_mode == SkillExecutionMode.SCRIPT
    assert parsed.execution_config["runtime"] == "python"
    assert parsed.execution_config["script"] == "scripts/run.py"
    assert parsed.execution_config["limits"]["timeout_seconds"] == 10
    assert parsed.execution_config["artifacts"] == [
        {
            "path": "/workspace/output/result.json",
            "optional": True,
        }
    ]


def test_parse_script_skill_rejects_invalid_runtime(tmp_path: Path):
    skill_root = write_skill(
        tmp_path / "bad-runtime",
        """---
name: bad-runtime
description: Bad runtime.
x-clouisle:
  execution:
    mode: script
    runtime: bash
    script: run.py
---
Run the script.
""",
        "run.py",
    )

    parsed = SkillPackageService.parse_skill_root(tmp_path, skill_root)

    assert "skill_script_runtime_invalid" in parsed.errors


def test_parse_script_skill_rejects_unsafe_artifact_path(tmp_path: Path):
    skill_root = write_skill(
        tmp_path / "bad-artifact",
        """---
name: bad-artifact
description: Bad artifact.
x-clouisle:
  execution:
    mode: script
    runtime: python
    script: run.py
    artifacts:
      - path: /tmp/result.json
---
Run the script.
""",
        "run.py",
    )

    parsed = SkillPackageService.parse_skill_root(tmp_path, skill_root)

    assert "skill_execution_artifact_path_invalid" in parsed.errors


def test_parse_script_skill_rejects_invalid_limits(tmp_path: Path):
    skill_root = write_skill(
        tmp_path / "bad-limits",
        """---
name: bad-limits
description: Bad limits.
x-clouisle:
  execution:
    mode: script
    runtime: python
    script: run.py
    limits:
      timeout_seconds: 9999
---
Run the script.
""",
        "run.py",
    )

    parsed = SkillPackageService.parse_skill_root(tmp_path, skill_root)

    assert "skill_execution_limits_invalid" in parsed.errors
