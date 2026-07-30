"""Behavioral tests for workflow templates."""

from datetime import datetime

import pytest

from app.services.workflow import templates as templates_module
from app.services.workflow.templates import (
    TemplateCategory,
    TemplateManager,
    TemplateVariable,
    TemplateVisibility,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def manager() -> TemplateManager:
    return TemplateManager()


async def test_create_update_and_delete_custom_template(manager: TemplateManager):
    template = await manager.create_template(
        name="Team helper",
        description="Answers team questions",
        category=TemplateCategory.GENERAL,
        visibility=TemplateVisibility.TEAM,
        author_id="user-1",
        author_name="User One",
        nodes=[{"id": "start"}],
        edges=[],
        tags=["team"],
    )

    assert await manager.get_template(template.id) is template

    previous_updated_at = template.updated_at
    updated = await manager.update_template(
        template.id, {"name": "Updated helper", "unknown": "ignored"}
    )
    assert updated is template
    assert template.name == "Updated helper"
    assert not hasattr(template, "unknown")
    assert template.updated_at >= previous_updated_at

    assert await manager.delete_template(template.id) is True
    assert await manager.delete_template(template.id) is False
    assert await manager.delete_template("builtin_qa_bot") is False


async def test_list_templates_filters_sorts_and_paginates(manager: TemplateManager):
    lower = await manager.create_template(
        name="Lower",
        description="Lower ranked",
        category=TemplateCategory.ANALYSIS,
        visibility=TemplateVisibility.PUBLIC,
        author_id="user-1",
        author_name="User One",
        nodes=[],
        edges=[],
        tags=["shared"],
    )
    higher = await manager.create_template(
        name="Higher",
        description="Higher ranked",
        category=TemplateCategory.ANALYSIS,
        visibility=TemplateVisibility.PUBLIC,
        author_id="user-1",
        author_name="User One",
        nodes=[],
        edges=[],
        tags=["shared", "featured"],
    )
    lower.usage_count = 1
    lower.rating = 5
    higher.usage_count = 2

    results = await manager.list_templates(
        category=TemplateCategory.ANALYSIS,
        visibility=TemplateVisibility.PUBLIC,
        author_id="user-1",
        tags=["featured", "missing"],
        limit=1,
    )

    assert results == [higher]
    assert await manager.list_templates(
        category=TemplateCategory.ANALYSIS, offset=1, limit=1
    ) == [lower]


async def test_search_is_case_insensitive_and_excludes_private_templates(
    manager: TemplateManager,
):
    public = await manager.create_template(
        name="Invoice Assistant",
        description="Processes documents",
        category=TemplateCategory.AUTOMATION,
        visibility=TemplateVisibility.PUBLIC,
        author_id="user-1",
        author_name="User One",
        nodes=[],
        edges=[],
        tags=["billing"],
    )
    await manager.create_template(
        name="Private Invoice",
        description="Hidden",
        category=TemplateCategory.AUTOMATION,
        visibility=TemplateVisibility.PRIVATE,
        author_id="user-1",
        author_name="User One",
        nodes=[],
        edges=[],
    )

    assert await manager.search("INVOICE", category=TemplateCategory.AUTOMATION) == [
        public
    ]
    assert await manager.search("billing") == [public]


async def test_instantiate_replaces_nested_values_and_uses_defaults(
    manager: TemplateManager,
):
    template = await manager.create_template(
        name="Parameterized",
        description="Parameterized workflow",
        category=TemplateCategory.CUSTOM,
        visibility=TemplateVisibility.PRIVATE,
        author_id="user-1",
        author_name="User One",
        nodes=[
            {
                "data": {
                    "count": "{{count}}",
                    "message": "Hello {{name}}",
                    "items": ["{{enabled}}"],
                }
            }
        ],
        edges=[{"source": "unchanged"}],
        config={"model": "{{model}}"},
        variables=[
            TemplateVariable("name", "Name", "", "string"),
            TemplateVariable("count", "Count", "", "number", default_value=3),
            TemplateVariable("enabled", "Enabled", "", "boolean", default_value=True),
            TemplateVariable("model", "Model", "", "string", default_value="small"),
        ],
    )

    result = await manager.instantiate(template.id, {"name": "Ada"}, "My workflow")

    assert result["name"] == "My workflow"
    assert result["nodes"][0]["data"] == {
        "count": 3,
        "message": "Hello Ada",
        "items": [True],
    }
    assert result["config"] == {"model": "small"}
    assert result["edges"] == [{"source": "unchanged"}]
    assert template.nodes[0]["data"]["count"] == "{{count}}"
    assert template.usage_count == 1


@pytest.mark.parametrize(
    "template_id,variables,message",
    [
        ("missing", {}, "Template not found: missing"),
        ("builtin_qa_bot", {}, "Missing required variable: model_id"),
    ],
)
async def test_instantiate_rejects_invalid_requests(
    manager: TemplateManager, template_id: str, variables: dict, message: str
):
    with pytest.raises(ValueError, match=message):
        await manager.instantiate(template_id, variables)


async def test_rating_updates_average_and_rejects_invalid_ratings(
    manager: TemplateManager,
):
    template = await manager.get_template("builtin_qa_bot")
    assert template is not None

    assert await manager.rate_template(template.id, "user-1", 5) is True
    assert await manager.rate_template(template.id, "user-2", 3) is True
    assert template.rating == 4
    assert template.rating_count == 2
    assert await manager.rate_template(template.id, "user-3", 0) is False
    assert await manager.rate_template("missing", "user-3", 4) is False


async def test_public_category_and_featured_helpers(manager: TemplateManager):
    assert await manager.get_by_category(TemplateCategory.GENERAL) == [
        await manager.get_template("builtin_qa_bot")
    ]
    assert await manager.get_featured(limit=1) == [
        await manager.get_template("builtin_qa_bot")
    ]


async def test_get_template_manager_reuses_global_instance(monkeypatch):
    monkeypatch.setattr(templates_module, "_template_manager", None)

    manager = templates_module.get_template_manager()

    assert templates_module.get_template_manager() is manager


async def test_serialization_and_stats_reflect_template_state(manager: TemplateManager):
    template = await manager.get_template("builtin_qa_bot")
    assert template is not None
    template.created_at = datetime(2026, 1, 2, 3, 4, 5)
    template.updated_at = datetime(2026, 2, 3, 4, 5, 6)
    template.usage_count = 2

    serialized = template.to_dict()
    summary = template.to_summary()
    stats = await manager.get_stats()

    assert serialized["category"] == "general"
    assert serialized["variables"][0]["type"] == "model"
    assert serialized["created_at"] == "2026-01-02T03:04:05"
    assert serialized["updated_at"] == "2026-02-03T04:05:06"
    assert set(summary) == {
        "id",
        "name",
        "description",
        "category",
        "author_name",
        "tags",
        "version",
        "icon",
        "usage_count",
        "rating",
        "rating_count",
    }
    assert stats == {
        "total_templates": 4,
        "public_templates": 4,
        "builtin_templates": 4,
        "by_category": {
            "general": 1,
            "research": 1,
            "customer_service": 1,
            "code_assistant": 1,
        },
        "total_usage": 2,
    }
