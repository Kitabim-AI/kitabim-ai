# Local OCR Client: Relative Line-Length Signal for Line-Break/Merge Heuristic

## Status
Approved for implementation. Scoped to `clients/kitabim-ocr/` only (see Non-goals).

## Problem

`clean_uyghur_text()` in `clients/kitabim-ocr/engine/text_cleanup.py` decides, for each
pair of adjacent lines inside an OCR'd paragraph block, whether the line break between
them is:
- a **print-line wrap** that should become a space so the frontend can reflow the
  paragraph at the wider on-screen width, or
- an **intentional break** (dialogue turn, list item, poem verse, indented sub-paragraph,
  colon-introduced quote, etc.) that must be preserved as `\n`.

The current heuristic relies entirely on punctuation/structural regex signals (trailing
colon, next-line dash, list markers, indentation + terminal punctuation, markdown/TOC/
key-value markers). It misses intentional breaks that carry none of those cues — e.g. a
short line ending a thought with no colon, dash, or list marker, which today gets
incorrectly merged into the following line.

## Root cause

Surya's recognition step is a VLM that OCRs each layout block image to HTML using a
fixed, non-configurable prompt (`"OCR this block image to HTML."`, documented in Surya's
own source as "the model's training-time contract — do not paraphrase without
retraining"). Unlike the production Gemini OCR pipeline — which is explicitly instructed
via `OCR_PROMPT` to "keep text continuous within paragraphs... unless the text is a
poem" — Surya's block-recognition model was never trained/prompted to make that semantic
call. It reliably preserves per-print-line breaks within a block, which is why this
client needs its own reconstruction heuristic and always will, regardless of prompt
tuning.

Marker and Docling were considered and rejected: Marker now runs its OCR through the
same Surya VLM this client already uses, so it would inherit the identical
per-visual-line `<br>` behavior rather than fixing it. Docling has no confirmed reliable
Uyghur/Arabic-script recognition.

Surya's `BlockOCRResult` schema (`surya.recognition.schema`) only exposes block-level
`polygon`/`bbox`, not per-line boxes, so a true pixel-geometry margin comparison isn't
available without wiring in Surya's separate line-detection model (a larger change,
deferred — see Non-goals).

## Design

Add one new signal to the existing per-line merge-decision loop in
`clean_uyghur_text()`, purely additive to the existing OR'd conditions
(`is_colon_intro`, `is_next_dialogue`, `is_next_list_marker`, `is_indented_paragraph`,
`is_markdown_header`/`is_next_markdown_header`, `is_toc_line`/`is_next_toc_line`,
`is_key_value`/`is_next_key_value`):

1. Before the per-line loop, once per block:
   ```python
   block_max_len = max(len(l.lstrip()) for l in lines)
   ```
2. For each non-final line (`idx < len(lines) - 1` — the last line of a block is never
   checked; it's expected to be short as a normal paragraph ending and is already
   appended as-is with no decision needed):
   ```python
   is_short_relative_line = (
       block_max_len >= 15 and len(raw_line) <= 0.6 * block_max_len
   )
   ```
   where `raw_line = line.lstrip()` (already computed in the loop).
3. OR `is_short_relative_line` into the existing condition list that decides "keep `\n`"
   vs. "merge with space."

**Threshold: 0.6 (60%).** Chosen conservatively because the corpus's typesetting
(justified vs. ragged-right) is mixed/unknown — the signal should only fire on lines
that are unambiguously short, not on ordinary word-wrap variance. Tune after validating
against real samples (see Testing).

**Guard: `block_max_len < 15` chars disables the check** for that block — not enough
signal at that length to be meaningful, avoids noise on very short/fragmentary blocks.

This only affects blocks that reach the per-line loop at all — poem blocks
(`is_poem_block`) and metadata/key-value blocks (`is_metadata_or_key_value_block`) are
classified and handled earlier in `clean_uyghur_text()` and never enter this loop.

## Non-goals (deferred, not part of this change)

- **No change to `packages/backend-core/app/utils/text.py`.** That copy is the source
  of truth used by the production Gemini OCR pipeline (`ocr_service.py`,
  `batch_ocr_service.py`, `chunking_job.py`). This change is being validated on the
  experimental, not-yet-deployed local Surya client first; porting it to backend-core
  (and keeping the two files in sync, per the existing vendoring convention) is a
  follow-up decision after real-world validation here, not part of this change.
- **No per-line pixel geometry via Surya's line-detection model.** Would give a more
  accurate (non-approximated) margin comparison but requires wiring in a second model
  inference pass per block/page — meaningfully more engineering and latency cost.
  Revisit only if the character-count approximation proves insufficient in practice.
- **No text-only LLM reflow pass.** Would most closely match Gemini's own judgment but
  reintroduces an API cost/dependency into what's meant to be a free, local, standalone
  OCR path. Revisit only if heuristic approaches prove insufficient.
- **No corpus backfill.** This client isn't in production; there's no existing corpus
  processed by it to reprocess.

## Testing

Add cases to `clients/kitabim-ocr/tests/engine/test_text_cleanup.py`:
1. A short non-final line with no punctuation/indent/dash/colon cue is now preserved as
   an intentional break (the case this change exists to fix).
2. A non-final line at ~70–85% of its block's max length still merges (regression guard
   against being too aggressive on ordinary wrap variance).
3. A 2-line block where the *last* line is short still merges line 1 into it (regression
   guard confirming the check only applies to non-final lines).
4. A block with `block_max_len < 15` behaves unchanged (guard is respected).
5. Full existing `test_text_cleanup.py` suite continues to pass unmodified (this is an
   additive-only change).

Before merging, manually spot-check the updated `clean_uyghur_text()` against a handful
of real Surya-OCR'd pages (a few prose pages, at least one with dialogue, one with a
list) to confirm no regressions in already-correct merge decisions, per the project's
established "validate fixes on samples, not bulk" pattern.

## Rollout

Pure function change in a standalone, not-yet-deployed client. No migration, no
backfill, no feature flag needed — affects only future local OCR runs of this client.
