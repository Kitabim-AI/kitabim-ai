# Semantic Chunking Implementation Plan

## 1. Overview
Currently, the system embeds entire pages (truncated to 2000 chars) as a single vector. We will transition to **Semantic Chunking** using `RecursiveCharacterTextSplitter` to improve retrieval accuracy and granularity. Each page will be split into multiple overlapping chunks, stored in a dedicated `chunks` collection.

## 2. Database Schema Changes

### New Collection: `chunks`
We will create a new MongoDB collection named `chunks` to store vector embeddings and text segments.

**Schema:**
```json
{
  "_id": "ObjectId",
  "bookId": "String (indexed)",
  "pageNumber": "Integer",
  "chunkIndex": "Integer",
  "text": "String",
  "embedding": "List[float] (1x768)",
  "metadata": {
    "startChar": "Integer",
    "endChar": "Integer"
  },
  "createdAt": "DateTime"
}
```

### Existing Collection: `pages`
*   **Remove:** `embedding` field (will be redundant).
*   **Retain:** `text` (source of truth for the full page content), `status`, `isVerified`.

## 3. Chunking Strategy

We will use `RecursiveCharacterTextSplitter` from LangChain.
*   **Chunk Size:** 1000 characters.
*   **Overlap:** 200 characters.
*   **Separators:** `["\n\n", "\n", ". ", " ", ""]` (prioritizes paragraphs and sentences).

**Why this supports "Semantic" goals:**
While not using an ML-based "semantic splitter" (which is slow), recursive splitting respects natural language boundaries (paragraphs/sentences), ensuring chunks are semantically coherent compared to arbitrary slicing.

## 4. Component Updates

### A. New Service: `ChunkingService` (`app/services/chunking_service.py`)
*   Wraps `RecursiveCharacterTextSplitter`.
*   Method `split_text(text: str) -> List[str]`.

### B. PDF Processing (`app/services/pdf_service.py`)
*   **Current:** `embedder.aembed_documents([page_text])` -> Update `pages`.
*   **New:**
    1.  Get page text.
    2.  `chunks = chunking_service.split_text(text)`.
    3.  `embeddings = embedder.aembed_documents(chunks)`.
    4.  Construct `chunk` documents.
    5.  `db.chunks.delete_many({"bookId": ..., "pageNumber": ...})` (Idempotency).
    6.  `db.chunks.insert_many(new_chunk_docs)`.

### C. RAG Retrieval (`app/services/rag_service.py`)
*   **Current:** Query `pages`.
*   **New:**
    1.  Query `chunks` (`find({"bookId": ...})`).
    2.  Compute Cosine Similarity on chunks.
    3.  Group results by Page?
        *   *Strategy:* Return the top N chunks.
        *   Map the winning chunk back to its `pageNumber`. Return the `page` content for context, or just the chunk text if we want specific answers.
        *   *Decision:* The `rag_service` currently returns `context`. We will construct context from the *Top Chunks*.

### D. Data Management (`app/api/endpoints/books.py`)
*   **Deletion:** When deleting a book, delete from `chunks`.
*   **Re-OCR/Reset:** Clear related entries in `chunks`.

## 5. Execution Steps
1.  Create `ChunkingService`.
2.  Update `pdf_service` to write to `chunks`.
3.  Update `rag_service` to read from `chunks`.
4.  Update API endpoints for cleanup.
