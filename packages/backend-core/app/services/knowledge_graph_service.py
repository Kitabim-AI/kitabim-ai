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
    local_id: str = Field(
        ...,
        description="Unique key for this entity within this response, e.g. 'e1'. Referenced by relations. "
        "If two mentions could refer to different people who happen to share a name (different roles, "
        "no stated family/era connection), emit them as separate entity objects, each with its own "
        "local_id and context_summary — do not force them together. A global resolution pass, not this "
        "extraction step, makes the final same/different call.",
    )
    name: Optional[str] = Field(
        None,
        description="The standard name of the person, place, event, era or concept — do NOT embed years in the name",
    )
    type: Optional[EntityType] = Field(
        None, description="The primary category of the entity"
    )
    subtype: Optional[str] = Field(
        None,
        description="Optional subtype (e.g. 'City' for Location, 'Sultan' for Person)",
    )
    year_hijri: Optional[int] = Field(
        None,
        description="For Person: birth year. For Event/Era: the event/era year. Use only when a specific Hijri year is stated.",
    )
    century_gregorian: Optional[int] = Field(
        None,
        description="Gregorian century associated with this entity (e.g. 15 for 15th century CE). Use only when a Gregorian century is stated but no specific Hijri year.",
    )
    context_summary: Optional[str] = Field(
        None,
        description="Brief context to help the global resolution pass — role, era, key relationships "
        "(e.g. 'son of Ibrahim, governor of Kashgar').",
    )


# ── Chunk-level extraction (used by knowledge_graph_job) ─────────────────────


class ExtractedRelation(BaseModel):
    source_entity: Optional[str] = Field(
        None,
        description="local_id of the source entity (see ExtractedEntity.local_id), not its name",
    )
    relation_type: Optional[str] = Field(
        None,
        description="The specific directed relationship type in UPPER_SNAKE_CASE (e.g. SON_OF, DAUGHTER_OF, "
        "FATHER_OF, MOTHER_OF, BROTHER_OF, SISTER_OF, UNCLE_OF, GRANDSON_OF, SPOUSE_OF, BORN_IN, DIED_IN, "
        "LIVED_IN, CONQUERED, RULED, GOVERNED, SUCCEEDED, STUDIED_UNDER).",
    )
    target_entity: Optional[str] = Field(
        None,
        description="local_id of the target entity (see ExtractedEntity.local_id), not its name",
    )
    parent_role: Optional[str] = Field(
        None,
        description="'father' or 'mother' — only set when relation_type is CHILD_OF",
    )
    year_hijri: Optional[int] = Field(
        None,
        description="Hijri year when this relationship occurred. Use only when a specific Hijri year is stated.",
    )
    century_gregorian: Optional[int] = Field(
        None,
        description="Gregorian century when this relationship occurred (e.g. 15 for 15th century CE). Use only when a Gregorian century is stated but no specific Hijri year.",
    )
    evidence: Optional[str] = Field(
        None,
        description="The exact phrase or sentence fragment from the text supporting this relationship extraction. Required for auditing and filtering figurative kinship claims.",
    )


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
                # An entity needs local_id (required by the schema), name, and type
                local_id = item.get("local_id")
                name = item.get("name")
                etype = item.get("type")
                if local_id and name and etype:
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
