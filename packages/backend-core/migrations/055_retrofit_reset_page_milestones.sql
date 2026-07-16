-- Retrofit pages that were reset via the broken reset_page endpoint.
--
-- The old endpoint set milestone = 'idle' (legacy column) but never touched the
-- decoupled ocr_milestone/chunking_milestone/embedding_milestone columns, so the
-- OCR scanner never picked those pages up.
--
-- Affected pages are identified by:
--   pipeline_step = 'ocr'   (set by the reset endpoint)
--   milestone     = 'idle'  (set by the reset endpoint)
--   ocr_milestone != 'idle' (not yet corrected — scanner never touched them)
--   text IS NULL            (text was cleared by the reset endpoint)
--
-- Fix: reset all decoupled milestones to 'idle' so the OCR scanner picks them up,
-- then recompute book-level milestones from the corrected page state.

-- Step 1: fix the stuck pages.
UPDATE pages
SET
    ocr_milestone         = 'idle',
    chunking_milestone    = 'idle',
    embedding_milestone   = 'idle',
    spell_check_milestone = 'idle',
    status                = 'pending',
    is_indexed            = FALSE,
    retry_count           = 0,
    last_updated          = NOW()
WHERE
    pipeline_step = 'ocr'
    AND milestone = 'idle'
    AND ocr_milestone != 'idle'
    AND text IS NULL;

-- Step 2: recompute book-level milestones for every book that had stuck pages,
-- using the same logic as BookMilestoneService.compute_milestone_status().
WITH page_counts AS (
    SELECT
        book_id,
        COUNT(*)                                                                        AS total,
        COUNT(*) FILTER (WHERE ocr_milestone = 'succeeded')                             AS ocr_done,
        COUNT(*) FILTER (WHERE ocr_milestone IN ('failed', 'error'))                    AS ocr_failed,
        COUNT(*) FILTER (WHERE ocr_milestone = 'in_progress')                           AS ocr_active,
        COUNT(*) FILTER (WHERE chunking_milestone = 'succeeded')                        AS chunking_done,
        COUNT(*) FILTER (WHERE chunking_milestone IN ('failed', 'error'))               AS chunking_failed,
        COUNT(*) FILTER (WHERE chunking_milestone = 'in_progress')                      AS chunking_active,
        COUNT(*) FILTER (WHERE embedding_milestone = 'succeeded')                       AS embedding_done,
        COUNT(*) FILTER (WHERE embedding_milestone IN ('failed', 'error'))              AS embedding_failed,
        COUNT(*) FILTER (WHERE embedding_milestone = 'in_progress')                     AS embedding_active,
        COUNT(*) FILTER (WHERE spell_check_milestone = 'succeeded')                     AS spell_check_done,
        COUNT(*) FILTER (WHERE spell_check_milestone IN ('failed', 'error'))            AS spell_check_failed,
        COUNT(*) FILTER (WHERE spell_check_milestone = 'in_progress')                   AS spell_check_active
    FROM pages
    WHERE book_id IN (
        SELECT DISTINCT book_id
        FROM pages
        WHERE pipeline_step = 'ocr' AND milestone = 'idle' AND ocr_milestone = 'idle' AND text IS NULL
    )
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
            WHEN total = 0                                                          THEN 'idle'
            WHEN chunking_done = total                                              THEN 'complete'
            WHEN chunking_failed = total                                            THEN 'failed'
            WHEN chunking_done + chunking_failed = total AND chunking_failed > 0    THEN 'partial_failure'
            WHEN chunking_done > 0 OR chunking_active > 0 OR chunking_failed > 0   THEN 'in_progress'
            ELSE 'idle'
        END AS chunking_milestone,
        CASE
            WHEN total = 0                                                            THEN 'idle'
            WHEN embedding_done = total                                               THEN 'complete'
            WHEN embedding_failed = total                                             THEN 'failed'
            WHEN embedding_done + embedding_failed = total AND embedding_failed > 0   THEN 'partial_failure'
            WHEN embedding_done > 0 OR embedding_active > 0 OR embedding_failed > 0  THEN 'in_progress'
            ELSE 'idle'
        END AS embedding_milestone,
        CASE
            WHEN total = 0                                                                    THEN 'idle'
            WHEN spell_check_done = total                                                     THEN 'complete'
            WHEN spell_check_failed = total                                                   THEN 'failed'
            WHEN spell_check_done + spell_check_failed = total AND spell_check_failed > 0     THEN 'partial_failure'
            WHEN spell_check_done > 0 OR spell_check_active > 0 OR spell_check_failed > 0    THEN 'in_progress'
            ELSE 'idle'
        END AS spell_check_milestone
    FROM page_counts
)
UPDATE books
SET
    ocr_milestone         = computed.ocr_milestone,
    chunking_milestone    = computed.chunking_milestone,
    embedding_milestone   = computed.embedding_milestone,
    spell_check_milestone = computed.spell_check_milestone,
    status                = 'pending',
    last_updated          = NOW()
FROM computed
WHERE books.id = computed.book_id;
