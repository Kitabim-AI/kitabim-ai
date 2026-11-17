# Database Migrations (`migrations`)

## Overview
Provides sequential SQL migration scripts and rollbacks for the Kitabim AI PostgreSQL database schema, including tables, indexes, extensions (such as `pg_trgm` and `vector`), and initial system configuration seeds.

## Interface
- `[001_initial_baseline.sql:books]` — Book metadata, pipeline milestones, and processing flags.
- `[001_initial_baseline.sql:pages]` — Per-page OCR text, status, page offsets, and milestone states.
- `[001_initial_baseline.sql:chunks]` — Extracted text chunks with vector embeddings.
- `[001_initial_baseline.sql:users]` — User accounts, authentication providers, and role access.
- `[001_initial_baseline.sql:refresh_tokens]` — Hashed JWT refresh tokens and expiration metadata.
- `[001_initial_baseline.sql:system_configs]` — Key-value system configuration store.
- `[001_initial_baseline.sql:user_chat_usage]` — Daily chat usage quota tracking per user/IP.
- `[001_initial_baseline.sql:book_summaries]` — Book summaries and chapter abstracts.
- `[001_initial_baseline.sql:auto_correct_rules]` — Uyghur spell-check auto-correct mappings.
- `[001_initial_baseline.sql:page_spell_issues]` — Logged spell check issues per page.
- `[041_add_agent_metrics_to_rag_evaluations.sql:rag_evaluations]` — RAG query evaluation and metrics.
- `[058_rename_dictionary_to_words_and_create_new_dictionary.sql:words]` — Base Uyghur lexicon vocabulary.
- `[058_rename_dictionary_to_words_and_create_new_dictionary.sql:dictionary]` — Multi-dictionary entry definitions.
- `[059_create_synonyms_table.sql:synonyms]` — Uyghur synonym word pairs.
- `[060_create_history_dictionary.sql:history_dictionary]` — Historical terms, definitions, and aliases.
- `[062_create_names_dictionary.sql:names_dictionary]` — Uyghur proper name lexicon.
- `[064_create_english_uyghur_dictionary.sql:english_uyghur_dictionary]` — English-Uyghur bilingual dictionary.
- `[067_create_quran_table.sql:quran]` — Quran verses with translations and vector embeddings.
- `[070_add_batch_ocr_jobs.sql:batch_ocr_jobs]` — Asynchronous batch OCR tracking jobs.
- `[071_add_batch_embedding_jobs.sql:batch_embedding_jobs]` — Batch embedding generation jobs.
- `[072_add_conversations.sql:conversations]` — User chat conversation threads.
- `[072_add_conversations.sql:conversation_messages]` — Individual messages within conversation threads.
- `[075_add_entity_resolution_tables.sql:graph_resolution_queue]` — Entity resolution queue for claiming Neo4j nodes.
- `[075_add_entity_resolution_tables.sql:graph_resolution_reviews]` — Admin review queue for ambiguous resolution cases.
- `[075_add_entity_resolution_tables.sql:graph_merge_log]` — Pre-merge snapshot log enabling unmerge.
- `[078_create_batch_history_extraction_jobs.sql:batch_history_extraction_jobs]` — Batch history extraction jobs.
- `[079_create_history_dictionary_staging.sql:history_dictionary_staging]` — Staging table for extracted history terms.
- `[080_add_history_facts.sql:history_facts]` — Extracted historical facts and citations.
- `[091_add_batch_llm_spell_check_jobs.sql:batch_llm_spell_check_jobs]` — Batch LLM spell check jobs.
- `[095_create_reading_progress.sql:reading_progress]` — User reading progress tracking.
- `[096_create_bookmarks.sql:bookmarks]` — User bookmarked pages.
- `[097_seed_max_book_upload_mb_system_config.sql:system_configs]` — Seeds `max_book_upload_mb` upload size configuration.
- `[098_seed_rag_summary_narrowing_config.sql:system_configs]` — Seeds RAG summary narrowing configuration keys.
- `[099_normalize_book_categories.sql:books]` — Normalizes book category tags across `books.categories`.
- `[100_add_gemini_llm_spell_check_timeout_config.sql:system_configs]` — Historical LLM spell-check timeout configuration (retired in `102`).
- `[101_add_book_structure_and_section_chunking.sql:book_sections]` — Adds `book_sections` hierarchy, `books.structure_milestone` and backfill provenance columns, `pages.detected_page_number`, and `chunks` section/page-span/hash columns.
- `[102_drop_llm_spell_check_and_history_staging.sql:pages]` — Drops retired LLM spell-check and history concept extraction/staging tables, columns, and system configs.
- `[103_strip_hypothetical_queries_from_book_summaries.sql:book_summaries]` — Strips retired Section 6 (`Hypothetical Queries`) and renumbers Section 7 (`Keywords`) to Section 6 in `book_summaries.summary`.

## Invariants
- `[001_initial_baseline.sql:books]` — Migrations `002`-`033` are squashed into `001_initial_baseline.sql`; active sequential numbering begins at `034`.
- Migration files follow sequential naming pattern `NNN_description.sql` and rollback pattern `NNN_rollback_description.sql`.
- All migration DDL/DML scripts must be wrapped in atomic transaction blocks (`BEGIN; ... COMMIT;`).

## Side Effects
- Mutates PostgreSQL schema definitions, constraints, tables, columns, and indexes.
- Inserts or deletes default configuration and seed data rows.

## Verification
- Run: `pytest packages/backend-core/tests`

## Migration Guide & Operations

### Migration Naming Convention
Migrations follow the pattern: `NNN_description.sql`
- `NNN` = Sequential migration number (e.g., 089)
- `description` = Brief description of the migration

### Running Migrations

#### Local Development
```bash
# Run a specific migration on local database
psql -h localhost -p 5432 -U omarjan -d kitabim-ai -f packages/backend-core/migrations/089_remove_dead_system_configs.sql
```

#### Production
Using the migration runner script:
```bash
# From project root
./scripts/run_migration_prod.sh 089
```

### Rollback Migrations
Rollback migrations follow the pattern: `NNN_rollback_description.sql`

To rollback a migration:
```bash
# Local
psql -h localhost -p 5432 -U omarjan -d kitabim-ai \
  -f packages/backend-core/migrations/089_rollback_remove_dead_system_configs.sql

# Production
./scripts/run_migration_prod.sh 089_rollback
```
