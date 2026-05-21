"""
Knowledge Graph Job — extracts entities/relations from book chunks and indexes them in Memgraph.

Processes book chunks concurrently using a semaphore to limit LLM API concurrency.
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
from app.services.knowledge_graph_service import KnowledgeExtraction
from app.utils.observability import log_json

from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger("app.worker.knowledge_graph_job")


async def knowledge_graph_job(ctx, book_id: str) -> None:
    log_json(logger, logging.INFO, "knowledge graph job started", book_id=book_id)

    try:
        # 1. Fetch LLM settings from PostgreSQL
        async with db_session.async_session_factory() as session:
            config_repo = SystemConfigsRepository(session)
            chat_model = await config_repo.get_value("gemini_chat_model", "gemini-3.1-flash-lite")
            max_parallel = int(await config_repo.get_value("kg_max_parallel_chunks", "5"))
            
            # Load book details
            result = await session.execute(select(Book).where(Book.id == book_id))
            book = result.scalar_one_or_none()
            if not book:
                log_json(logger, logging.WARNING, "knowledge_graph_job: book not found", book_id=book_id)
                return

            # Fetch all chunks of the book ordered by page_number, chunk_index
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

        # 3. Connect to Memgraph & Initialize
        graph_repo = GraphRepository()
        try:
            await graph_repo.init_constraints()

            # Idempotency: Clear existing graph data for this book first
            await graph_repo.clear_book_graph(book_id)
            log_json(logger, logging.INFO, "cleared existing graph data for book", book_id=book_id)

            # Create Book and Author nodes, then connect them
            author_name = book.author or "Unknown Author"
            await graph_repo.upsert_book(book_id=str(book.id), title=book.title, author=author_name)
            await graph_repo.upsert_author(name=author_name)
            await graph_repo.connect_author_book(author_name=author_name, book_id=str(book.id))

            # 4. Initialize LLM with structured output
            llm = ChatGoogleGenerativeAI(
                model=chat_model,
                google_api_key=api_key,
                temperature=0.0
            ).with_structured_output(KnowledgeExtraction)

            # 5. Process chunks concurrently with semaphore limits
            semaphore = asyncio.Semaphore(max_parallel)

            async def process_single_chunk(chunk: Chunk) -> None:
                async with semaphore:
                    chunk_id = chunk.id
                    page_num = chunk.page_number
                    text_preview = chunk.text[:100] + "..." if chunk.text else ""

                    # Write Chunk node & link to Book
                    await graph_repo.upsert_chunk(
                        chunk_id=chunk_id,
                        book_id=str(book.id),
                        page_number=page_num,
                        text_preview=text_preview
                    )
                    await graph_repo.connect_book_chunk(book_id=str(book.id), chunk_id=chunk_id)

                    if not chunk.text:
                        return

                    # Prompt for structured entity and relationship extraction
                    prompt = (
                        "You are an expert historical analyst and librarian. Read the following text chunk "
                        "from a book and extract key entities (persons, locations, events, eras, organization, concepts) "
                        "and the directed relationships between them. Ensure entities are referred to by their standard, "
                        "canonical names.\n\n"
                        "Important Kinship/Relationship Guideline:\n"
                        "- In Uyghur historical texts, terms of endearment or lineage like 'قوزىچىسى' or 'نەۋرىسى' "
                        "refer to a grandchild (e.g., GRANDSON_OF or GRANDCHILD_OF), NOT a direct child (e.g., SON_OF).\n"
                        "Verify and extract the exact kinship relationship using this rule.\n\n"
                        f"Text Chunk:\n{chunk.text}"
                    )

                    try:
                        extraction = await llm.ainvoke(prompt)

                        # Insert Entities
                        for entity in extraction.entities:
                            name = entity.name.strip()
                            if not name:
                                continue
                            await graph_repo.upsert_entity(
                                name=name,
                                entity_type=entity.type.value,
                                subtype=entity.subtype
                            )
                            # Connect Chunk to Entity
                            await graph_repo.connect_chunk_entity(chunk_id=chunk_id, entity_name=name)

                        # Insert Relationships
                        for rel in extraction.relations:
                            src = rel.source_entity.strip()
                            tgt = rel.target_entity.strip()
                            rtype = rel.relation_type.strip()
                            if not src or not tgt or not rtype:
                                continue
                            await graph_repo.connect_entities(
                                source_name=src,
                                rel_type=rtype,
                                target_name=tgt
                            )
                    except Exception as e:
                        log_json(logger, logging.WARNING, "failed to extract/index chunk",
                                 book_id=book_id, chunk_id=chunk_id, error=str(e))

            # Gather tasks and run
            tasks = [process_single_chunk(chunk) for chunk in chunks]
            await asyncio.gather(*tasks)
        finally:
            await graph_repo.close()

        log_json(logger, logging.INFO, "knowledge graph job completed", book_id=book_id, chunk_count=len(chunks))

    except Exception as exc:
        log_json(logger, logging.ERROR, "knowledge graph job failed", book_id=book_id, error=str(exc))
        raise
