"""Database seeding logic"""

import logging
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.observability import log_json

logger = logging.getLogger("app.db.seeds")


async def seed_system_configs(session: AsyncSession):
    """Seed default system configurations if they don't exist"""
    repo = SystemConfigsRepository(session)

    defaults = [
        {
            "key": "ocr_max_retry_count",
            "value": "10",
            "description": "Maximum number of OCR retry attempts per page before marking it as error/skipped.",
        },
        {
            "key": "gemini_chat_model",
            "value": "gemini-3-flash-preview",
            "description": "Gemini model used for chat responses (reader chat and global chat).",
        },
        {
            "key": "gemini_ocr_model",
            "value": "gemini-3-flash-preview",
            "description": "Gemini model used for OCR page processing.",
        },
        {
            "key": "gemini_embedding_model",
            "value": "gemini-embedding-2",
            "description": "Gemini model used for generating text embeddings (vector search).",
        },
        {
            "key": "maintenance_retention_days",
            "value": "7",
            "description": "Number of days to retain processed pipeline events before automated cleanup.",
        },
        {
            "key": "spell_check_enabled",
            "value": "true",
            "description": "Globally enable/disable background spell check processing.",
        },
        {
            "key": "ocr_max_parallel_pages",
            "value": "1",
            "description": "Maximum number of pages to OCR concurrently within a single OCR job. Set to 1 to process pages strictly one at a time.",
        },
        {
            "key": "summary_scanner_batch_size",
            "value": "5",
            "description": "Number of books the summary scanner enqueues per run. Increase temporarily to speed up bulk regeneration, then reset to 5.",
        },
        {
            "key": "graph_scanner_batch_size",
            "value": "5",
            "description": "Number of books the graph scanner enqueues per run. Increase temporarily to speed up bulk backfill, then reset to 5.",
        },
        {
            "key": "gemini_kg_extraction_model",
            "value": "gemini-3.1-flash-lite",
            "description": "Gemini model used for entity/relation extraction during knowledge graph indexing.",
        },
        {
            "key": "kg_chunk_batch_size",
            "value": "5",
            "description": "Number of chunks combined into a single LLM call during knowledge graph extraction. Higher values reduce API calls and improve coreference resolution at the cost of larger prompts. Default tuned for 1500-char chunks (~7 500 chars per call).",
        },
        {
            "key": "kg_max_parallel_chunks",
            "value": "5",
            "description": "Maximum number of concurrent LLM batch calls during knowledge graph extraction. Each call processes kg_chunk_batch_size chunks.",
        },
        {
            "key": "agent_max_steps",
            "value": "6",
            "description": "Maximum ReAct iterations/steps per round in the agent loop.",
        },
        {
            "key": "agent_enough_chunks",
            "value": "8",
            "description": "Early-exit threshold: stop agent loop once this many chunks are collected.",
        },
        {
            "key": "knowledge_graph_enabled",
            "value": "false",
            "description": "Globally enable/disable knowledge graph extraction and the graph scanner. Set to 'true' to activate.",
        },
        {
            "key": "fictional_categories",
            "value": "رومان, تارىخىي رومان, بالىلار رومانى, ساتىرىك رومان, پەلسەپىۋىي رومان, پوۋېست, پوۋېستلار, تارىخىي پوۋېست, ھېكايىلەر, تارىخىي ھېكايىلەر, بالىلار ھېكايىلېرى, چۆچەكلەر, قىسسە, تارىخىي قىسسە, داستان, داستانلار, تارىخىي داستان, رىۋايەتلەر, مەسەللەر, لەتىپىلەر, يۇمۇرلار, شېئىرلار, سەھنە ئەسەرلېرى, كىنو سېنارىيىلىرى",
            "description": "Comma-separated list of categories that indicate a book is fictional. If a book's categories match any in this list, its Person entities will be namespaced to prevent cross-book duplication. Otherwise, it defaults to non-fictional.",
        },
    ]

    for item in defaults:
        existing = await repo.get(item["key"])
        if not existing:
            log_json(
                logger,
                logging.INFO,
                "Seeding system config",
                key=item["key"],
                value=item["value"],
            )
            await repo.create(**item)

    await session.commit()
