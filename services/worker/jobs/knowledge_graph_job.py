"""
Knowledge Graph Job — extracts entities/relations from book chunks and indexes them in Neo4j.

Chunks are grouped into batches before being sent to the LLM. This reduces the number of API
calls (one per batch instead of one per chunk) and gives the model cross-chunk context so it
can resolve coreferences (e.g. 'the Khan' → 'Genghis Khan') across nearby text — but only
*within* one batch's single LLM call. The LLM expresses that coreference resolution by reusing
the same `local_id` for the same person across entities in one response; it does NOT attempt to
deduplicate an entity across different batches or across books. Identity is assigned here in
Python (`id = uuid4()`) purely by extraction position — there is no dedup at write time.
Cross-batch/cross-book duplicates (including within the same book) are entirely the job of the
global resolution pass (`graph_resolution_job`), which has strictly more context than a single
chunk-batch LLM call ever could.

Only Entity nodes and Entity→Entity RELATED_TO edges are stored in Neo4j.
Chunk nodes are not stored — chunk text lives in Postgres and is retrieved via vector search.

`scope` ("fiction" | "nonfiction") is a required parameter, supplied by the admin at the moment
they trigger `POST /{book_id}/reprocess/graph` — see design v2 §3 for why no automatic
classification is needed.

Batch size and concurrency are both configurable via system_configs:
  kg_chunk_batch_size     — chunks per LLM call (default 10, ~5 000 chars per call)
  kg_max_parallel_chunks  — concurrent batch calls in-flight at once (default 5)
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy import select, update

from app.core.config import settings
from app.core.providers import get_embedding_provider
from app.db import session as db_session
from app.db.models import Book, Chunk
from app.db.repositories.graph_repository import GraphRepository
from app.db.repositories.graph_resolution_repository import (
    GraphResolutionQueueRepository,
)
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.entity_resolution_service import embed_and_store_entity_profiles
from app.services.knowledge_graph_service import (
    KnowledgeExtraction,
    parse_and_clean_json_from_exception,
    EntityType,
)
from app.utils.observability import log_json

from google import genai
from google.genai import types

logger = logging.getLogger("app.worker.knowledge_graph_job")

VALID_SCOPES = {"fiction", "nonfiction"}


def hijri_to_gregorian(year_hijri: int) -> int:
    """Convert a Hijri year to an approximate Gregorian year (±1 year accuracy)."""
    return round(year_hijri - (year_hijri / 33.7) + 622)


def _chunk_ref(book_id: str, chunk: Chunk) -> str:
    return f"{book_id}:{chunk.page_number}:{chunk.chunk_index}"


async def _maybe_embed_entity_profiles(
    graph_repo: GraphRepository, entities: list[dict], book_id: str
) -> None:
    """Embeds and stores entity profile vectors (Item 8,
    knowledge-graph-improvement-backlog.md) when entity_semantic_matching_enabled is
    on. Never raises — an embedding failure must not fail the graph write that
    already succeeded by the time this is called; it's an optional signal for the
    resolution pass, not a requirement for extraction.
    """
    if not entities:
        return
    try:
        async with db_session.async_session_factory() as config_session:
            config_repo = SystemConfigsRepository(config_session)
            semantic_enabled = (
                await config_repo.get_value("entity_semantic_matching_enabled", "false")
            ).strip().lower() == "true"
            if not semantic_enabled:
                return
            gemini_embedding_model = await config_repo.get_value(
                "gemini_embedding_model"
            )
        if not gemini_embedding_model:
            raise RuntimeError("system_config 'gemini_embedding_model' is not set")
        embeddings_model = get_embedding_provider(gemini_embedding_model)
        await embed_and_store_entity_profiles(graph_repo, entities, embeddings_model)
    except Exception as embed_exc:
        log_json(
            logger,
            logging.WARNING,
            "entity profile embedding failed — resolution will fall back to lexical matching only",
            book_id=book_id,
            error=str(embed_exc),
        )


async def knowledge_graph_job(ctx, book_id: str, scope: str) -> None:
    log_json(
        logger,
        logging.INFO,
        "knowledge graph job started",
        book_id=book_id,
        scope=scope,
    )

    if scope not in VALID_SCOPES:
        raise ValueError(
            f"knowledge_graph_job: invalid scope '{scope}', expected one of {VALID_SCOPES}"
        )

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
            #      - lets the model resolve coreferences across chunk boundaries (within
            #        this one call only — see module docstring)
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
                        "(e.g. 'the Khan', 'he', 'the ruler') to the same entity's local_id.\n\n"
                        "Entity Identity Guideline:\n"
                        "- Assign each distinct entity a unique local_id (e.g. 'e1', 'e2') within this response. "
                        "Reuse the same local_id for every mention of the same entity in this text.\n"
                        "- If two mentions could refer to different people who happen to share a name (different "
                        "roles, no stated family/era connection), emit them as SEPARATE entity objects, each with "
                        "its own local_id. Do not force them together. When in doubt, keep them separate — a "
                        "global resolution pass, not this step, makes the final same/different call.\n"
                        "- Relations reference entities by local_id, not by name.\n\n"
                        "Language Guideline:\n"
                        "- Extract all entity names (persons, locations, events, etc.) strictly in their original "
                        "Uyghur Perso-Arabic script as they appear in the text. Do NOT translate or transliterate "
                        "names to English or Latin characters (e.g., use 'نۇھ' instead of 'Nuh', and 'ياپەس' instead of 'Yafes').\n"
                        "- Relation types must be in English, ALL_CAPS, underscore-separated "
                        "(e.g. SON_OF, DAUGHTER_OF, FATHER_OF, MOTHER_OF, BROTHER_OF, UNCLE_OF, GRANDSON_OF, "
                        "SPOUSE_OF, CONQUERED, RULED, SUCCEEDED, STUDIED_UNDER, BORN_IN, DIED_IN). Never use Uyghur or other languages for relation types.\n"
                        "- Always enforce precise directed edge semantics:\n"
                        "  * Son -> [SON_OF] -> Father/Mother\n"
                        "  * Daughter -> [DAUGHTER_OF] -> Father/Mother\n"
                        "  * Father -> [FATHER_OF] -> Son/Daughter\n"
                        "  * Mother -> [MOTHER_OF] -> Son/Daughter\n"
                        "  * Brother -> [BROTHER_OF] -> Sibling\n"
                        "  * Nephew -> [NEPHEW_OF] -> Uncle\n"
                        "  * Uncle -> [UNCLE_OF] -> Nephew\n"
                        "  * Person -> [CHILD_OF] -> Parent (only if gender is unspecified)\n"
                        "- In Uyghur historical texts: 'ئوغلى' = SON_OF, 'قىزى' = DAUGHTER_OF, 'ئاتىسى'/'فەدەر' = FATHER_OF, 'ئانىسى' = MOTHER_OF, 'ئىنىسى'/'ئاكىسى' = BROTHER_OF, 'تاغىسى'/'ئاممىسى' = UNCLE_OF, 'نەۋرىسى' = GRANDSON_OF.\n\n"
                        "Important Kinship/Relationship Guideline:\n"
                        "- In Uyghur historical texts, terms of endearment or lineage like 'قوزىچىسى' or 'نەۋرىسى' "
                        "refer to a grandchild (e.g., GRANDSON_OF or GRANDCHILD_OF), NOT a direct child (e.g., CHILD_OF).\n"
                        "- Verify and extract the exact kinship relationship using this rule.\n\n"
                        "Literal Kinship vs Figurative Language Guideline:\n"
                        "- Only emit kinship edges (SON_OF, FATHER_OF, CHILD_OF, DAUGHTER_OF, BROTHER_OF, etc.) for LITERAL biological, legal, or genealogical relationships.\n"
                        "- NEVER emit kinship edges for figurative, simile, metaphorical, honorific, or emotional expressions.\n"
                        "- Negative examples (do NOT emit kinship edge):\n"
                        "  * Simile/metaphor: 'loved me like a father', 'gave the love of a father', 'was a father to the orphans' -> NO edge\n"
                        "  * Honorific/epithet: 'father of the nation', 'father of medicine' -> NO edge\n"
                        "  * Spiritual/metaphorical: 'spiritual father', 'father of the movement' -> NO edge\n"
                        "  * Uyghur comparison markers: 'ئاتا / ئاتىسى' used figuratively with 'ئوخشاش', 'گويا', 'دەك' -> NO edge\n"
                        "- Precision over recall for relations: if unsure whether a relationship is literal biological kinship, do NOT emit the kinship edge.\n"
                        "- Always capture the exact supporting sentence fragment in the `evidence` field of ExtractedRelation.\n\n"
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
                        "Context Summary Guideline:\n"
                        "- For every extracted entity, especially Person entities, provide a brief `context_summary` from the text (e.g., 'son of Ibrahim, ruler of Kashgar', 'general under Abdurashid Khan') to help the global resolution pass later.\n\n"
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

            # 6. Assign identity by extraction position (id = uuid4()) — no cross-batch
            #    dedup here; that is entirely the global resolution pass's job.
            all_entities: list[dict] = []
            all_relations: list[dict] = []
            queue_rows: list[dict] = []
            fiction_book_id = str(book_id) if scope == "fiction" else None

            for batch_idx, (batch, extraction) in enumerate(results):
                if not extraction:
                    continue

                chunk_refs = [_chunk_ref(book_id, c) for c in batch if c.text]

                local_id_map: dict[str, str] = {}
                for ent in extraction.entities:
                    name = ent.name.strip() if ent.name else ""
                    if not name or not ent.local_id:
                        continue
                    entity_id = str(uuid.uuid4())
                    local_id_map[ent.local_id] = entity_id

                    etype = (
                        ent.type.value
                        if isinstance(ent.type, EntityType)
                        else (ent.type or EntityType.OTHER.value)
                    )
                    entity_data: dict = {
                        "id": entity_id,
                        "canonical_name": name,
                        "aliases": [name],
                        "type": etype,
                        "subtype": ent.subtype,
                        "context_summary": ent.context_summary,
                        "scope": scope,
                        "book_id": fiction_book_id,
                        "resolution_status": "unresolved",
                    }
                    if ent.year_hijri:
                        entity_data["year_hijri"] = ent.year_hijri
                        entity_data["year_gregorian"] = hijri_to_gregorian(
                            ent.year_hijri
                        )
                    elif ent.century_gregorian:
                        entity_data["century_gregorian"] = ent.century_gregorian
                    all_entities.append(entity_data)
                    queue_rows.append(
                        {
                            "entity_id": entity_id,
                            "scope": scope,
                            "book_id": fiction_book_id,
                            "sort_year": entity_data.get("year_hijri"),
                        }
                    )

                for rel in extraction.relations:
                    src_local = rel.source_entity
                    tgt_local = rel.target_entity
                    rtype = rel.relation_type.strip() if rel.relation_type else ""
                    if not src_local or not tgt_local or not rtype:
                        continue
                    src_id = local_id_map.get(src_local)
                    tgt_id = local_id_map.get(tgt_local)
                    if not src_id or not tgt_id:
                        # Relation references a local_id the LLM didn't also emit as an
                        # entity in this same response — nothing to resolve it to.
                        continue

                    relation_data: dict = {
                        "source_id": src_id,
                        "target_id": tgt_id,
                        "rel_type": rtype,
                        "book_id": str(book_id),
                        "chunk_refs": chunk_refs,
                    }
                    if rel.evidence:
                        relation_data["evidence"] = rel.evidence
                    if rtype == "CHILD_OF" and rel.parent_role:
                        relation_data["parent_role"] = rel.parent_role
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
                await _maybe_embed_entity_profiles(graph_repo, all_entities, book_id)
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

        # 7. Enqueue every newly created entity into the global resolution queue —
        #    both scopes get queued (fiction resolves within its book, non-fiction
        #    across the library — same queue, same job, parameterized by scope).
        if queue_rows and save_errors == 0:
            async with db_session.async_session_factory() as session:
                queue_repo = GraphResolutionQueueRepository(session)
                await queue_repo.bulk_enqueue(queue_rows)

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
            scope=scope,
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
