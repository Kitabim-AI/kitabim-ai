from __future__ import annotations

import logging

logger = logging.getLogger("app.worker.word_index_scanner")


async def run_word_index_scanner(ctx) -> None:
    """
    DEPRECATED: Word Indexing is no longer used in the pipeline.
    This scanner is kept as a stub to avoid import errors in legacy code.
    """
    logger.warning("run_word_index_scanner called but word indexing is disabled.")
    return

