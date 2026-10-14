-- Migration: 099_normalize_book_categories.sql
-- Description: Normalize books.categories. Strips invisible characters
--   (zero-width space U+200B, zero-width joiner U+200D, BOM U+FEFF) that made
--   visually identical categories distinct (e.g. ئ‍ىسلام vs ئىسلام), trims
--   whitespace/quotes, merges spelling variants and singular → plural pairs
--   into one canonical name (chosen by the project owner 2026-10-14), and
--   removes duplicates within each book, keeping first-occurrence order.
--   The mapping below must match CATEGORY_ALIASES in app/utils/categories.py
--   (checked by tests/app/utils/categories_test.py).
--   Original values are saved to books_categories_backup_099 first; the
--   rollback restores from it.
-- Author: Kitabim.AI
-- Date: 2026-10-14

BEGIN;

-- IF NOT EXISTS: a re-run must not overwrite the original snapshot.
CREATE TABLE IF NOT EXISTS books_categories_backup_099 AS
SELECT id AS book_id, categories
FROM books
WHERE categories IS NOT NULL AND cardinality(categories) > 0;

WITH mapping(old_name, new_name) AS (
    VALUES
        ('مۇۋاپېقىيەتشۇناسلىق', 'مۇۋەپپەقىيەتشۇناسلىق'),
        ('مۇۋاپپىقىيەتشۇناسلىق', 'مۇۋەپپەقىيەتشۇناسلىق'),
        ('ماقالىلار', 'ماقالىلەر'),
        ('نەسرلەر', 'نەسىرلەر'),
        ('ئەدەبىي ئاخبارات', 'ئەدەبىي ئاخباراتلار'),
        ('ئوچېرك', 'ئوچېركلار'),
        ('داستان', 'داستانلار'),
        ('پوۋېست', 'پوۋېستلار'),
        ('ئەدەبىي خاتىرە', 'ئەدەبىي خاتىرىلەر'),
        ('تەزكىرە', 'تەزكىرىلەر')
),
cleaned AS (
    SELECT
        b.id,
        t.pos,
        btrim(
            btrim(regexp_replace(t.cat, '[​‍﻿]', '', 'g')),
            '"'
        ) AS cat
    FROM books b
    CROSS JOIN LATERAL unnest(b.categories) WITH ORDINALITY AS t(cat, pos)
    WHERE b.categories IS NOT NULL
),
mapped AS (
    SELECT c.id, c.pos, COALESCE(m.new_name, btrim(c.cat)) AS cat
    FROM cleaned c
    LEFT JOIN mapping m ON m.old_name = btrim(c.cat)
    WHERE btrim(c.cat) <> ''
),
first_seen AS (
    SELECT id, cat, min(pos) AS pos
    FROM mapped
    GROUP BY id, cat
),
normalized AS (
    SELECT b.id,
           COALESCE(
               (SELECT array_agg(f.cat ORDER BY f.pos) FROM first_seen f WHERE f.id = b.id),
               '{}'::text[]
           ) AS categories
    FROM books b
    WHERE b.categories IS NOT NULL
)
UPDATE books
SET categories = n.categories
FROM normalized n
WHERE books.id = n.id
  AND books.categories IS DISTINCT FROM n.categories;

COMMIT;
