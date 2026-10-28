"""Skill definition versions must fit the PostgreSQL INTEGER column."""

from types import SimpleNamespace

from app.api.v1.endpoints.chat_tools import _skill_definition_version

INT4_MAX = 2**31 - 1


def test_skill_definition_version_fits_int4_for_any_content():
    skill = SimpleNamespace(
        id="skill-1",
        version=3,
        package_hash="a" * 64,
        package_path="/skills/demo",
        source_type="inline",
        source_uri=None,
        source_ref=None,
        source_subdir=None,
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
        default_config={"model": "x"},
    )
    for index in range(200):
        value = _skill_definition_version(skill, {"model": f"m{index}"})
        assert 1 <= value <= INT4_MAX
