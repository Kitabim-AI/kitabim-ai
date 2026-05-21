"""Shared Pydantic schemas for knowledge-graph entity and relation extraction.

Both ``knowledge_graph_job`` (chunk-level) and ``summary_job`` (book-level)
import from here so the schemas stay in sync.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    PERSON = "Person"
    LOCATION = "Location"
    EVENT = "Event"
    ORGANIZATION = "Organization"
    ERA = "HistoricalEra"
    CONCEPT = "Concept"
    OTHER = "Other"


class ExtractedEntity(BaseModel):
    name: str = Field(description="The standard name of the person, place, event, era or concept")
    type: EntityType = Field(description="The primary category of the entity")
    subtype: Optional[str] = Field(None, description="Optional subtype (e.g. 'City' for Location, 'Sultan' for Person)")


# ── Chunk-level extraction (used by knowledge_graph_job) ─────────────────────

class ExtractedRelation(BaseModel):
    source_entity: str = Field(description="Name of the source entity")
    relation_type: str = Field(description="The type of relationship (e.g., LIVED_IN, PART_OF, INFLUENCED, BORN_IN, SON_OF)")
    target_entity: str = Field(description="Name of the target entity")


class KnowledgeExtraction(BaseModel):
    entities: List[ExtractedEntity] = Field(default_factory=list, description="List of unique entities found in the text")
    relations: List[ExtractedRelation] = Field(default_factory=list, description="List of directed relationships between the found entities")


# ── Book-level extraction (used by summary_job) ───────────────────────────────

class GlobalRelation(BaseModel):
    source: str = Field(description="Name of the source entity (can be the book title itself, or a character/concept name)")
    relation: str = Field(description="Relationship type (e.g. HAS_THEME, HAS_CHARACTER, SET_IN, SON_OF, INFLUENCED, LIVED_IN)")
    target: str = Field(description="Name of the target entity")
    target_type: EntityType = Field(description="The primary category of the target entity")


class GlobalMetadataExtraction(BaseModel):
    entities: List[ExtractedEntity] = Field(default_factory=list, description="Main characters, primary locations, or core themes/concepts")
    relations: List[GlobalRelation] = Field(default_factory=list, description="Relationships connecting the book title or entities")
