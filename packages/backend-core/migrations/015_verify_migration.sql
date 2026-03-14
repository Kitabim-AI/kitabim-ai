-- Verification script for Migration 015
-- Run this AFTER the migration to verify data integrity

\echo '══════════════════════════════════════════════════════════════════════════════'
\echo 'Migration 015 Verification Report'
\echo '══════════════════════════════════════════════════════════════════════════════'
\echo ''

-- ──────────────────────────────────────────────────────────────────────────────
-- 1. Check table existence and structure
-- ──────────────────────────────────────────────────────────────────────────────

\echo '1. Verifying table structure...'
\echo ''

SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'dictionary')
        THEN '✓ dictionary table exists'
        ELSE '✗ ERROR: dictionary table missing'
    END as check_1;

SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'words')
        THEN '✓ words table exists'
        ELSE '✗ ERROR: words table missing'
    END as check_2;

SELECT
    CASE
        WHEN EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'book_word_index')
        THEN '✓ book_word_index table exists'
        ELSE '✗ ERROR: book_word_index table missing'
    END as check_3;

SELECT
    CASE
        WHEN EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'book_word_index' AND column_name = 'word_id'
        )
        THEN '✓ book_word_index.word_id column exists'
        ELSE '✗ ERROR: book_word_index.word_id column missing'
    END as check_4;

\echo ''

-- ──────────────────────────────────────────────────────────────────────────────
-- 2. Check row counts and data integrity
-- ──────────────────────────────────────────────────────────────────────────────

\echo '2. Verifying data counts...'
\echo ''

SELECT
    'dictionary' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('dictionary')) as total_size
FROM dictionary

UNION ALL

SELECT
    'words' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('words')) as total_size
FROM words

UNION ALL

SELECT
    'book_word_index' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('book_word_index')) as total_size
FROM book_word_index;

\echo ''

-- ──────────────────────────────────────────────────────────────────────────────
-- 3. Check foreign key integrity
-- ──────────────────────────────────────────────────────────────────────────────

\echo '3. Verifying foreign key integrity...'
\echo ''

SELECT
    CASE
        WHEN COUNT(*) = 0
        THEN '✓ All book_word_index.word_id references are valid'
        ELSE CONCAT('✗ ERROR: ', COUNT(*), ' orphaned word_id references')
    END as check_fk_words
FROM book_word_index bwi
LEFT JOIN words w ON w.id = bwi.word_id
WHERE w.id IS NULL;

SELECT
    CASE
        WHEN COUNT(*) = 0
        THEN '✓ All book_word_index.book_id references are valid'
        ELSE CONCAT('✗ ERROR: ', COUNT(*), ' orphaned book_id references')
    END as check_fk_books
FROM book_word_index bwi
LEFT JOIN books b ON b.id = bwi.book_id
WHERE b.id IS NULL;

\echo ''

-- ──────────────────────────────────────────────────────────────────────────────
-- 4. Check for duplicate words
-- ──────────────────────────────────────────────────────────────────────────────

\echo '4. Checking for duplicates...'
\echo ''

SELECT
    CASE
        WHEN COUNT(*) = 0
        THEN '✓ No duplicate words in words table'
        ELSE CONCAT('✗ ERROR: ', COUNT(*), ' duplicate words found')
    END as check_duplicates
FROM (
    SELECT word, COUNT(*) as cnt
    FROM words
    GROUP BY word
    HAVING COUNT(*) > 1
) dups;

\echo ''

-- ──────────────────────────────────────────────────────────────────────────────
-- 5. Storage savings analysis
-- ──────────────────────────────────────────────────────────────────────────────

\echo '5. Storage savings analysis...'
\echo ''

WITH stats AS (
    SELECT
        COUNT(*) as total_records,
        COUNT(DISTINCT word_id) as unique_words,
        pg_total_relation_size('book_word_index') as new_size
    FROM book_word_index
),
estimated_old_size AS (
    -- Estimate old size: each row had TEXT word instead of INT word_id
    -- Average Uyghur word is ~10-15 bytes, INT is 4 bytes
    -- So savings is roughly (avg_word_length - 4) * total_records
    SELECT
        (SELECT COUNT(*) FROM book_word_index) * 50 as estimated_bytes
)
SELECT
    total_records as "Total Records",
    unique_words as "Unique Words",
    pg_size_pretty(new_size) as "New Size",
    pg_size_pretty(estimated_bytes) as "Estimated Old Size",
    pg_size_pretty(estimated_bytes - new_size) as "Estimated Savings",
    ROUND(100.0 * (estimated_bytes - new_size) / NULLIF(estimated_bytes, 0), 1) || '%' as "Savings %"
FROM stats, estimated_old_size;

\echo ''

-- ──────────────────────────────────────────────────────────────────────────────
-- 6. Index verification
-- ──────────────────────────────────────────────────────────────────────────────

\echo '6. Verifying indexes...'
\echo ''

SELECT
    indexname,
    tablename,
    pg_size_pretty(pg_relation_size(indexname::regclass)) as size
FROM pg_indexes
WHERE tablename IN ('words', 'book_word_index', 'dictionary')
ORDER BY tablename, indexname;

\echo ''

-- ──────────────────────────────────────────────────────────────────────────────
-- 7. Sample data verification
-- ──────────────────────────────────────────────────────────────────────────────

\echo '7. Sample data verification (first 5 records)...'
\echo ''

SELECT
    b.title as book_title,
    w.word,
    bwi.occurrence_count
FROM book_word_index bwi
INNER JOIN words w ON w.id = bwi.word_id
INNER JOIN books b ON b.id = bwi.book_id
ORDER BY bwi.occurrence_count DESC
LIMIT 5;

\echo ''
\echo '══════════════════════════════════════════════════════════════════════════════'
\echo 'Verification Complete'
\echo '══════════════════════════════════════════════════════════════════════════════'
