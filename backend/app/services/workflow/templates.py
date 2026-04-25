"""
Workflow templates.

Provides a template system for reusable workflow patterns:
- Pre-built workflow templates
- Template marketplace
- Template customization and instantiation
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4

from .types import WorkflowValue

logger = logging.getLogger(__name__)


class TemplateCategory(str, Enum):
    """Template categories."""

    GENERAL = "general"
    CUSTOMER_SERVICE = "customer_service"
    DATA_PROCESSING = "data_processing"
    CONTENT_GENERATION = "content_generation"
    CODE_ASSISTANT = "code_assistant"
    RESEARCH = "research"
    AUTOMATION = "automation"
    ANALYSIS = "analysis"
    CUSTOM = "custom"


class TemplateVisibility(str, Enum):
    """Template visibility levels."""

    PUBLIC = "public"  # Available to all
    TEAM = "team"  # Team-only
    PRIVATE = "private"  # Creator-only


@dataclass
class TemplateVariable:
    """A customizable variable in a template."""

    name: str
    label: str
    description: str
    variable_type: str  # string, number, boolean, select, model, tool
    default_value: WorkflowValue | None = None
    required: bool = True
    options: list[WorkflowValue] = field(default_factory=list)  # For select type
    validation: dict = field(default_factory=dict)  # Validation rules

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "type": self.variable_type,
            "default": self.default_value,
            "required": self.required,
            "options": self.options,
            "validation": self.validation,
        }


@dataclass
class WorkflowTemplate:
    """Workflow template definition."""

    id: str
    name: str
    description: str
    category: TemplateCategory
    visibility: TemplateVisibility
    author_id: str
    author_name: str

    # Workflow structure
    nodes: list[dict]
    edges: list[dict]
    config: dict = field(default_factory=dict)

    # Template variables
    variables: list[TemplateVariable] = field(default_factory=list)

    # Metadata
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    preview_image: str | None = None
    icon: str | None = None

    # Stats
    usage_count: int = 0
    rating: float = 0.0
    rating_count: int = 0

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "visibility": self.visibility.value,
            "author_id": self.author_id,
            "author_name": self.author_name,
            "nodes": self.nodes,
            "edges": self.edges,
            "config": self.config,
            "variables": [v.to_dict() for v in self.variables],
            "tags": self.tags,
            "version": self.version,
            "preview_image": self.preview_image,
            "icon": self.icon,
            "usage_count": self.usage_count,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def to_summary(self) -> dict:
        """Get template summary for listing."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "author_name": self.author_name,
            "tags": self.tags,
            "version": self.version,
            "icon": self.icon,
            "usage_count": self.usage_count,
            "rating": self.rating,
            "rating_count": self.rating_count,
        }


class TemplateManager:
    """
    Manages workflow templates.

    Provides:
    - Template CRUD operations
    - Template discovery and search
    - Template instantiation
    - Rating and usage tracking

    Example:
        manager = TemplateManager()

        # Create template from workflow
        template = await manager.create_from_workflow(
            workflow_id="wf_123",
            name="Customer Support Bot",
            description="AI-powered customer support",
            category=TemplateCategory.CUSTOMER_SERVICE,
        )

        # Instantiate template
        workflow = await manager.instantiate(
            template_id=template.id,
            variables={"model_id": "gpt-4", "greeting": "Hello!"},
        )

        # Browse templates
        templates = await manager.search(
            category=TemplateCategory.CUSTOMER_SERVICE,
            query="support",
        )
    """

    def __init__(self):
        # In-memory storage (use database in production)
        self._templates: dict[str, WorkflowTemplate] = {}
        self._init_builtin_templates()

    def _init_builtin_templates(self):
        """Initialize built-in templates."""
        # Simple Q&A Bot
        self._templates["builtin_qa_bot"] = WorkflowTemplate(
            id="builtin_qa_bot",
            name="Simple Q&A Bot",
            description="A basic question-answering bot using LLM",
            category=TemplateCategory.GENERAL,
            visibility=TemplateVisibility.PUBLIC,
            author_id="system",
            author_name="System",
            nodes=[
                {
                    "id": "start_1",
                    "type": "start",
                    "data": {"label": "Start"},
                    "position": {"x": 100, "y": 100},
                },
                {
                    "id": "llm_1",
                    "type": "llm",
                    "data": {
                        "label": "LLM Response",
                        "model_id": "{{model_id}}",
                        "prompt": "{{system_prompt}}",
                        "temperature": 0.7,
                    },
                    "position": {"x": 100, "y": 200},
                },
                {
                    "id": "end_1",
                    "type": "end",
                    "data": {"label": "End"},
                    "position": {"x": 100, "y": 300},
                },
            ],
            edges=[
                {"id": "e1", "source": "start_1", "target": "llm_1"},
                {"id": "e2", "source": "llm_1", "target": "end_1"},
            ],
            variables=[
                TemplateVariable(
                    name="model_id",
                    label="LLM Model",
                    description="Select the language model",
                    variable_type="model",
                    required=True,
                ),
                TemplateVariable(
                    name="system_prompt",
                    label="System Prompt",
                    description="System instructions for the AI",
                    variable_type="string",
                    default_value="You are a helpful assistant.",
                    required=True,
                ),
            ],
            tags=["simple", "qa", "beginner"],
            icon="💬",
        )

        # RAG Knowledge Bot
        self._templates["builtin_rag_bot"] = WorkflowTemplate(
            id="builtin_rag_bot",
            name="RAG Knowledge Bot",
            description="Knowledge base powered Q&A with retrieval augmentation",
            category=TemplateCategory.RESEARCH,
            visibility=TemplateVisibility.PUBLIC,
            author_id="system",
            author_name="System",
            nodes=[
                {
                    "id": "start_1",
                    "type": "start",
                    "data": {"label": "Start"},
                    "position": {"x": 100, "y": 100},
                },
                {
                    "id": "kb_1",
                    "type": "knowledge_retrieval",
                    "data": {
                        "label": "Search Knowledge",
                        "knowledge_base_id": "{{knowledge_base_id}}",
                        "top_k": "{{retrieval_count}}",
                    },
                    "position": {"x": 100, "y": 200},
                },
                {
                    "id": "llm_1",
                    "type": "llm",
                    "data": {
                        "label": "Generate Answer",
                        "model_id": "{{model_id}}",
                        "prompt": "Based on the following context, answer the user's question.\n\nContext:\n{{knowledge_retrieval.results}}\n\nQuestion: {{input.query}}",
                        "temperature": 0.5,
                    },
                    "position": {"x": 100, "y": 300},
                },
                {
                    "id": "end_1",
                    "type": "end",
                    "data": {"label": "End"},
                    "position": {"x": 100, "y": 400},
                },
            ],
            edges=[
                {"id": "e1", "source": "start_1", "target": "kb_1"},
                {"id": "e2", "source": "kb_1", "target": "llm_1"},
                {"id": "e3", "source": "llm_1", "target": "end_1"},
            ],
            variables=[
                TemplateVariable(
                    name="knowledge_base_id",
                    label="Knowledge Base",
                    description="Select the knowledge base",
                    variable_type="knowledge_base",
                    required=True,
                ),
                TemplateVariable(
                    name="model_id",
                    label="LLM Model",
                    description="Select the language model",
                    variable_type="model",
                    required=True,
                ),
                TemplateVariable(
                    name="retrieval_count",
                    label="Retrieval Count",
                    description="Number of documents to retrieve",
                    variable_type="number",
                    default_value=5,
                    validation={"min": 1, "max": 20},
                ),
            ],
            tags=["rag", "knowledge", "retrieval"],
            icon="📚",
        )

        # Conditional Router
        self._templates["builtin_conditional_router"] = WorkflowTemplate(
            id="builtin_conditional_router",
            name="Intent Router",
            description="Route conversations based on detected intent",
            category=TemplateCategory.CUSTOMER_SERVICE,
            visibility=TemplateVisibility.PUBLIC,
            author_id="system",
            author_name="System",
            nodes=[
                {
                    "id": "start_1",
                    "type": "start",
                    "data": {"label": "Start"},
                    "position": {"x": 200, "y": 100},
                },
                {
                    "id": "llm_classify",
                    "type": "llm",
                    "data": {
                        "label": "Classify Intent",
                        "model_id": "{{model_id}}",
                        "prompt": "Classify the following message into one of these intents: {{intents}}. Return only the intent name.\n\nMessage: {{input.message}}",
                        "temperature": 0,
                    },
                    "position": {"x": 200, "y": 200},
                },
                {
                    "id": "router_1",
                    "type": "condition",
                    "data": {
                        "label": "Route by Intent",
                        "conditions": [
                            {
                                "condition": "llm_classify.output == 'support'",
                                "target": "llm_support",
                            },
                            {
                                "condition": "llm_classify.output == 'sales'",
                                "target": "llm_sales",
                            },
                            {"condition": "true", "target": "llm_general"},
                        ],
                    },
                    "position": {"x": 200, "y": 300},
                },
                {
                    "id": "llm_support",
                    "type": "llm",
                    "data": {
                        "label": "Support Response",
                        "model_id": "{{model_id}}",
                        "prompt": "You are a support agent. Help with: {{input.message}}",
                    },
                    "position": {"x": 50, "y": 400},
                },
                {
                    "id": "llm_sales",
                    "type": "llm",
                    "data": {
                        "label": "Sales Response",
                        "model_id": "{{model_id}}",
                        "prompt": "You are a sales representative. Help with: {{input.message}}",
                    },
                    "position": {"x": 200, "y": 400},
                },
                {
                    "id": "llm_general",
                    "type": "llm",
                    "data": {
                        "label": "General Response",
                        "model_id": "{{model_id}}",
                        "prompt": "You are a helpful assistant. Help with: {{input.message}}",
                    },
                    "position": {"x": 350, "y": 400},
                },
                {
                    "id": "end_1",
                    "type": "end",
                    "data": {"label": "End"},
                    "position": {"x": 200, "y": 500},
                },
            ],
            edges=[
                {"id": "e1", "source": "start_1", "target": "llm_classify"},
                {"id": "e2", "source": "llm_classify", "target": "router_1"},
                {"id": "e3", "source": "router_1", "target": "llm_support"},
                {"id": "e4", "source": "router_1", "target": "llm_sales"},
                {"id": "e5", "source": "router_1", "target": "llm_general"},
                {"id": "e6", "source": "llm_support", "target": "end_1"},
                {"id": "e7", "source": "llm_sales", "target": "end_1"},
                {"id": "e8", "source": "llm_general", "target": "end_1"},
            ],
            variables=[
                TemplateVariable(
                    name="model_id",
                    label="LLM Model",
                    description="Select the language model",
                    variable_type="model",
                    required=True,
                ),
                TemplateVariable(
                    name="intents",
                    label="Intent List",
                    description="Comma-separated list of intents",
                    variable_type="string",
                    default_value="support, sales, general",
                ),
            ],
            tags=["router", "intent", "classification", "customer-service"],
            icon="🔀",
        )

        # Code Review Assistant
        self._templates["builtin_code_review"] = WorkflowTemplate(
            id="builtin_code_review",
            name="Code Review Assistant",
            description="Automated code review with multiple perspectives",
            category=TemplateCategory.CODE_ASSISTANT,
            visibility=TemplateVisibility.PUBLIC,
            author_id="system",
            author_name="System",
            nodes=[
                {
                    "id": "start_1",
                    "type": "start",
                    "data": {"label": "Start"},
                    "position": {"x": 200, "y": 100},
                },
                {
                    "id": "parallel_1",
                    "type": "parallel",
                    "data": {"label": "Parallel Review"},
                    "position": {"x": 200, "y": 200},
                },
                {
                    "id": "llm_security",
                    "type": "llm",
                    "data": {
                        "label": "Security Review",
                        "model_id": "{{model_id}}",
                        "prompt": "Review this code for security issues:\n\n{{input.code}}",
                    },
                    "position": {"x": 50, "y": 300},
                },
                {
                    "id": "llm_quality",
                    "type": "llm",
                    "data": {
                        "label": "Quality Review",
                        "model_id": "{{model_id}}",
                        "prompt": "Review this code for quality and best practices:\n\n{{input.code}}",
                    },
                    "position": {"x": 200, "y": 300},
                },
                {
                    "id": "llm_perf",
                    "type": "llm",
                    "data": {
                        "label": "Performance Review",
                        "model_id": "{{model_id}}",
                        "prompt": "Review this code for performance issues:\n\n{{input.code}}",
                    },
                    "position": {"x": 350, "y": 300},
                },
                {
                    "id": "merge_1",
                    "type": "merge",
                    "data": {"label": "Merge Reviews"},
                    "position": {"x": 200, "y": 400},
                },
                {
                    "id": "llm_summary",
                    "type": "llm",
                    "data": {
                        "label": "Summary",
                        "model_id": "{{model_id}}",
                        "prompt": "Summarize these code reviews into a final report:\n\nSecurity: {{llm_security.output}}\n\nQuality: {{llm_quality.output}}\n\nPerformance: {{llm_perf.output}}",
                    },
                    "position": {"x": 200, "y": 500},
                },
                {
                    "id": "end_1",
                    "type": "end",
                    "data": {"label": "End"},
                    "position": {"x": 200, "y": 600},
                },
            ],
            edges=[
                {"id": "e1", "source": "start_1", "target": "parallel_1"},
                {"id": "e2", "source": "parallel_1", "target": "llm_security"},
                {"id": "e3", "source": "parallel_1", "target": "llm_quality"},
                {"id": "e4", "source": "parallel_1", "target": "llm_perf"},
                {"id": "e5", "source": "llm_security", "target": "merge_1"},
                {"id": "e6", "source": "llm_quality", "target": "merge_1"},
                {"id": "e7", "source": "llm_perf", "target": "merge_1"},
                {"id": "e8", "source": "merge_1", "target": "llm_summary"},
                {"id": "e9", "source": "llm_summary", "target": "end_1"},
            ],
            variables=[
                TemplateVariable(
                    name="model_id",
                    label="LLM Model",
                    description="Select the language model",
                    variable_type="model",
                    required=True,
                ),
            ],
            tags=["code", "review", "parallel", "developer"],
            icon="🔍",
        )

    # Template CRUD

    async def create_template(
        self,
        name: str,
        description: str,
        category: TemplateCategory,
        visibility: TemplateVisibility,
        author_id: str,
        author_name: str,
        nodes: list[dict],
        edges: list[dict],
        variables: list[TemplateVariable] | None = None,
        config: dict | None = None,
        tags: list[str] | None = None,
        icon: str | None = None,
    ) -> WorkflowTemplate:
        """Create a new template."""
        template = WorkflowTemplate(
            id=str(uuid4()),
            name=name,
            description=description,
            category=category,
            visibility=visibility,
            author_id=author_id,
            author_name=author_name,
            nodes=nodes,
            edges=edges,
            variables=variables or [],
            config=config or {},
            tags=tags or [],
            icon=icon,
        )

        self._templates[template.id] = template
        logger.info(f"Created template: {template.id} - {name}")
        return template

    async def create_from_workflow(
        self,
        workflow_id: str,
        name: str,
        description: str,
        category: TemplateCategory,
        visibility: TemplateVisibility,
        author_id: str,
        author_name: str,
        variables: list[TemplateVariable] | None = None,
        tags: list[str] | None = None,
    ) -> WorkflowTemplate:
        """Create a template from an existing workflow."""
        # In production, fetch workflow from database
        # For now, return placeholder
        raise NotImplementedError("Implement workflow fetching")

    async def get_template(self, template_id: str) -> WorkflowTemplate | None:
        """Get a template by ID."""
        return self._templates.get(template_id)

    async def update_template(
        self,
        template_id: str,
        updates: dict,
    ) -> WorkflowTemplate | None:
        """Update a template."""
        template = self._templates.get(template_id)
        if not template:
            return None

        for key, value in updates.items():
            if hasattr(template, key):
                setattr(template, key, value)

        template.updated_at = datetime.utcnow()
        return template

    async def delete_template(self, template_id: str) -> bool:
        """Delete a template."""
        if template_id.startswith("builtin_"):
            return False  # Cannot delete built-in templates
        return self._templates.pop(template_id, None) is not None

    # Template Discovery

    async def list_templates(
        self,
        category: TemplateCategory | None = None,
        visibility: TemplateVisibility | None = None,
        author_id: str | None = None,
        tags: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowTemplate]:
        """List templates with filters."""
        templates = list(self._templates.values())

        # Apply filters
        if category:
            templates = [t for t in templates if t.category == category]
        if visibility:
            templates = [t for t in templates if t.visibility == visibility]
        if author_id:
            templates = [t for t in templates if t.author_id == author_id]
        if tags:
            templates = [t for t in templates if any(tag in t.tags for tag in tags)]

        # Sort by usage and rating
        templates.sort(key=lambda t: (t.usage_count, t.rating), reverse=True)

        return templates[offset : offset + limit]

    async def search(
        self,
        query: str,
        category: TemplateCategory | None = None,
        limit: int = 20,
    ) -> list[WorkflowTemplate]:
        """Search templates by name, description, or tags."""
        query_lower = query.lower()
        results = []

        for template in self._templates.values():
            # Check category filter
            if category and template.category != category:
                continue

            # Check visibility
            if template.visibility == TemplateVisibility.PRIVATE:
                continue

            # Search in name, description, tags
            if (
                query_lower in template.name.lower()
                or query_lower in template.description.lower()
                or any(query_lower in tag.lower() for tag in template.tags)
            ):
                results.append(template)

        # Sort by relevance (name match first, then usage)
        results.sort(
            key=lambda t: (
                query_lower in t.name.lower(),
                t.usage_count,
            ),
            reverse=True,
        )

        return results[:limit]

    async def get_featured(self, limit: int = 10) -> list[WorkflowTemplate]:
        """Get featured/popular templates."""
        templates = [
            t
            for t in self._templates.values()
            if t.visibility == TemplateVisibility.PUBLIC
        ]
        templates.sort(key=lambda t: (t.rating, t.usage_count), reverse=True)
        return templates[:limit]

    async def get_by_category(
        self,
        category: TemplateCategory,
        limit: int = 20,
    ) -> list[WorkflowTemplate]:
        """Get templates by category."""
        return await self.list_templates(
            category=category,
            visibility=TemplateVisibility.PUBLIC,
            limit=limit,
        )

    # Template Instantiation

    async def instantiate(
        self,
        template_id: str,
        variables: dict,
        workflow_name: str | None = None,
    ) -> dict:
        """
        Instantiate a template with variable values.

        Returns a workflow definition ready to be saved.
        """
        template = self._templates.get(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        # Validate required variables
        for var in template.variables:
            if var.required and var.name not in variables:
                if var.default_value is not None:
                    variables[var.name] = var.default_value
                else:
                    raise ValueError(f"Missing required variable: {var.name}")

        # Deep copy nodes and edges
        nodes = json.loads(json.dumps(template.nodes))
        edges = json.loads(json.dumps(template.edges))
        config = json.loads(json.dumps(template.config))

        # Replace variables in nodes
        nodes = self._replace_variables(nodes, variables)
        config = self._replace_variables(config, variables)

        # Update usage count
        template.usage_count += 1

        return {
            "name": workflow_name or f"{template.name} (from template)",
            "description": f"Created from template: {template.name}",
            "nodes": nodes,
            "edges": edges,
            "config": config,
            "template_id": template_id,
            "template_version": template.version,
        }

    def _replace_variables(self, data: WorkflowValue, variables: dict[str, WorkflowValue]) -> WorkflowValue:
        """Recursively replace {{variable}} placeholders."""
        if isinstance(data, str):
            for name, value in variables.items():
                placeholder = "{{" + name + "}}"
                if placeholder in data:
                    if data == placeholder:
                        # Entire value is a placeholder
                        return value
                    else:
                        # Placeholder within string
                        data = data.replace(placeholder, str(value))
            return data
        elif isinstance(data, dict):
            return {k: self._replace_variables(v, variables) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._replace_variables(item, variables) for item in data]
        return data

    # Rating System

    async def rate_template(
        self,
        template_id: str,
        user_id: str,
        rating: float,
    ) -> bool:
        """Rate a template (1-5 stars)."""
        template = self._templates.get(template_id)
        if not template:
            return False

        if not 1 <= rating <= 5:
            return False

        # Update rating (simple average)
        total = template.rating * template.rating_count + rating
        template.rating_count += 1
        template.rating = total / template.rating_count

        return True

    # Statistics

    async def get_stats(self) -> dict:
        """Get template statistics."""
        templates = list(self._templates.values())
        public_templates = [
            t for t in templates if t.visibility == TemplateVisibility.PUBLIC
        ]

        by_category: dict[str, int] = {}
        for template in public_templates:
            cat = template.category.value
            by_category[cat] = by_category.get(cat, 0) + 1

        return {
            "total_templates": len(templates),
            "public_templates": len(public_templates),
            "builtin_templates": len(
                [t for t in templates if t.id.startswith("builtin_")]
            ),
            "by_category": by_category,
            "total_usage": sum(t.usage_count for t in templates),
        }


# Global template manager instance
_template_manager: TemplateManager | None = None


def get_template_manager() -> TemplateManager:
    """Get global template manager instance."""
    global _template_manager
    if _template_manager is None:
        _template_manager = TemplateManager()
    return _template_manager
