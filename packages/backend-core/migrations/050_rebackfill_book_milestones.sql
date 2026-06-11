-- Re-backfill book-level milestone fields from current page states.
--
-- Migration 048 ran while some worker jobs were still in flight, causing those books
-- to receive 'in_progress' book-level milestones even though their pages later completed.
-- The fixed worker code (all book_ids updated after a batch) handles future runs, but
-- this re-run corrects the books that were stuck with stale 'in_progress' values.
--
-- Safe to run at any time: for books with pages genuinely in_progress (active jobs),
-- it will correctly compute 'in_progress'. Those books will self-correct when the job
-- finishes and calls update_book_milestone_for_step.
--
-- Uses the same logic as BookMilestoneService.compute_milestone_status():
--   done == total                      → 'complete'
--   failed == total                    → 'failed'
--   done + failed == total, failed > 0 → 'partial_failure'
--   done > 0 OR active > 0 OR failed>0 → 'in_progress'
--   else                               → 'idle'

WITH page_counts AS (
    SELECT
        book_id,
        COUNT(*)                                                                     AS total,
        -- OCR
        COUNT(*) FILTER (WHERE ocr_milestone = 'succeeded')                          AS ocr_done,
        COUNT(*) FILTER (WHERE ocr_milestone IN ('failed', 'error'))                 AS ocr_failed,
        COUNT(*) FILTER (WHERE ocr_milestone = 'in_progress')                        AS ocr_active,
        -- Chunking
        COUNT(*) FILTER (WHERE chunking_milestone = 'succeeded')                     AS chunking_done,
        COUNT(*) FILTER (WHERE chunking_milestone IN ('failed', 'error'))             AS chunking_failed,
        COUNT(*) FILTER (WHERE chunking_milestone = 'in_progress')                   AS chunking_active,
        -- Embedding
        COUNT(*) FILTER (WHERE embedding_milestone = 'succeeded')                    AS embedding_done,
        COUNT(*) FILTER (WHERE embedding_milestone IN ('failed', 'error'))            AS embedding_failed,
        COUNT(*) FILTER (WHERE embedding_milestone = 'in_progress')                  AS embedding_active,
        -- Spell check
        COUNT(*) FILTER (WHERE spell_check_milestone = 'succeeded')                  AS spell_check_done,
        COUNT(*) FILTER (WHERE spell_check_milestone IN ('failed', 'error'))          AS spell_check_failed,
        COUNT(*) FILTER (WHERE spell_check_milestone = 'in_progress')                AS spell_check_active
    FROM pages
    GROUP BY book_id
),
computed AS (
    SELECT
        book_id,
        CASE
            WHEN total = 0                                          THEN 'idle'
            WHEN ocr_done = total                                   THEN 'complete'
            WHEN ocr_failed = total                                 THEN 'failed'
            WHEN ocr_done + ocr_failed = total AND ocr_failed > 0  THEN 'partial_failure'
            WHEN ocr_done > 0 OR ocr_active > 0 OR ocr_failed > 0  THEN 'in_progress'
            ELSE 'idle'
        END AS ocr_milestone,
        CASE
            WHEN total = 0                                                        THEN 'idle'
            WHEN chunking_done = total                                            THEN 'complete'
            WHEN chunking_failed = total                                          THEN 'failed'
            WHEN chunking_done + chunking_failed = total AND chunking_failed > 0  THEN 'partial_failure'
            WHEN chunking_done > 0 OR chunking_active > 0 OR chunking_failed > 0  THEN 'in_progress'
            ELSE 'idle'
        END AS chunking_milestone,
        CASE
            WHEN total = 0                                                          THEN 'idle'
            WHEN embedding_done = total                                             THEN 'complete'
            WHEN embedding_failed = total                                           THEN 'failed'
            WHEN embedding_done + embedding_failed = total AND embedding_failed > 0  THEN 'partial_failure'
            WHEN embedding_done > 0 OR embedding_active > 0 OR embedding_failed > 0  THEN 'in_progress'
            ELSE 'idle'
        END AS embedding_milestone,
        CASE
            WHEN total = 0                                                                  THEN 'idle'
            WHEN spell_check_done = total                                                   THEN 'complete'
            WHEN spell_check_failed = total                                                 THEN 'failed'
            WHEN spell_check_done + spell_check_failed = total AND spell_check_failed > 0   THEN 'partial_failure'
            WHEN spell_check_done > 0 OR spell_check_active > 0 OR spell_check_failed > 0  THEN 'in_progress'
            ELSE 'idle'
        END AS spell_check_milestone
    FROM page_counts
)
UPDATE books
SET
    ocr_milestone        = computed.ocr_milestone,
    chunking_milestone   = computed.chunking_milestone,
    embedding_milestone  = computed.embedding_milestone,
    spell_check_milestone = computed.spell_check_milestone
FROM computed
WHERE books.id = computed.book_id;
