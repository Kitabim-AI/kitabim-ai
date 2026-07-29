from app.services.knowledge_graph_service import (
    KnowledgeExtraction,
    GlobalMetadataExtraction,
    parse_and_clean_json_from_exception,
    EntityType,
)


def test_parse_and_clean_knowledge_extraction_success():
    # Simulate a validation exception message containing the raw JSON with an empty dict at the end of relations
    error_message = (
        "Failed to parse KnowledgeExtraction from completion {\n"
        '  "entities": [\n'
        '    {"local_id": "e1", "name": "Nuh", "type": "Person", "subtype": "Prophet"},\n'
        '    {"local_id": "e2", "name": "Yafes", "type": "Person", "subtype": "Son of Nuh"}\n'
        "  ],\n"
        '  "relations": [\n'
        '    {"source_entity": "e2", "relation_type": "SON_OF", "target_entity": "e1"},\n'
        "    {}\n"
        "  ]\n"
        "}. Got: 3 validation errors for KnowledgeExtraction\n"
        "relations.1.source_entity\n"
        "  Field required [type=missing, input_value={}, input_type=dict]"
    )

    exc = ValueError(error_message)

    parsed = parse_and_clean_json_from_exception(exc, KnowledgeExtraction)

    assert parsed is not None
    assert len(parsed.entities) == 2
    assert parsed.entities[0].name == "Nuh"
    assert parsed.entities[1].name == "Yafes"

    # The empty dict in relations should have been filtered out, leaving exactly 1 valid relation
    assert len(parsed.relations) == 1
    assert parsed.relations[0].source_entity == "e2"
    assert parsed.relations[0].relation_type == "SON_OF"
    assert parsed.relations[0].target_entity == "e1"


def test_parse_and_clean_global_metadata_success():
    error_message = (
        "Failed to parse GlobalMetadataExtraction from completion {\n"
        '  "entities": [\n'
        '    {"local_id": "e1", "name": "Moghul", "type": "Person", "subtype": "Son of Alanje"},\n'
        '    {"local_id": "e2", "name": "", "type": "Person"}\n'  # empty name
        "  ],\n"
        '  "relations": [\n'
        '    {"source": "Book Title", "relation": "HAS_CHARACTER", "target": "Moghul", "target_type": "Person"},\n'
        '    {"source": "", "relation": "", "target": ""}\n'  # incomplete relation
        "  ]\n"
        "}. Got: validation errors..."
    )

    exc = ValueError(error_message)

    parsed = parse_and_clean_json_from_exception(exc, GlobalMetadataExtraction)

    assert parsed is not None
    # Empty name entity should be filtered out
    assert len(parsed.entities) == 1
    assert parsed.entities[0].name == "Moghul"

    # Incomplete relation should be filtered out
    assert len(parsed.relations) == 1
    assert parsed.relations[0].source == "Book Title"
    assert parsed.relations[0].relation == "HAS_CHARACTER"
    assert parsed.relations[0].target == "Moghul"


def test_parse_and_clean_invalid_json():
    # If the exception has no JSON pattern
    exc = ValueError("Some other internal Google API error occurred")
    parsed = parse_and_clean_json_from_exception(exc, KnowledgeExtraction)
    assert parsed is None

    # If the JSON is completely broken/unparseable
    exc = ValueError(
        "Failed to parse from completion {entities: [broken json"
    ).with_traceback(None)
    parsed = parse_and_clean_json_from_exception(exc, KnowledgeExtraction)
    assert parsed is None


def test_entity_type_normalization_variations():
    # Test direct validation of EntityType enum
    from app.services.knowledge_graph_service import EntityType

    assert EntityType("person") == EntityType.PERSON
    assert EntityType("PERSONS") == EntityType.PERSON
    assert EntityType("character") == EntityType.PERSON

    assert EntityType("location") == EntityType.LOCATION
    assert EntityType("cities") == EntityType.LOCATION

    assert EntityType("historical era") == EntityType.ERA
    assert EntityType("Historical_Era") == EntityType.ERA
    assert EntityType("era") == EntityType.ERA

    assert EntityType("kingdom") == EntityType.ORGANIZATION
    assert EntityType("dynasty") == EntityType.ORGANIZATION

    assert EntityType("theme") == EntityType.CONCEPT
    assert EntityType("concepts") == EntityType.CONCEPT

    # Test validation of entities with variations through parse_and_clean_json_from_exception
    error_message = (
        "Failed to parse KnowledgeExtraction from completion {\n"
        '  "entities": [\n'
        '    {"local_id": "e1", "name": "Nuh", "type": "person", "subtype": "Prophet"},\n'
        '    {"local_id": "e2", "name": "Yafes", "type": "historical era", "subtype": "Era Setting"},\n'
        '    {"local_id": "e3", "name": "Kashgar", "type": "cities"}\n'
        "  ],\n"
        '  "relations": []\n'
        "}. Got: validation errors..."
    )
    exc = ValueError(error_message)
    parsed = parse_and_clean_json_from_exception(exc, KnowledgeExtraction)
    assert parsed is not None
    assert len(parsed.entities) == 3
    assert parsed.entities[0].type == EntityType.PERSON
    assert parsed.entities[1].type == EntityType.ERA
    assert parsed.entities[2].type == EntityType.LOCATION


def test_optional_fields_parsing():
    # Test that KnowledgeExtraction validates successfully when fields are omitted or None
    raw_data = {
        "entities": [
            {"local_id": "e1", "name": "Nuh"},  # type is missing (None)
            {"local_id": "e2", "type": "Person"},  # name is missing (None)
            {
                "local_id": "e3",
                "name": "Yafes",
                "type": None,
            },  # type is explicitly None
        ],
        "relations": [
            {"source_entity": "Yafes"},  # relation_type and target_entity are missing
            {
                "source_entity": "Yafes",
                "relation_type": "SON_OF",
                "target_entity": None,
            },  # target_entity is None
        ],
    }

    parsed = KnowledgeExtraction.model_validate(raw_data)
    assert parsed is not None

    assert len(parsed.entities) == 3
    assert parsed.entities[0].name == "Nuh"
    assert parsed.entities[0].type is None
    assert parsed.entities[1].name is None
    assert parsed.entities[1].type == EntityType.PERSON

    assert len(parsed.relations) == 2
    assert parsed.relations[0].source_entity == "Yafes"
    assert parsed.relations[0].relation_type is None
    assert parsed.relations[0].target_entity is None
    assert parsed.relations[1].target_entity is None
