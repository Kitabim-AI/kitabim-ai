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

    @classmethod
    def _missing_(cls, value: object) -> EntityType | None:
        if not isinstance(value, str):
            return None
        val = value.strip().lower()
        if val in ("person", "persons", "character", "characters", "author", "authors"):
            return cls.PERSON
        if val in (
            "location",
            "locations",
            "place",
            "places",
            "city",
            "cities",
            "country",
            "countries",
        ):
            return cls.LOCATION
        if val in ("event", "events"):
            return cls.EVENT
        if val in (
            "organization",
            "organizations",
            "kingdom",
            "kingdoms",
            "state",
            "states",
            "dynasty",
            "dynasties",
        ):
            return cls.ORGANIZATION
        if val in (
            "historicalera",
            "era",
            "eras",
            "timeperiod",
            "historical era",
            "historical_era",
        ):
            return cls.ERA
        if val in ("concept", "concepts", "theme", "themes", "book", "books"):
            return cls.CONCEPT
        if val in ("other", "others"):
            return cls.OTHER

        for member in cls:
            if member.value.lower() == val:
                return member
        return None


class ExtractedEntity(BaseModel):
    name: Optional[str] = Field(
        None,
        description="The standard name of the person, place, event, era or concept",
    )
    type: Optional[EntityType] = Field(
        None, description="The primary category of the entity"
    )
    subtype: Optional[str] = Field(
        None,
        description="Optional subtype (e.g. 'City' for Location, 'Sultan' for Person)",
    )


# ── Chunk-level extraction (used by knowledge_graph_job) ─────────────────────


class ExtractedRelation(BaseModel):
    source_entity: Optional[str] = Field(None, description="Name of the source entity")
    relation_type: Optional[str] = Field(
        None,
        description="The type of relationship (e.g., LIVED_IN, PART_OF, INFLUENCED, BORN_IN, SON_OF)",
    )
    target_entity: Optional[str] = Field(None, description="Name of the target entity")


class KnowledgeExtraction(BaseModel):
    entities: List[ExtractedEntity] = Field(
        default_factory=list, description="List of unique entities found in the text"
    )
    relations: List[ExtractedRelation] = Field(
        default_factory=list,
        description="List of directed relationships between the found entities",
    )


# ── Book-level extraction (used by summary_job) ───────────────────────────────


class GlobalRelation(BaseModel):
    source: Optional[str] = Field(
        None,
        description="Name of the source entity (can be the book title itself, or a character/concept name)",
    )
    relation: Optional[str] = Field(
        None,
        description="Relationship type (e.g. HAS_THEME, HAS_CHARACTER, SET_IN, SON_OF, INFLUENCED, LIVED_IN)",
    )
    target: Optional[str] = Field(None, description="Name of the target entity")
    target_type: Optional[EntityType] = Field(
        None, description="The primary category of the target entity"
    )


class GlobalMetadataExtraction(BaseModel):
    entities: List[ExtractedEntity] = Field(
        default_factory=list,
        description="Main characters, primary locations, or core themes/concepts",
    )
    relations: List[GlobalRelation] = Field(
        default_factory=list,
        description="Relationships connecting the book title or entities",
    )


import json


def _extract_json_by_braces(text: str) -> str | None:
    first_brace = text.find("{")
    if first_brace == -1:
        return None

    count = 0
    in_string = False
    escape = False

    for i in range(first_brace, len(text)):
        char = text[i]

        if escape:
            escape = False
            continue

        if char == "\\":
            escape = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if not in_string:
            if char == "{":
                count += 1
            elif char == "}":
                count -= 1
                if count == 0:
                    return text[first_brace : i + 1]

    return None


def parse_and_clean_json_from_exception(
    exc: Exception, model_class: type[BaseModel]
) -> BaseModel | None:
    """Attempts to extract a JSON string from a Pydantic validation parsing failure,
    filter out any invalid/empty dictionary objects from its lists, and validate it.
    """
    exc_str = str(exc)

    json_str = _extract_json_by_braces(exc_str)
    if not json_str:
        return None

    try:
        data = json.loads(json_str)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    # Filter out empty or incomplete items from lists
    # Clean 'entities'
    if "entities" in data and isinstance(data["entities"], list):
        cleaned_entities = []
        for item in data["entities"]:
            if isinstance(item, dict):
                # An entity needs name and type
                name = item.get("name")
                etype = item.get("type")
                if name and etype:
                    cleaned_entities.append(item)
        data["entities"] = cleaned_entities

    # Clean 'relations'
    if "relations" in data and isinstance(data["relations"], list):
        cleaned_relations = []
        for item in data["relations"]:
            if isinstance(item, dict):
                # For chunk-level ExtractedRelation: source_entity, relation_type, target_entity
                # For book-level GlobalRelation: source, relation, target, target_type
                if model_class.__name__ == "KnowledgeExtraction":
                    if (
                        item.get("source_entity")
                        and item.get("relation_type")
                        and item.get("target_entity")
                    ):
                        cleaned_relations.append(item)
                elif model_class.__name__ == "GlobalMetadataExtraction":
                    if (
                        item.get("source")
                        and item.get("relation")
                        and item.get("target")
                        and item.get("target_type")
                    ):
                        cleaned_relations.append(item)
        data["relations"] = cleaned_relations

    try:
        return model_class.model_validate(data)
    except Exception:
        return None
