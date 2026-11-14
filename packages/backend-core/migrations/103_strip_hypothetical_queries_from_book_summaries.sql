-- Migration: 103_strip_hypothetical_queries_from_book_summaries.sql
-- Description: Strip Section 6 (Hypothetical Queries / تىپىك سوئاللار) from book_summaries.summary and renumber Section 7 (Keywords / ئاچقۇچلۇق سۆزلەر) to 6 without clearing embeddings.
-- Author: Kitabim.AI
-- Date: 2026-11-09

BEGIN;

UPDATE public.book_summaries
SET
    summary = regexp_replace(
        regexp_replace(
            regexp_replace(
                summary,
                '\n?[[:space:]]*(?:\*\*|#+\s*)?6\.\s*تىپىك سوئاللار[\s\S]*(\n[[:space:]]*(?:\*\*|#+\s*)?7\.\s*ئاچقۇچلۇق سۆزلەر)',
                '\1'
            ),
            '\n?[[:space:]]*(?:\*\*|#+\s*)?6\.\s*تىپىك سوئاللار[\s\S]*$',
            ''
        ),
        '(^|\n)([[:space:]]*(?:\*\*|#+\s*)?)7(\.\s*ئاچقۇچلۇق سۆزلەر)',
        '\1\26\3',
        'g'
    )
WHERE summary IS NOT NULL
  AND (
      summary ~ '6\.\s*تىپىك سوئاللار'
      OR summary ~ '7\.\s*ئاچقۇچلۇق سۆزلەر'
  );

COMMIT;
