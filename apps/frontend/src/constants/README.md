# Frontend Constants

## Overview
Provides application-wide immutable static datasets and pipeline enumeration configurations, including conversational assistant persona definitions and OCR/RAG ingestion pipeline milestones.

## Interface
- `[characters.ts:Character]`: Interface defining assistant persona metadata (`id`, `name_uy`, `name_en`, `avatar_emoji`).
- `[characters.ts:CHARACTERS]`: Array of system assistant personas (`religious_scholar`, `uyghurologist`, `historian`, `writer`, `librarian`).
- `[characters.ts:DEFAULT_CHARACTER_ID]`: Fallback assistant persona identifier (`'librarian'`).
- `[milestones.ts:PIPELINE_STEP]`: Pipeline execution step enum constants (`OCR`, `CHUNKING`, `EMBEDDING`, `SUMMARY`, `SPELL_CHECK`, `GRAPH`, `HISTORY`, `READY`, `ERROR`).
- `[milestones.ts:PipelineStep]`: Union type representing values of `PIPELINE_STEP`.
- `[milestones.ts:PAGE_LEVEL_MILESTONE_STEPS]`: Readonly tuple of page-level pipeline milestone steps (`ocr`, `chunking`, `embedding`, `spell_check`).
- `[milestones.ts:MILESTONE_FIELD_BY_STEP]`: Mapping from pipeline steps to book milestone field names.
- `[milestones.ts:ADMIN_PIPELINE_STEPS]`: Array of pipeline steps paired with admin i18n translation label keys.
- `[milestones.ts:REPROCESS_STEP]`: Reprocessing action step enum constants (`OCR`, `CHUNKING`, `EMBEDDING`, `SPELL_CHECK`, `LLM_SPELL_CHECK`, `GRAPH`, `SUMMARY`, `HISTORY`).
- `[milestones.ts:ReprocessStep]`: Union type representing values of `REPROCESS_STEP`.

## Invariants
- `[characters.ts:DEFAULT_CHARACTER_ID]`: Value `'librarian'` is guaranteed to match a valid `Character.id` in `[characters.ts:CHARACTERS]`.
- `[milestones.ts:PAGE_LEVEL_MILESTONE_STEPS]`: Guaranteed to be a subset of `PIPELINE_STEP` values.
- `[milestones.ts:REPROCESS_STEP]`: Reprocessing steps for spell checking use kebab-case (`'spell-check'`, `'llm-spell-check'`), contrasting with the snake_case milestone value in `PIPELINE_STEP.SPELL_CHECK` (`'spell_check'`).

## Side Effects
- `None`: Pure constants and TypeScript definitions with zero side effects.

## Verification
- Run: `npm test`
