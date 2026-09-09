"""
Memory tools for LLM function calling.
Allows LLM to create and manage user memory entities and relations.
"""

from typing import Any

# Tool definitions for LLM function calling
CREATE_MEMORY_ENTITY_TOOL = {
    "name": "create_memory_entity",
    "description": "Create a new memory entity about the user. Use this when the user shares important information about themselves, their preferences, skills, projects, or goals. This helps personalize future conversations.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Entity name (e.g., 'Python', 'E-commerce Project', 'Google')",
            },
            "entity_type": {
                "type": "string",
                "enum": [
                    "person",
                    "preference",
                    "skill",
                    "project",
                    "goal",
                    "fact",
                    "concept",
                    "organization",
                    "location",
                    "custom",
                ],
                "description": "Type of entity: person (user or people they mention), preference (user preferences), skill (skills/technologies), project (projects/work), goal (goals/objectives), fact (general facts), concept (abstract concepts), organization (companies/teams), location (places), custom (other)",
            },
            "description": {
                "type": "string",
                "description": "Detailed description of the entity",
            },
            "properties": {
                "type": "object",
                "description": "Additional properties as key-value pairs (e.g., {'level': 'expert', 'years': 5})",
            },
        },
        "required": ["name", "entity_type"],
    },
}

CREATE_MEMORY_RELATION_TOOL = {
    "name": "create_memory_relation",
    "description": "Create a relation between two memory entities. Use this to connect related information and build a knowledge graph about the user.",
    "input_schema": {
        "type": "object",
        "properties": {
            "source_entity_name": {
                "type": "string",
                "description": "Name of source entity (must already exist)",
            },
            "target_entity_name": {
                "type": "string",
                "description": "Name of target entity (must already exist)",
            },
            "relation_type": {
                "type": "string",
                "enum": [
                    "prefers",
                    "works_on",
                    "knows",
                    "uses",
                    "works_at",
                    "located_in",
                    "has_goal",
                    "related_to",
                    "part_of",
                ],
                "description": "Type of relation: prefers (user prefers X), works_on (user works on X), knows (user knows X), uses (user uses X), works_at (user works at X), located_in (user/entity located in X), has_goal (user has goal X), related_to (generic relation), part_of (X is part of Y)",
            },
            "description": {
                "type": "string",
                "description": "Description of the relation",
            },
        },
        "required": ["source_entity_name", "target_entity_name", "relation_type"],
    },
}

UPDATE_MEMORY_ENTITY_TOOL = {
    "name": "update_memory_entity",
    "description": "Update an existing memory entity. Use this when the user provides new information about something you already know.",
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_name": {
                "type": "string",
                "description": "Name of entity to update",
            },
            "description": {
                "type": "string",
                "description": "New description (will be merged with existing)",
            },
            "properties": {
                "type": "object",
                "description": "Properties to update/add",
            },
        },
        "required": ["entity_name"],
    },
}

SEARCH_MEMORY_TOOL = {
    "name": "search_memory",
    "description": (
        "Search user's memory graph for relevant information. Use this to recall what you know about the user. "
        "Each result contains name, entity type, description, and the last updated date (updated_at). "
        "Optionally restrict the search to recent memories by specifying time_window_days."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query keywords",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5,
            },
            "time_window_days": {
                "type": "integer",
                "description": (
                    "Optional time filter in days (e.g., 7 for past week, 30 for past month, 365 for past year). "
                    "Only memories created or updated within this window will be returned."
                ),
            },
            "entity_type": {
                "type": "string",
                "enum": [
                    "person",
                    "preference",
                    "skill",
                    "project",
                    "goal",
                    "fact",
                    "concept",
                    "organization",
                    "location",
                    "custom",
                ],
                "description": "Optional memory entity type filter",
            },
        },
        "required": ["query"],
    },
}


GET_MEMORY_SUBGRAPH_TOOL = {
    "name": "get_memory_subgraph",
    "description": (
        "Read entities and relationships connected to memory nodes returned by search_memory. "
        "Use entity IDs from search_memory when available; exact entity names are also accepted. "
        "Use this when the answer depends on how the user's projects, skills, preferences, "
        "goals, or other memories are related. Do not infer relationships that are not returned."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "entity_ids": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 5,
                "description": "Entity IDs from search_memory (preferred), or exact entity names",
            },
            "max_depth": {
                "type": "integer",
                "minimum": 1,
                "maximum": 3,
                "default": 1,
                "description": "Graph traversal depth",
            },
            "direction": {
                "type": "string",
                "enum": ["incoming", "outgoing", "both"],
                "default": "both",
                "description": "Which relationship directions to follow",
            },
            "relation_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional relationship type filters",
            },
        },
        "required": ["entity_ids"],
    },
}


def get_memory_tools() -> list[dict[str, Any]]:
    """Get all memory tools for LLM function calling."""
    return [
        CREATE_MEMORY_ENTITY_TOOL,
        CREATE_MEMORY_RELATION_TOOL,
        UPDATE_MEMORY_ENTITY_TOOL,
        SEARCH_MEMORY_TOOL,
        GET_MEMORY_SUBGRAPH_TOOL,
    ]
