-- Migration Rollback: 103_rollback_strip_hypothetical_queries_from_book_summaries.sql
-- Description: No-op data rollback for stripping Section 6 hypothetical queries from book_summaries.summary.
-- Author: Kitabim.AI
-- Date: 2026-11-09

BEGIN;
-- Data cleanup migration 103 removed unused hypothetical questions in-place; rollback is a documented no-op.
COMMIT;
