-- Migration: 080_add_history_facts.sql
-- Description: Add structured `facts` to history_dictionary(_staging), replacing `sources`.
--   Existing published history_dictionary rows are bootstrapped into a single
--   legacy fact (wrapping their prose `definition`, carrying over any existing
--   `sources` as that fact's citations) before `sources` is dropped, so no
--   citation data is lost. Pending staging rows predate the fact model and
--   cannot be curated under it, so they are cleared for re-extraction instead.
-- Author: Omarjan
-- Date: 2026-08-02

BEGIN;

ALTER TABLE public.history_dictionary
    ADD COLUMN IF NOT EXISTS facts JSONB NOT NULL DEFAULT '[]'::jsonb;

UPDATE public.history_dictionary
SET facts = jsonb_build_array(
    jsonb_build_object(
        'id', 1,
        'text', definition,
        'citations', COALESCE(sources, '[]'::jsonb),
        'status', 'active',
        'conflict_group', NULL
    )
)
WHERE definition IS NOT NULL
  AND btrim(definition) <> ''
  AND jsonb_array_length(facts) = 0;

ALTER TABLE public.history_dictionary
    DROP COLUMN IF EXISTS sources;

ALTER TABLE public.history_dictionary_staging
    ADD COLUMN IF NOT EXISTS facts JSONB NOT NULL DEFAULT '[]'::jsonb,
    DROP COLUMN IF EXISTS sources,
    ALTER COLUMN definition DROP NOT NULL;

-- Clean cut-over: existing prose-only staging candidates predate the fact
-- model and cannot be curated under the new UI; clear them so books are
-- re-queued through the new extraction pipeline instead.
DELETE FROM public.history_dictionary_staging WHERE status = 'pending';

COMMIT;
