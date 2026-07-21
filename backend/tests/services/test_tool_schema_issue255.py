from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.tool import (
    CodeConfigSchema,
    CodeExecuteRequest,
    CustomToolType,
    HttpMethod,
    ToolCreateInput,
    ToolShareInput,
    ToolSharePermission,
    ToolType,
    ToolUpdateInput,
    get_builtin_tool_description_key,
    get_builtin_tool_parameter_description_key,
)


def test_tool_create_defaults_and_serialization():
    tool = ToolCreateInput(
        name="weather_lookup",
        display_name="Weather lookup",
        custom_type=CustomToolType.HTTP,
        http_config={"url": "https://example.com/{{city}}"},
    )

    assert tool.type is ToolType.CUSTOM
    assert tool.category == "other"
    assert tool.is_enabled is True
    assert tool.parameters == []
    assert tool.http_config is not None
    assert tool.http_config.method is HttpMethod.GET
    assert tool.http_config.timeout == 30
    assert tool.model_dump(mode="json")["custom_type"] == "http"


def test_tool_name_validators_accept_valid_names_and_optional_update():
    assert ToolCreateInput(name="Tool_2", display_name="Tool").name == "Tool_2"
    assert ToolUpdateInput(name="renamed_tool").name == "renamed_tool"
    assert ToolUpdateInput().name is None


@pytest.mark.parametrize("schema", [ToolCreateInput, ToolUpdateInput])
def test_tool_name_validators_reject_invalid_names(schema):
    with pytest.raises(ValidationError, match="tool_name_invalid_format"):
        schema(
            name="2-invalid",
            **({"display_name": "Tool"} if schema is ToolCreateInput else {}),
        )


def test_code_config_normalizes_legacy_dependencies_by_language():
    python = CodeConfigSchema(
        language="python",
        code="pass",
        dependencies=["httpx"],
        python_package_index_url=" https://packages.example/simple/ ",
    )
    javascript = CodeConfigSchema(
        language="javascript",
        code="return true",
        dependencies=["zod"],
        node_package_registry_url=" https://registry.example/npm/ ",
    )

    assert python.python_packages == ["httpx"]
    assert python.python_package_index_url == "https://packages.example/simple"
    assert javascript.js_packages == ["zod"]
    assert javascript.node_package_registry_url == "https://registry.example/npm"


def test_code_config_preserves_explicit_packages_and_ignores_extra_fields():
    config = CodeConfigSchema(
        language="python",
        code="pass",
        dependencies=["legacy"],
        python_packages=["current"],
        obsolete_runtime="ignored",
    )

    assert config.python_packages == ["current"]
    assert config.command == []
    assert config.limits.timeout_seconds == 30
    assert "obsolete_runtime" not in config.model_dump()


def test_code_normalizers_return_non_mapping_input_unchanged():
    payload = ["not", "a", "mapping"]

    assert CodeConfigSchema.normalize_legacy_dependencies(payload) is payload
    assert CodeExecuteRequest.normalize_package_source_urls(payload) is payload


def test_code_execute_defaults_normalization_and_invalid_limits():
    request = CodeExecuteRequest(
        language="python",
        code="print('ok')",
        python_package_index_url="   ",
    )

    assert request.timeout == 30
    assert request.params == {}
    assert request.python_package_index_url is None
    assert request.model_dump(mode="json")["limits"]["disk_mb"] == 1024

    with pytest.raises(ValidationError):
        CodeExecuteRequest(language="python", code="pass", timeout=61)


def test_builtin_tool_translation_keys():
    assert get_builtin_tool_description_key("calculate") == (
        "builtin_tool_calculate_description"
    )
    assert get_builtin_tool_parameter_description_key("calculate", "expression") == (
        "builtin_tool_calculate_param_expression_description"
    )


def test_nested_constraints_and_share_serialization():
    with pytest.raises(ValidationError):
        CodeConfigSchema(
            language="python",
            code="pass",
            artifacts=[{"path": "/workspace/out", "size": -1}],
        )

    team_id = uuid4()
    share = ToolShareInput(team_id=team_id)
    assert share.permission is ToolSharePermission.READ_ONLY
    assert share.model_dump(mode="json") == {
        "team_id": str(team_id),
        "permission": "read_only",
    }
