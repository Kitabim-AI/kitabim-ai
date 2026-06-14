"""
Knowledge Graph Job — extracts entities/relations from book chunks and indexes them in Neo4j.

Chunks are grouped into batches before being sent to the LLM. This reduces the number of API
calls (one per batch instead of one per chunk) and gives the model cross-chunk context so it
can resolve coreferences (e.g. 'the Khan' → 'Genghis Khan') across nearby text.

Only Entity nodes and Entity→Entity RELATED_TO edges are stored in Neo4j.
Chunk nodes are not stored — chunk text lives in Postgres and is retrieved via vector search.

Batch size and concurrency are both configurable via system_configs:
  kg_chunk_batch_size     — chunks per LLM call (default 10, ~5 000 chars per call)
  kg_max_parallel_chunks  — concurrent batch calls in-flight at once (default 5)
"""

from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy import select, update

from app.core.config import settings
from app.db import session as db_session
from app.db.models import Book, Chunk
from app.db.repositories.graph_repository import GraphRepository
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.knowledge_graph_service import (
    KnowledgeExtraction,
    parse_and_clean_json_from_exception,
    EntityType,
)
from app.utils.observability import log_json

from google import genai
from google.genai import types

logger = logging.getLogger("app.worker.knowledge_graph_job")


def hijri_to_gregorian(year_hijri: int) -> int:
    """Convert a Hijri year to an approximate Gregorian year (±1 year accuracy)."""
    return round(year_hijri - (year_hijri / 33.7) + 622)


async def knowledge_graph_job(ctx, book_id: str) -> None:
    log_json(logger, logging.INFO, "knowledge graph job started", book_id=book_id)

    try:
        # 1. Fetch settings from PostgreSQL
        async with db_session.async_session_factory() as session:
            config_repo = SystemConfigsRepository(session)
            kg_enabled_val = await config_repo.get_value(
                "knowledge_graph_enabled", "false"
            )
            if kg_enabled_val != "true":
                await session.execute(
                    update(Book)
                    .where(Book.id == book_id)
                    .values(graph_milestone="idle")
                )
                await session.commit()
                log_json(
                    logger,
                    logging.WARNING,
                    "knowledge graph job skipped: feature is disabled via system_configs",
                    book_id=book_id,
                )
                return

            chat_model = await config_repo.get_value(
                "gemini_kg_extraction_model", "gemini-3.1-flash-lite"
            )
            max_parallel = int(
                await config_repo.get_value("kg_max_parallel_chunks", "5")
            )
            chunk_batch_size = int(
                await config_repo.get_value("kg_chunk_batch_size", "5")
            )

            result = await session.execute(select(Book).where(Book.id == book_id))
            book = result.scalar_one_or_none()
            if not book:
                log_json(
                    logger,
                    logging.WARNING,
                    "knowledge_graph_job: book not found",
                    book_id=book_id,
                )
                return

            # Load fictional categories and determine if this book is fictional
            fictional_categories_val = await config_repo.get_value(
                "fictional_categories",
                "رومان, تارىخىي رومان, بالىلار رومانى, ساتىرىك رومان, پەلسەپىۋىي رومان, پوۋېست, پوۋېستلار, تارىخىي پوۋېست, ھېكايىلەر, تارىخىي ھېكايىلەر, بالىلار ھېكايىلېرى, چۆچەكلەر, قىسسە, تارىخىي قىسسە, داستان, داستانلار, تارىخىي داستان, رىۋايەتلەر, مەسەللەر, لەتىپىلەر, يۇمۇرلار, شېئىرلار, سەھنە ئەسەرلېرى, كىنو سېنارىيىلىرى, fiction, novel, story, drama, poetry, fairytale, fable, play",
            )
            fictional_cats = [
                c.strip().lower()
                for c in fictional_categories_val.split(",")
                if c.strip()
            ]
            book_cats = [
                c.strip().lower() for c in (book.categories or []) if c.strip()
            ]
            is_fictional = any(c in fictional_cats for c in book_cats)
            log_json(
                logger,
                logging.INFO,
                "book classification determined",
                book_id=book_id,
                title=book.title,
                categories=book.categories,
                is_fictional=is_fictional,
            )

            # Fetch all chunks ordered so batches are contiguous pages of text
            result = await session.execute(
                select(Chunk)
                .where(Chunk.book_id == book_id)
                .order_by(Chunk.page_number, Chunk.chunk_index)
            )
            chunks = list(result.scalars().all())

        if not chunks:
            log_json(
                logger,
                logging.WARNING,
                "knowledge_graph_job: no chunks found for book — resetting milestone to idle",
                book_id=book_id,
            )
            async with db_session.async_session_factory() as session:
                await session.execute(
                    update(Book)
                    .where(Book.id == book_id)
                    .values(graph_milestone="idle")
                )
                await session.commit()
            return

        # 2. Check API key
        api_key = settings.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY settings configuration is not set")

        # 3. Connect to Neo4j, clear stale data, then initialise
        graph_repo = GraphRepository()
        try:
            await graph_repo.delete_book_graph(book_id)
            log_json(
                logger,
                logging.INFO,
                "cleared existing graph data for book",
                book_id=book_id,
            )
            await graph_repo.init_constraints()

            # 4. Initialize GenAI client
            client = genai.Client(api_key=api_key)

            # 5. Group consecutive chunks into batches and process concurrently.
            #    Sending N chunks per call instead of 1:
            #      - cuts LLM calls by chunk_batch_size×
            #      - lets the model resolve coreferences across chunk boundaries
            batches = [
                chunks[i : i + chunk_batch_size]
                for i in range(0, len(chunks), chunk_batch_size)
            ]
            semaphore = asyncio.Semaphore(max_parallel)

            async def extract_batch(
                batch: list[Chunk],
            ) -> tuple[list[Chunk], KnowledgeExtraction | None]:
                async with semaphore:
                    chunks_with_text = [c for c in batch if c.text]
                    if not chunks_with_text:
                        return batch, None

                    # Combine texts with page labels so the LLM has positional context
                    combined_text = "\n\n---\n\n".join(
                        f"[Page {c.page_number}, Part {idx + 1}]\n{c.text}"
                        for idx, c in enumerate(chunks_with_text)
                    )

                    prompt = (
                        "You are an expert historical analyst and librarian. Read the following text chunks "
                        "from a book and extract key entities (persons, locations, events, eras, organizations, concepts) "
                        "and the directed relationships between them across ALL chunks. Resolve coreferences "
                        "(e.g. 'the Khan', 'he', 'the ruler') to their canonical entity names.\n\n"
                        "Language Guideline:\n"
                        "- Extract all entity names (persons, locations, events, etc.) strictly in their original "
                        "Uyghur Perso-Arabic script as they appear in the text. Do NOT translate or transliterate "
                        "names to English or Latin characters (e.g., use 'نۇھ' instead of 'Nuh', and 'ياپەس' instead of 'Yafes').\n"
                        "- Relation types must be in English, ALL_CAPS, underscore-separated "
                        "(e.g. SON_OF, CONQUERED, ALLIED_WITH, FOUGHT_IN). Never use Uyghur or other languages for relation types.\n\n"
                        "Important Kinship/Relationship Guideline:\n"
                        "- In Uyghur historical texts, terms of endearment or lineage like 'قوزىچىسى' or 'نەۋرىسى' "
                        "refer to a grandchild (e.g., GRANDSON_OF or GRANDCHILD_OF), NOT a direct child (e.g., SON_OF).\n"
                        "- Verify and extract the exact kinship relationship using this rule.\n\n"
                        "Military/Political Guideline:\n"
                        "- Extract explicit military and political actions as directed relationship edges, not just as event nodes.\n"
                        "- Examples: CONQUERED, DEFEATED, FOUGHT_IN, ALLIED_WITH, LED_ARMY, FLED_FROM, FLED_TO, RULED, CAPTURED, SERVED, PLEDGED_ALLEGIANCE_TO.\n"
                        "- When a person performs a military action against a location or another person, "
                        "create a relationship edge — do NOT only record it as an event node.\n\n"
                        "Year/Date Guideline:\n"
                        "- If the text mentions a specific Hijri year (ھىجرىيە، ھ) for an event or relationship, extract it as an integer in the year_hijri field.\n"
                        "- If the text mentions a Gregorian century (e.g. '15th century', '15-ئەسىر CE') without a specific Hijri year, extract it as an integer in the century_gregorian field (e.g. 15 for 15th century).\n"
                        "- Do NOT set both year_hijri and century_gregorian on the same entity/relation.\n"
                        "- Do NOT embed years or centuries inside entity names — store the name cleanly (e.g. 'ئىسان بۇغاخاننىڭ ۋاپاتى', not 'ئىسان بۇغاخاننىڭ ۋاپاتى (ھىجرىيە 866-يىلى)').\n\n"
                        f"Text Chunks:\n{combined_text}"
                    )

                    extraction = None
                    raw_text = None
                    try:
                        response = await client.aio.models.generate_content(
                            model=chat_model,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                response_schema=KnowledgeExtraction,
                                temperature=0.0,
                            ),
                        )
                        raw_text = response.text
                        extraction = KnowledgeExtraction.model_validate_json(raw_text)
                    except Exception as e:
                        # Attempt to parse and clean data from the raw text or exception if validation failed
                        text_to_parse = raw_text if raw_text else str(e)
                        extraction = parse_and_clean_json_from_exception(
                            ValueError(text_to_parse), KnowledgeExtraction
                        )
                        if extraction:
                            log_json(
                                logger,
                                logging.INFO,
                                "recovered from output parsing validation error using fallback parser",
                                book_id=book_id,
                                chunk_ids=[c.id for c in batch],
                                error=str(e),
                            )
                        else:
                            log_json(
                                logger,
                                logging.WARNING,
                                "failed to extract/index chunk batch",
                                book_id=book_id,
                                chunk_ids=[c.id for c in batch],
                                error=str(e),
                            )
                    return batch, extraction

            # Run parallel LLM extractions
            tasks = [extract_batch(batch) for batch in batches]
            results = await asyncio.gather(*tasks)

            # 6. Accumulate all entities and relations across all batches, then write
            #    to Neo4j in exactly 2 round-trips (upsert + connect) instead of 2×N.
            #    Entity names are deduplicated — the same historical figure appears in
            #    many batches and Neo4j MERGE handles it, but sending 1 entry is cheaper.
            seen_entity_names: set[str] = set()
            all_entities: list[dict] = []
            all_relations: list[dict] = []

            base_title = re.sub(r"[\s-]+\d+\s*$", "", book.title or "").strip()

            # Helper to namespace Person entity names for fictional books
            def get_display_name(name: str, etype: EntityType | str | None) -> str:
                if not name:
                    return ""
                is_person = False
                if isinstance(etype, EntityType) and etype == EntityType.PERSON:
                    is_person = True
                elif isinstance(etype, str) and etype.strip().lower() == "person":
                    is_person = True

                if is_fictional and is_person:
                    return f"{name} ({base_title})"
                return name

            for batch, extraction in results:
                if not extraction:
                    continue

                chunks_with_text = [c for c in batch if c.text]
                if not chunks_with_text:
                    continue

                # Map entity name -> type in this extraction batch
                entity_types = {
                    e.name.strip(): e.type
                    for e in extraction.entities
                    if e.name and e.type
                }

                for entity in extraction.entities:
                    name = entity.name.strip() if entity.name else ""
                    if not name:
                        continue
                    etype = entity.type
                    display_name = get_display_name(name, etype)
                    if display_name in seen_entity_names:
                        continue
                    seen_entity_names.add(display_name)
                    entity_data: dict = {
                        "name": display_name,
                        "type": etype.value
                        if isinstance(etype, EntityType)
                        else (etype if etype else EntityType.OTHER.value),
                        "subtype": entity.subtype,
                    }
                    if entity.year_hijri:
                        entity_data["year_hijri"] = entity.year_hijri
                        entity_data["year_gregorian"] = hijri_to_gregorian(
                            entity.year_hijri
                        )
                    elif entity.century_gregorian:
                        entity_data["century_gregorian"] = entity.century_gregorian
                    all_entities.append(entity_data)

                # Ensure relation endpoints exist as entities (fallback to Concept type)
                for rel in extraction.relations:
                    src = rel.source_entity.strip() if rel.source_entity else ""
                    tgt = rel.target_entity.strip() if rel.target_entity else ""

                    src_type = entity_types.get(src)
                    tgt_type = entity_types.get(tgt)

                    src_display = get_display_name(src, src_type)
                    tgt_display = get_display_name(tgt, tgt_type)

                    for raw_name, display_name, etype in [
                        (src, src_display, src_type),
                        (tgt, tgt_display, tgt_type),
                    ]:
                        if display_name and display_name not in seen_entity_names:
                            seen_entity_names.add(display_name)
                            all_entities.append(
                                {
                                    "name": display_name,
                                    "type": etype.value
                                    if isinstance(etype, EntityType)
                                    else (etype if etype else "Concept"),
                                    "subtype": "Auto-extracted from relation",
                                }
                            )

                    rtype = rel.relation_type.strip() if rel.relation_type else ""
                    if not src_display or not tgt_display or not rtype:
                        continue
                    relation_data: dict = {
                        "source_name": src_display,
                        "rel_type": rtype,
                        "target_name": tgt_display,
                        "book_id": str(book_id),
                    }
                    if rel.year_hijri:
                        relation_data["year_hijri"] = rel.year_hijri
                        relation_data["year_gregorian"] = hijri_to_gregorian(
                            rel.year_hijri
                        )
                    elif rel.century_gregorian:
                        relation_data["century_gregorian"] = rel.century_gregorian
                    all_relations.append(relation_data)

            # Single bulk write: 2 Neo4j round-trips for the entire book
            save_errors = 0
            try:
                if all_entities:
                    await graph_repo.upsert_entities_bulk(all_entities)
                if all_relations:
                    await graph_repo.connect_entities_bulk(all_relations)
                log_json(
                    logger,
                    logging.INFO,
                    "Neo4j bulk write complete",
                    book_id=book_id,
                    entities=len(all_entities),
                    relations=len(all_relations),
                )
            except Exception as save_exc:
                save_errors += 1
                log_json(
                    logger,
                    logging.ERROR,
                    "failed to save entities/relations to Neo4j",
                    book_id=book_id,
                    error=str(save_exc),
                )

        finally:
            await graph_repo.close()

        # Update database status — 'partial' if any batch saves failed, 'complete' otherwise
        final_milestone = "partial" if save_errors > 0 else "complete"
        if save_errors > 0:
            log_json(
                logger,
                logging.WARNING,
                "knowledge graph job completed with batch save errors",
                book_id=book_id,
                save_errors=save_errors,
                milestone=final_milestone,
            )
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Book)
                .where(Book.id == book_id)
                .values(graph_milestone=final_milestone)
            )
            await session.commit()

        log_json(
            logger,
            logging.INFO,
            "knowledge graph job completed",
            book_id=book_id,
            chunk_count=len(chunks),
            batch_count=len(batches),
            batch_size=chunk_batch_size,
        )

    except Exception as exc:
        log_json(
            logger,
            logging.ERROR,
            "knowledge graph job failed",
            book_id=book_id,
            error=str(exc),
        )
        # Update database status to failed
        try:
            async with db_session.async_session_factory() as session:
                await session.execute(
                    update(Book)
                    .where(Book.id == book_id)
                    .values(graph_milestone="failed")
                )
                await session.commit()
        except Exception as db_exc:
            log_json(
                logger,
                logging.ERROR,
                "failed to update book graph_milestone to failed in exception handler",
                book_id=book_id,
                error=str(db_exc),
            )
        raise
