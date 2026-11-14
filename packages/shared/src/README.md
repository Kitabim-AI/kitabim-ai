# Shared API Types & Schemas

## Overview
Shared TypeScript type definitions and OpenAPI contract models consumed across the Kitabim frontend application and API clients. It provides auto-generated OpenAPI schemas and extended domain interfaces for books, pages, chat conversations, reading progress, and error events.

## Interface
- `[index.ts:export * from './types']`: Main entry point re-exporting shared TypeScript interfaces.
- `[types.ts:Book]`: Client domain interface extending OpenAPI schema with typed Dates, nested pages, `ocrVersion`, `contentPageMap`, and pipeline milestones (`ocrMilestone`, `structureMilestone`, `chunkingMilestone`, `embeddingMilestone`, `spellCheckMilestone`).
- `[types.ts:ExtractionResult]`: Page-level OCR, page-number (`detectedPageNumber`, `contentPageNumber`, `contentPageNumberManual`), and indexing progress state (`status`, `pipelineStep`, `milestone`).
- `[types.ts:ErrorEvent]`: Standardized error event model with timestamp and contextual metadata.
- `[types.ts:PaginatedBooks]`: Paginated wrapper containing an array of `Book` models.
- `[types.ts:Message]`: Turn-by-turn chat message payload including token costs and RAG evaluation IDs.
- `[types.ts:Conversation]`: Chat session entity metadata.
- `[types.ts:ConversationMessage]`: Detailed message entity including agent execution steps and user feedback.
- `[types.ts:ChatRequest]`: Chat invocation request payload with conversation history and character contexts.
- `[types.ts:Bookmark]`: User page bookmark record.
- `[types.ts:ReadingProgressEntry]`: User reading progress state tracking last viewed page and book metadata.
- `[api-types.ts:paths]`: Auto-generated OpenAPI route definitions covering all backend HTTP endpoints.
- `[api-types.ts:components]`: Auto-generated OpenAPI data transfer objects and schema definitions.

## Invariants
- `[api-types.ts]`: Auto-generated from backend OpenAPI schema via `npm run openapi:generate-types`; manual changes must not be made directly to this file.
- `[types.ts:Book]`: Date properties (`uploadDate`, `lastUpdated`) are parsed into native JavaScript `Date` instances.

## Side Effects
- `None` (Pure static TypeScript interface and type declarations without runtime side effects).

## Verification
- Run: `npm --workspace apps/frontend run test`
