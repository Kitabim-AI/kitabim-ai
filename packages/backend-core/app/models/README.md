# Pydantic Domain Models & Schemas (`app/models`)

## Overview
Defines shared Pydantic v2 data transfer objects (DTOs), API request/response schemas, camelCase alias generators, and user/role domain models shared across the backend API and worker services.

## Interface
- `[schemas.py:to_camel]` — `to_camel(string: str) -> str`: Converts `snake_case` field names into `camelCase` aliases.
- `[schemas.py:ErrorEvent]` — `class ErrorEvent(BaseModel)`: Error metadata (`ts`, `kind`, `message`, `context`).
- `[schemas.py:ExtractionResult]` — `class ExtractionResult(BaseModel)`: Per-page OCR extraction and pipeline status schema (`page_number`, `content_page_number`, `display_page_number`, `text`, `status`, `error`, `last_updated`, `pipeline_step`, `milestone`, `is_toc`, `llm_spell_check_status`, `llm_spell_check_at`).
- `[schemas.py:PageTocUpdate]` — `class PageTocUpdate(BaseModel)`: Payload for toggling `is_toc` on a page.
- `[schemas.py:OcrPageInput]` — `class OcrPageInput(BaseModel)`: External OCR page ingestion payload (`page_number`, `text`, `is_toc`).
- `[schemas.py:Book]` — `class Book(BaseModel)`: Book domain and API representation including metadata, pipeline milestones (`ocr_milestone`, `chunking_milestone`, `embedding_milestone`, `spell_check_milestone`), flags (`has_summary`, `has_graph`, `has_history`), and optional pages.
- `[schemas.py:PaginatedBooks]` — `class PaginatedBooks(BaseModel)`: Paginated book list response (`books`, `total`, `total_ready`, `page`, `page_size`).
- `[schemas.py:ChatRequest]` — `class ChatRequest(BaseModel)`: Chat query payload (`book_id`, `question`, `is_global`, `conversation_id`, `history`, `current_page`, `character_id`, `context_book_ids`, `exact_phrase`).
- `[schemas.py:ChatResponse]` — `class ChatResponse(BaseModel)`: Chat answer and usage response (`answer`, `usage`).
- `[schemas.py:ChatUsageStatus]` — `class ChatUsageStatus(BaseModel)`: Daily chat usage quota state (`usage`, `limit`, `has_reached_limit`).
- `[schemas.py:ContactSubmissionCreate]` — `class ContactSubmissionCreate(BaseModel)`: Public contact form request (`name`, `email`, `interest`, `message`).
- `[schemas.py:ContactSubmissionPublic]` — `class ContactSubmissionPublic(BaseModel)`: Public acknowledgment response (`id`, `status`, `created_at`).
- `[schemas.py:ContactSubmissionAdmin]` — `class ContactSubmissionAdmin(BaseModel)`: Admin view of a contact submission (`id`, `name`, `email`, `interest`, `message`, `status`, `admin_notes`, `reviewed_by`, `reviewed_at`, `created_at`).
- `[schemas.py:RagQuestionAdmin]` — `class RagQuestionAdmin(BaseModel)`: Admin RAG evaluation and cost record (`id`, `question`, `is_global`, `book_id`, `book_title`, `user_id`, `user_display_name`, `is_first_turn`, `show_on_homepage`, `user_feedback`, `ts`, `eval_status`, `faithfulness_score`, `answer_relevance_score`, `context_precision_score`, `input_tokens`, `output_tokens`, `cost_usd`, `answer`, `retrieved_context`).
- `[schemas.py:RagQuestionsPage]` — `class RagQuestionsPage(BaseModel)`: Offset/limit paginated RAG evaluation records (`items`, `total`, `offset`, `limit`).
- `[schemas.py:RagQuestionToggle]` — `class RagQuestionToggle(BaseModel)`: Request payload to toggle `show_on_homepage`.
- `[schemas.py:RagQuestionToggleResponse]` — `class RagQuestionToggleResponse(BaseModel)`: Response payload for `show_on_homepage` toggle (`id`, `show_on_homepage`).
- `[schemas.py:ContentSearchHit]` — `class ContentSearchHit(BaseModel)`: Full-text page search hit (`id`, `book_id`, `book_title`, `book_author`, `book_volume`, `book_cover_url`, `page_number`, `snippet`, `rank`).
- `[schemas.py:PaginatedContentHits]` — `class PaginatedContentHits(BaseModel)`: Paginated full-text content search response (`hits`, `total`, `page`, `page_size`).
- `[schemas.py:FactCitation]` — `class FactCitation(BaseModel)`: Book and page citation for an extracted historical fact (`book_id`, `book_title`, `volume`, `pages`).
- `[schemas.py:HistoryFact]` — `class HistoryFact(BaseModel)`: Historical fact item (`id`, `text`, `citations`, `status`, `conflict_group`).
- `[schemas.py:HistoryStagingItem]` — `class HistoryStagingItem(BaseModel)`: Staged historical dictionary entry with associated `HistoryFact` list.
- `[schemas.py:PaginatedHistoryStagingItems]` — `class PaginatedHistoryStagingItems(BaseModel)`: Paginated list of staged history dictionary items (`items`, `total`, `page`, `page_size`).
- `[user.py:UserRole]` — `class UserRole(str, Enum)`: User access role enum (`ADMIN = "admin"`, `EDITOR = "editor"`, `READER = "reader"`).
- `[user.py:UserBase]` — `class UserBase(BaseModel)`: Shared user fields (`email`, `display_name`, `avatar_url`).
- `[user.py:UserCreate]` — `class UserCreate(UserBase)`: OAuth user creation payload (`provider`, `provider_id`, `role = UserRole.READER`).
- `[user.py:User]` — `class User(UserBase)`: Full internal user domain model (`id`, `role`, `provider`, `provider_id`, `created_at`, `updated_at`, `last_login_at`, `last_login_ip`, `is_active = True`).
- `[user.py:UserPublic]` — `class UserPublic(BaseModel)`: Public/admin user profile schema with `from_user(cls, user: User) -> UserPublic` factory method.
- `[user.py:UserInToken]` — `class UserInToken(BaseModel)`: Decoded JWT token claims (`sub`, `email`, `role`, `display_name`, `jti`, `type`).
- `[user.py:UserUpdate]` — `class UserUpdate(BaseModel)`: Partial user update schema (`display_name`, `role`, `is_active`).
- `[user.py:UserList]` — `class UserList(BaseModel)`: Paginated user list schema (`users`, `total`, `page`, `page_size`).

## Invariants
- `[schemas.py:OcrPageInput.strip_null_bytes]` — Null bytes (`\x00`) are stripped from `OcrPageInput.text` during validation; falsy values normalize to `""`.
- `[schemas.py:ChatRequest.validate_question]` — `ChatRequest.question` must not exceed 500 characters and must contain at least one Uyghur/Arabic script character matching `[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]`.
- `[schemas.py:ContactSubmissionCreate]` — Enforces `name` length `1..255`, `email` length `3..255`, `interest` in `Literal["editor", "developer", "other"]`, and `message` length `10..5000`.
- `[schemas.py:to_camel]` — Schemas configured with `alias_generator=to_camel` and `populate_by_name=True` accept both `snake_case` and `camelCase` inputs and serialize to `camelCase` field aliases.
- `[user.py:UserRole]` — User roles are strictly constrained to `"admin"`, `"editor"`, and `"reader"`, defaulting to `UserRole.READER` on creation.

## Side Effects
- None

## Verification
- Run: `pytest packages/backend-core/tests`
