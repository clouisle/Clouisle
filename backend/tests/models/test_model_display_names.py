"""Human-readable model representation coverage."""

from uuid import uuid4

from app.models.agent import Agent
from app.models.api_key import APIKey
from app.models.knowledge_base import KnowledgeBase
from app.models.memory import EntityType, MemoryEntity, MemoryRelation, RelationType
from app.models.workflow import Workflow


def test_named_resources_render_their_names():
    assert str(Agent(name="Support assistant")) == "Support assistant"
    assert str(KnowledgeBase(name="Operations")) == "Operations"
    assert str(Workflow(name="Incident triage")) == "Incident triage"


def test_api_key_rendering_exposes_only_its_saved_prefix():
    key = APIKey(name="Automation", key_prefix="clou_abcd123")

    assert str(key) == "Automation (clou_abcd123...)"


def test_memory_graph_items_render_contextual_labels():
    source_id = uuid4()
    target_id = uuid4()
    entity = MemoryEntity(name="Python", entity_type=EntityType.SKILL)
    relation = MemoryRelation(relation_type=RelationType.USES)
    relation.source_entity_id = source_id
    relation.target_entity_id = target_id

    assert str(entity) == "Python (EntityType.SKILL)"
    assert str(relation) == (
        f"{source_id} --[RelationType.USES]--> {target_id}"
    )
