"""
Knowledge Graph Job — extracts entities/relations from book chunks and indexes them in Memgraph.

Chunks are grouped into batches before being sent to the LLM. This reduces the number of API
calls (one per batch instead of one per chunk) and gives the model cross-chunk context so it
can resolve coreferences (e.g. 'the Khan' → 'Genghis Khan') across nearby text.

Batch size and concurrency are both configurable via system_configs:
  kg_chunk_batch_size     — chunks per LLM call (default 10, ~5 000 chars per call)
  kg_max_parallel_chunks  — concurrent batch calls in-flight at once (default 5)
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.config import settings
from app.db import session as db_session
from app.db.models import Book, Chunk
from app.db.repositories.graph import GraphRepository
from app.db.repositories.system_configs import SystemConfigsRepository
from app.services.knowledge_graph_service import KnowledgeExtraction, parse_and_clean_json_from_exception, EntityType
from app.utils.observability import log_json

from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger("app.worker.knowledge_graph_job")


async def knowledge_graph_job(ctx, book_id: str) -> None:
    log_json(logger, logging.INFO, "knowledge graph job started", book_id=book_id)

    try:
        # 1. Fetch settings from PostgreSQL
        async with db_session.async_session_factory() as session:
            config_repo = SystemConfigsRepository(session)
            chat_model = await config_repo.get_value("gemini_chat_model", "gemini-2.0-flash-lite")
            max_parallel = int(await config_repo.get_value("kg_max_parallel_chunks", "5"))
            chunk_batch_size = int(await config_repo.get_value("kg_chunk_batch_size", "5"))

            result = await session.execute(select(Book).where(Book.id == book_id))
            book = result.scalar_one_or_none()
            if not book:
                log_json(logger, logging.WARNING, "knowledge_graph_job: book not found", book_id=book_id)
                return

            # Fetch all chunks ordered so batches are contiguous pages of text
            result = await session.execute(
                select(Chunk)
                .where(Chunk.book_id == book_id)
                .order_by(Chunk.page_number, Chunk.chunk_index)
            )
            chunks = list(result.scalars().all())

        if not chunks:
            log_json(logger, logging.WARNING, "knowledge_graph_job: no chunks found for book", book_id=book_id)
            return

        # 2. Check API key
        api_key = settings.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY settings configuration is not set")

        # 3. Connect to Memgraph & initialise
        graph_repo = GraphRepository()
        try:
            await graph_repo.init_constraints()

            # Idempotency: wipe existing chunk/relationship data for this book before rebuilding
            await graph_repo.clear_book_graph(book_id)
            log_json(logger, logging.INFO, "cleared existing graph data for book", book_id=book_id)

            # Book and Author nodes
            author_name = book.author or "Unknown Author"
            await graph_repo.upsert_book(book_id=str(book.id), title=book.title, author=author_name)
            await graph_repo.upsert_author(name=author_name)
            await graph_repo.connect_author_book(author_name=author_name, book_id=str(book.id))

            # 4. LLM with structured output
            llm = ChatGoogleGenerativeAI(
                model=chat_model,
                google_api_key=api_key,
                temperature=0.0,
            ).with_structured_output(KnowledgeExtraction)

            # 5. Bulk upsert all Chunk nodes and book→chunk edges upfront to establish graph structure
            chunks_bulk = []
            for chunk in chunks:
                text_preview = chunk.text[:100] + "..." if chunk.text else ""
                chunks_bulk.append({
                    "id": chunk.id,
                    "page_number": chunk.page_number,
                    "text_preview": text_preview,
                })
            await graph_repo.upsert_chunks_and_connect_bulk(str(book.id), chunks_bulk)

            # 6. Group consecutive chunks into batches and process concurrently.
            #    Sending N chunks per call instead of 1:
            #      - cuts LLM calls by chunk_batch_size×
            #      - lets the model resolve coreferences across chunk boundaries
            batches = [
                chunks[i : i + chunk_batch_size]
                for i in range(0, len(chunks), chunk_batch_size)
            ]
            semaphore = asyncio.Semaphore(max_parallel)

            async def extract_batch(batch: list[Chunk]) -> tuple[list[Chunk], KnowledgeExtraction | None]:
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
                        "names to English or Latin characters (e.g., use 'نۇھ' instead of 'Nuh', and 'ياپەس' instead of 'Yafes').\n\n"
                        "Important Kinship/Relationship Guideline:\n"
                        "- In Uyghur historical texts, terms of endearment or lineage like 'قوزىچىسى' or 'نەۋرىسى' "
                        "refer to a grandchild (e.g., GRANDSON_OF or GRANDCHILD_OF), NOT a direct child (e.g., SON_OF).\n"
                        "Verify and extract the exact kinship relationship using this rule.\n\n"
                        f"Text Chunks:\n{combined_text}"
                    )

                    extraction = None
                    try:
                        extraction = await llm.ainvoke(prompt)
                    except Exception as e:
                        # Attempt to parse and clean data from the exception/completion if it was a validation error
                        extraction = parse_and_clean_json_from_exception(e, KnowledgeExtraction)
                        if extraction:
                            log_json(
                                logger, logging.INFO, "recovered from output parsing validation error using fallback parser",
                                book_id=book_id,
                                chunk_ids=[c.id for c in batch],
                                error=str(e),
                            )
                        else:
                            log_json(
                                logger, logging.WARNING, "failed to extract/index chunk batch",
                                book_id=book_id,
                                chunk_ids=[c.id for c in batch],
                                error=str(e),
                            )
                    return batch, extraction

            # Run parallel LLM extractions
            tasks = [extract_batch(batch) for batch in batches]
            results = await asyncio.gather(*tasks)

            # 7. Process database inserts sequentially to avoid transaction deadlocks/lock conflicts
            for batch, extraction in results:
                if not extraction:
                    continue

                chunks_with_text = [c for c in batch if c.text]
                if not chunks_with_text:
                    continue

                try:
                    # Collect all entity names defined in extraction.entities
                    defined_entity_names = {e.name.strip() for e in extraction.entities if e.name and e.name.strip()}

                    # Extract and format entities
                    entities_to_upsert = []
                    for entity in extraction.entities:
                        name = entity.name.strip() if entity.name else ""
                        if not name:
                            continue
                        entities_to_upsert.append({
                            "name": name,
                            "type": entity.type.value if entity.type else EntityType.OTHER.value,
                            "subtype": entity.subtype,
                        })

                    # Scan relations for any entities not in defined_entity_names to ensure MATCH matches them
                    fallback_entities = []
                    for rel in extraction.relations:
                        src = rel.source_entity.strip() if rel.source_entity else ""
                        tgt = rel.target_entity.strip() if rel.target_entity else ""
                        if src and src not in defined_entity_names:
                            fallback_entities.append(src)
                            defined_entity_names.add(src)
                        if tgt and tgt not in defined_entity_names:
                            fallback_entities.append(tgt)
                            defined_entity_names.add(tgt)

                    for name in fallback_entities:
                        entities_to_upsert.append({
                            "name": name,
                            "type": "Concept",  # Fallback type
                            "subtype": "Auto-extracted from relation",
                        })

                    # Upsert entities in bulk
                    if entities_to_upsert:
                        await graph_repo.upsert_entities_bulk(entities_to_upsert)

                    # Connect chunks to entities in bulk (cross-attribute all extracted entities to chunks in batch)
                    pairs_to_connect = []
                    for name in defined_entity_names:
                        for chunk in chunks_with_text:
                            pairs_to_connect.append({
                                "chunk_id": chunk.id,
                                "entity_name": name,
                            })
                    if pairs_to_connect:
                        await graph_repo.connect_chunks_entities_bulk(pairs_to_connect)

                    # Connect entities in bulk
                    relations_to_connect = []
                    for rel in extraction.relations:
                        src = rel.source_entity.strip() if rel.source_entity else ""
                        tgt = rel.target_entity.strip() if rel.target_entity else ""
                        rtype = rel.relation_type.strip() if rel.relation_type else ""
                        if not src or not tgt or not rtype:
                            continue
                        relations_to_connect.append({
                            "source_name": src,
                            "rel_type": rtype,
                            "target_name": tgt,
                        })
                    if relations_to_connect:
                        await graph_repo.connect_entities_bulk(relations_to_connect)

                except Exception as save_exc:
                    log_json(
                        logger, logging.ERROR, "failed to save parsed/recovered entities/relations to Memgraph",
                        book_id=book_id,
                        chunk_ids=[c.id for c in batch],
                        error=str(save_exc),
                    )

        finally:
            await graph_repo.close()

        log_json(
            logger, logging.INFO, "knowledge graph job completed",
            book_id=book_id,
            chunk_count=len(chunks),
            batch_count=len(batches),
            batch_size=chunk_batch_size,
        )

    except Exception as exc:
        log_json(logger, logging.ERROR, "knowledge graph job failed", book_id=book_id, error=str(exc))
        raise
