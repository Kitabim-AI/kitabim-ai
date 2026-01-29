# Backend business features

## Library ingestion and processing
- PDF upload with content-hash deduplication and background processing.
- OCR pipeline for Uyghur books using Gemini or a local OCR service, with parallel page processing.
- Automatic cover extraction from the first PDF page and cover URL generation.
- Per-page embeddings generation and full-book content compilation for RAG.
- Resume/reprocess workflows for in-flight books and retrofitting missing fields at startup.

## Library catalog management
- Paginated book listing with search, sorting, and optional grouping by work (title + author).
- Fetch book details by ID or by content hash.
- Create, update, and delete book metadata with safeguards for protected fields.
- Page-level reset and manual text update with embedding regeneration.
- Manual cover upload by title with image validation and conversion to JPEG.

## Reader assistance (RAG chat)
- Book-scoped and global chat endpoints with Uyghur-only responses.
- Author lookup from natural-language queries, including title extraction in Uyghur.
- Current-page and current-volume scoping to narrow answers when requested.
- Category-based global routing using Gemini to pick relevant book categories.
- Hybrid retrieval (embeddings + keyword matching) with fallback context building.

## Text quality control
- Spell-check for full books or individual pages using Gemini.
- Apply approved corrections to page text and trigger embedding refresh.
- Verified pages are protected from being overwritten by OCR reprocessing.
