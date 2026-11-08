# Surya OCR Uyghur Fine-Tuning Plan

> [!IMPORTANT]
> **Standalone Repository Initialized:** Active dataset generation, evaluation, and LoRA training now live in `/Users/Omarjan/Projects/surya-uyghur-finetune` (see its `docs/PLAN.md` and `AGENTS.md`). Only Phase 1 runtime lexicon post-processing and Phase 4 `.env` model-path configuration touch `clients/kitabim-ocr/` in this repository.

**Date:** 2026-11-03  
**Branch:** `feature/elephant-and-goldfish`  
**Target Component:** `clients/kitabim-ocr/` (standalone desktop OCR tool) & `scripts/` (offline dataset/training/eval tooling)  
**Prior Research:** [`reports/Surya OCR Uyghur fine tuning.md`](../../../reports/Surya%20OCR%20Uyghur%20fine%20tuning.md), [`research_notes/Surya OCR Uyghur fine tuning/`](../../../research_notes/Surya%20OCR%20Uyghur%20fine%20tuning/)

---

## 1. Context & Architecture Baseline

`clients/kitabim-ocr/requirements.txt` currently pins **`surya-ocr==0.23.0`**, which defaults to **`datalab-to/surya-ocr-2.5`** (replacing `datalab-to/surya-ocr-2` from `0.22.1`):

- **Backbone:** `Qwen3_5ForConditionalGeneration` (~689M parameters: 12-layer ViT encoder + merger + 24-layer hybrid 3:1 linear/full-attention text decoder, `mtp_num_hidden_layers=0`).
- **No Official Training Script:** All online `finetune_ocr.py` tutorials target the retired `v0.15–v0.17` Donut-style recognizer and are incompatible with Surya 2.x. Because Surya 2.5 is a standard Hugging Face safetensors VLM (`AutoModelForMultimodalLM` + `AutoProcessor`), it is fine-tuned locally on Apple Silicon with standard Qwen3.5 VLM SFT tooling (`mlx-vlm` or `transformers` + `peft` + `trl`).
- **Full Uyghur Tokenizer Coverage:** Both Surya 2 and 2.5 use an 88,526-token character-level `WordLevel` tokenizer (`Split` regex `[\s\S]`) in which every Uyghur Arabic-script character (`ئ`, `ە`, `ۆ`, `ۇ`, `ۈ`, `ۋ`, `ې`, `ى`, `ڭ`, `ژ`, `ھ`, `گ`, `چ`, `پ`) plus `-`, `U+2010`, soft hyphen, and tatweel is already a single in-vocabulary token. **No vocabulary modification or embedding resizing is required.**
- **Baseline Weakness:** Datalab's internal benchmark scores Uyghur at **32.9% (Surya 2.5) / 34.1% (Surya 2)** vs. 74.9% overall. Key failure modes in Kitabim (`clients/kitabim-ocr/engine/recognize.py`) are:
  1. **Confusable glyph dots/marks:** `و/ۇ/ۆ/ۈ/ۋ`, `ز/ژ`, `ك/ڭ/گ`, `ي/ئې`, `چ/ج`, and Arabic-biased substitutions (`ب` for final `پ`, `ه` for `ە`), especially when 1980s–2000s offset/lead-type printing fuses 3-dot clusters into blobs or erodes faint dots.
  2. **Line-end hyphen hallucinations:** Uyghur hyphenates mid-word across line breaks (`prefix-`). Autoregressive language priors complete non-word fragments into hallucinated whole words.
  3. **Bleed-through ghost text & dense-page loops:** Reverse-side ink bleed-through, gutter shadows, and noisy scan backgrounds trigger repetition loops (`is_block_repetition_loop`) and ghost hallucinations (`is_hallucinated_ghost_text`). In addition, Uyghur consumes 1 token per character (Surya 2.5's ~20k multi-char tokens contain zero Arabic-script merges), and `clients/kitabim-ocr/engine/config.py` sets `DEFAULT_SURYA_MAX_TOKENS_FULL_PAGE = 2500` (vs. Surya's internal default `12288`), which can truncate dense >2,500-char pages.

---

## 2. Strategic Direction: Degraded Multi-Font Synthetic (~80%) + Verified Real Scans (~20%)

### 2.1 Findings from Database Audit (Why Raw PDF↔DB Pairing Is Unsafe at Scale)
Auditing the local PostgreSQL corpus (`633` books, `236,744` pages) and `packages/backend-core/app/services/spell_check_service.py` surfaced four structural blockers against naively pairing scanned PDFs with `pages.text`:

1. **Paragraph Reflow:** Existing `pages.text` was produced by Gemini Vision with paragraph reflow, erasing physical line breaks, stripping running headers, reordering footnotes, and removing line-end hyphens (`prefix-`).
2. **Table of Contents (ToC) Layout Divergence:** DB ToC pages (`pages.is_toc = true`, plus unlabeled ToCs) are normalized into simple Markdown pipe tables (`| title | page |`) whose visual structure does not match the printed PDF layout (dotted leaders, multi-column entries, indented sub-chapters). **DB ToC / Markdown pipe-table pages must never be paired against real PDF scans.**
3. **Uncorrected OOV Spelling Errors in `pages.text`:** Automatic spell-checking (`spell_check_milestone = 'succeeded'`) primarily *discovers* issues rather than fixing them (`677,904` `open` issues vs. `5,259` `corrected`; only `294` active `auto_correct_rules`). Worse, even `0` open `page_spell_issues` does **not** guarantee clean spelling: `spell_check_service.py` ignores tokens `< 4` chars (`_MIN_WORD_LEN = 4`) and only creates a `PageSpellIssue` if an unknown word matches its fixed `_OCR_PAIRS` / `_VOWEL_INSERTIONS` tables. Enforcing strict **100.0% dictionary membership (`len >= 2`, zero 1-char fragments, excluding `auto_correct_rules` triggers)** eliminated **98.2%** of `0`-open-issue candidates (`18,275` → `323` pages).
4. **Real-Word Contextual Substitutions:** Even at 100.0% dictionary hit rate, lexicon checks cannot catch OCR dot swaps that form *another* valid Uyghur word (e.g., `قول` vs. `قۇل`, `باش` vs. `ياش`, `ئوت` vs. `ئۆت`). Pairing a scanned glyph of `قۇل` with a DB label of `قول` directly poisons the VLM's visual glyph mapping.

### 2.2 Why Generating Synthetic Images from DB Content Is the Primary Backbone (~80%)
Flipping the pipeline to **render synthetic page and block images directly from filtered DB text** solves all four blockers simultaneously:

- **100% Image↔Label Faithfulness by Construction:** Even if a source sentence contains a contextual real-word substitution (`قول`), rendering that text produces the **exact glyph of `قول`** in the image. Visual features and character targets agree 100% of the time with zero label noise (while strict dictionary filtering + clean born-digital EPUB books keep the decoder's language prior clean).
- **Exact Surya 2.5 Bounding Boxes & Compact Layout Tags for Free:** Rendering HTML via headless Chromium (Playwright) exposes pixel-exact `getBoundingClientRect()` coordinates (`0–1000` normalized) for every `<p>`, `<h1>`–`<h3>`, poetry stanza, `Page-Header`, `Page-Footer`, `Footnote`, and **synthetically typeset dotted-leader / multi-column ToC**. This directly produces native Surya 2.5 full-page targets (`surya.inference.compact.encode(html)`) with zero teacher-alignment failures.
- **Unlimited Local Scale Without GCS Downloads:** Tens of thousands of clean pages (including digital EPUBs in PostgreSQL) can be rendered locally in minutes without pulling multi-hundred-MB PDFs from GCS.

### 2.3 Closing the Sim-to-Real Gap (Degradation + 20% Real Anchor Mix)
Pure clean synthetic rendering overfits crisp digital rasterization and fails on vintage Uyghur scans. To bridge the domain gap:
1. **Multi-Font Diversity (12–15+ fonts):** Never render with a single font; rotate across the `ALKATIP`, `UKIJ`, and classic Arabic Naskh book font families.
2. **Uyghur Print & Scan Physics Augmentation:** Simulate reverse-page **ghost bleed-through** (compositing a flipped, faint second Uyghur page behind the foreground page while keeping only foreground text in the label), **3-dot ink fusion / erosion**, paper grain, gutter shadows, skew, low-DPI resampling, and JPEG ringing.
3. **~20% Verified Real-Scan Anchor Mix + 100%-Real Benchmark:** Anchor training with human side-by-side reviewed real scans (`2,683` `status == "reviewed"` pages already available locally in `/Users/omarjan/kitabim-ocr-work`) so the model retains vintage lead-type/offset glyph priors, and **evaluate exclusively on held-out real scans**.

---

## 3. Hardware & 100%-Local Execution Strategy (No Cloud GPU)

### Local Machine Specs (Sole Training & Inference Host)
- **SoC:** Apple M2 Pro (`12-core CPU`: 8P + 4E, `19-core GPU`, `Metal 4`)
- **Memory:** 32 GB Unified RAM (`datalab-to/surya-ocr-2.5` is ~689M params / `~1.4 GB` in `bf16`; full LoRA training uses `~6–10 GB` RAM, leaving >20 GB headroom)
- **Available Disk:** ~82 GB free

### Laptop Optimization Principles (Throughput Over Brute-Force Volume)
Because 32 GB RAM easily holds `bf16` LoRA, **wall-clock token throughput** — not memory — is the sole constraint on this laptop. Two design choices cut training time ~4–5× without sacrificing real-world CER:

1. **93% Tight Block Crops / 7% Full-Page Replay:** A full-page sample (`~3,500` vision + text tokens) takes **~8–12× longer per step** on M2 Pro than a cropped 3–6 line paragraph block (`~400` tokens), yet both train the exact same vision/decoder weights. Using **~93% block crops** for glyph/hyphen mastery plus **~7% full-page compact examples (`~900–1,000` pages)** to preserve `full_page=True` layout & bleed-through behavior cuts wall time ~3×.
2. **High-Density Curation (`14,000` Curated Examples vs. `35,000` Random):** Packing every block with 3–5× oversampled confusable Uyghur letters (`ۆ, ۈ, ۇ, ې, ڭ, ژ, پ, چ`), balanced across 12–15 fonts and 25% `prefix-` hyphen breaks, captures **~90%+ of a 35k random dataset's CER gain** in an incremental two-night schedule with `--save-steps 250` pause/resume.

### 100%-Local Execution Schedule on M2 Pro

| Stage | Target Hardware | Memory / Disk Footprint | Expected Wall Time | Notes |
|---|---|---|---|---|
| **0. CER Harness & 100%-Real Eval Set** | Local M2 Pro | ~500 MB disk | ~15–30 mins | Built from `~/kitabim-ocr-work` reviewed scans + human-verified diplomatic crops. |
| **1. DB Text Sampling (`sample_surya_finetune_pages.py`)** | Local M2 Pro | <50 MB JSON manifests | ~15–30 secs | Queries local PostgreSQL (`236.7k` pages, `1.46M` dictionary words). |
| **2A. Degraded Synthetic Data (~80%: `11,200` samples)** | Local M2 Pro (12-core CPU) | ~1.5 GB disk (WebP/JPEG) | ~10–20 mins | From ~3,000 clean DB/EPUB pages via Playwright RTL + HarfBuzz + bleed-through/Augraphy. |
| **2B. Real-Scan Anchor Data (~20%: `2,800` samples)** | Local M2 Pro (Metal) | ~500 MB disk | ~30–60 mins | From `2,683` local `reviewed` pages in `~/kitabim-ocr-work` (local PDFs, zero GCS fetch). |
| **3A. Backend Benchmark (100 steps: MLX vs. MPS)** | Local M2 Pro (19-core GPU) | ~6–10 GB RAM | ~5–10 mins | Compare native Metal `mlx_vlm.lora` (via `build_mlx.py` repair) vs. PyTorch `mps` (`TRL`+`PEFT`). |
| **3B. Night 1 Milestone LoRA (`4,000` samples, 1 epoch)** | Local M2 Pro (19-core GPU) | ~6–10 GB RAM | **~1.5–3 hrs** | Delivers ~65% of total CER gain; validate on real eval set before expanding. |
| **3C. Night 2 Full Target (`+10,000` → `14,000` total)** | Local M2 Pro (overnight) | ~6–10 GB RAM | **+4–9 hrs** (~4–5h MLX / ~7–9h MPS) | Resumes from Night 1 checkpoint (`--save-steps 250` allows pause/resume anytime). |
| **4. Merge, `build_gguf` / `build_mlx` & Client Test** | Local M2 Pro | ~2–3 GB disk | ~2–5 mins | Exports local `.gguf` (`llama-server`) and/or repaired MLX dir for `clients/kitabim-ocr`. |

> **Disk Hygiene Rule (~82 GB free):** Store rendered/cropped training images as compressed WebP or JPEG (`~2 GB` total for `14,000` examples). Never materialize uncompressed 300 DPI PNGs in bulk; render/crop on the fly and delete intermediate canvases immediately.

---

## 4. Pre-Flight Gates

1. **License Gate (Modified OpenRAIL-M & Font Redistribution):**
   - `datalab-to/surya-ocr-2.5` weights prohibit commercial use above \$5M gross revenue or \$5M funding, prohibit competing with Datalab, and apply §8 share-alike terms to model derivatives and arguably to OCR outputs.
   - **Mitigation / Hedge:** Keep the dataset in model-agnostic Hugging Face VLM chat format (`images` + `messages`). The exact same script can train `Qwen/Qwen3.5-VL-0.8B` (Apache-2.0) alongside `datalab-to/surya-ocr-2.5` to compare CER on the held-out Uyghur eval set.
   - Verify font licenses (`ALKATIP`, `UKIJ`, `Amiri`, `Noto Naskh Arabic`) before publishing any synthetic image dataset externally (internal model training is unaffected).
2. **Ground-Truth & Evaluation Gate:**
   - **Never evaluate solely on synthetic validation data** (which only measures fit to synthetic shaders/fonts).
   - **Never include DB ToC / Markdown pipe-table pages** in real-PDF alignment sets.
   - No fine-tuned checkpoint ships without beating baseline Surya 2.5 + deterministic lexicon post-processing on a **100%-real, human-verified diplomatic evaluation set** (`uyghur_v1`).

---

## 5. Phased Implementation Plan

> Per `AGENTS.md`, all dataset, evaluation, and training scripts MUST live under `scripts/` (never in the repo root or service directories), and `clients/kitabim-ocr/` remains standalone (excluded from Docker Compose and deploy scripts).

### Phase 0: CER Evaluation Harness & 100%-Real Held-Out Benchmark
**Files to create/update:**
- `scripts/eval_surya_uyghur.py` (new evaluation harness extending logic from `scripts/compare_ocr.py`)

**Tasks:**
1. Implement deterministic Uyghur OCR normalization before scoring:
   - Strip `[Header]` / `[Footer]` tags and HTML wrapper tags (`<p>`, `<div>`, `<br>`).
   - Fold Arabic `ه` (`U+0647`) → Uyghur `ە` (`U+06D5`), `ک` (`U+06A9`) → `ك` (`U+0643`), and NFKC-decompose Arabic presentation forms while preserving `ئ` (`U+0626`).
2. Compute:
   - Overall **CER** (Character Error Rate) and **WER** (Word Error Rate).
   - **Per-letter confusion matrix** across `{و, ۇ, ۆ, ۈ, ۋ}`, `{ز, ژ}`, `{ك, ڭ, گ}`, `{ي, ې}`, `{ب, پ}`, `{چ, ج}`.
   - **Hyphen-fragment slice accuracy** (exact match on line-end `prefix-` tokens and hallucinated-suffix insertion rate).
   - Separate counters for **max-token cap hits** vs. **repetition loops** (check whether raising `SURYA_MAX_TOKENS_FULL_PAGE` from `2500` to `6144` fixes dense ToC/two-column truncations).
3. Curate the **100%-Real Held-Out Evaluation Set** (`data/ocr_eval/uyghur_v1/`, excluded from all synthetic and real training splits by `book_id`):
   - Select **≥5 held-out real scanned books** stratified across print era (1980s lead type, 1990s–2000s offset, modern digital), font, bleed-through, poetry/verse, footnotes, and real printed ToCs (seeded from `status == "reviewed"` sessions in `~/kitabim-ocr-work`).
   - Pre-populate block/line transcriptions via Surya + reviewed text alignment, then **human-verify diplomatically** (preserving literal line-end `prefix-`).
   - Target **1,000–2,000 real lines**, including **≥300 line-end hyphen fragments** and **≥100 occurrences per rare/confusable letter** (`ژ`, `ڭ`, `ۆ`, `ۈ`, `ې`).

**Exit Criterion:** Baseline Surya 2.5 CER, WER, confusion matrix, and hyphen-slice scores recorded on real scans (`uyghur_v1`).

---

### Phase 1: Deterministic Lexicon Post-Processing Baseline
**Target files in `clients/kitabim-ocr/engine/`:**
- `clients/kitabim-ocr/engine/dictionary.py` & `clients/kitabim-ocr/engine/text_cleanup.py`

**Tasks:**
1. Restore lexicon-validated line-end de-hyphenation (previously removed in commit `e15a26a8`):
   - Join line-end `p1-` + next-line `p2` into `p1p2` **only** when `p1p2` exists in the exported lexicon (`words` + `names_dictionary` + `history_dictionary`) and `p1-p2` is not a valid hyphenated compound (e.g., `ئاز-ئازدىن`).
2. Add conservative non-word confusion-set repair:
   - Only rewrite tokens **absent** from the lexicon using ≤2 substitutions within `{و,ۇ,ۆ,ۈ,ۋ}`, `{ز,ژ}`, `{ي,ې}`, `{ك,ڭ,گ}`, and word-final `ب→پ`, only when a single in-lexicon candidate unambiguously matches.
3. Re-run `scripts/eval_surya_uyghur.py` to establish the post-processed baseline that LoRA fine-tuning must beat, while verifying over-correction stays near zero.

---

### Phase 2: Hybrid Training Dataset Construction (~80% Synthetic / ~20% Real)

**Scripts:**
- `scripts/sample_surya_finetune_pages.py` *(implemented)* — strict zero-OOV DB page sampler
- `scripts/build_surya_uyghur_synthetic.py` *(to create)* — multi-font RTL Playwright/HarfBuzz page & block renderer + Uyghur scan degradation + `compact.encode()` target builder
- `scripts/align_surya_uyghur_blocks.py` *(to create)* — real PDF block cropper + `edlib` aligner on human-reviewed `~/kitabim-ocr-work` pages

#### 2.1 Exact Surya 2.5 Prompt & Target Contract (`surya/inference/prompts.py` & `surya/inference/compact.py`)
Surya 2.5 uses two verbatim prompt contracts that `clients/kitabim-ocr/engine/recognize.py` invokes (`full_page=True` primary pass + `full_page=False` block fallback on looping blocks). To maximize M2 Pro training throughput without losing full-page layout capability, we split the `14,000`-example curated dataset **~93% Block Mode / ~7% Full-Page Mode**:

1. **Block Mode (~93% of training examples: `~13,000` blocks — `PROMPT_TYPE_BLOCK`):**
   - **User message:** `[block_image, "OCR this block image to HTML."]` *(verbatim — never paraphrase)*
   - **Assistant message:** Canonical HTML matching Surya 2.5 (`"<p>line 1-\nline 2 ...</p>"`, `"<h1>...</h1>"`, etc.), preserving literal diplomatic `prefix-` at wrapped line breaks (~400 tokens/sample — ~8–12× faster per step on M2 Pro than full-page samples).
2. **Full-Page Replay Mode (~7% of training examples: `~1,000` pages — `PROMPT_TYPE_HIGH_ACCURACY_BBOX`):**
   - **User message:** `[page_image, "OCR this image to HTML. Each block is a div with data-label and data-bbox (x0 y0 x1 y1, normalized 0-1000)."]` *(verbatim)*
   - **Assistant message:** **Surya 2.5 compact format** generated via `surya.inference.compact.encode(canonical_html)` — i.e., `<|Text|><|71|><|88|><|920|><|240|><p>...</p><|Footnote|><|71|><|860|><|920|><|915|><p>...</p>` using Surya 2.5's hyphenated `BLOCK_LABELS` (`Text`, `Section-Header`, `Page-Header`, `Page-Footer`, `Footnote`, `Table-Of-Contents`, `Table`, `List-Group`, `Caption`). *Note: Do **not** train full-page targets on raw `<div data-label="...">` strings; `surya.inference.compact.decode()` expects compact `<|Label|><|x0|><|y0|><|x1|><|y1|>` headers at inference time.*

#### 2.2 Track A — Clean Text Corpus Sampling (`scripts/sample_surya_finetune_pages.py`)
- Exclude held-out evaluation `book_id`s completely.
- Exclude `pages.is_toc = true`, heuristic ToCs, and Markdown pipe-table rows (`^\s*\|.+\|\s*$`).
- Reject degenerate/looping/ghost-text artifacts via `clients/kitabim-ocr/engine/text_cleanup.py` filters.
- Enforce **100.0% dictionary membership (`--min-dict-hit-rate 1.0`, zero OOV tokens)** across **all** Uyghur tokens (`len >= 2`), reject 1-char OCR fragments, and reject any token matching `auto_correct_rules.misspelled_word` (`words_dict.txt` + `names_dictionary` − `auto_correct_rules` = `1,466,633` valid forms).
- Also include clean born-digital **EPUB** books from PostgreSQL as a zero-OCR-noise source pool for synthetic rendering, stratified across `prose`, `heading_or_structured`, and `poetry` (capping pages per book for maximum lexical diversity).

#### 2.3 Track B — High-Density Degraded Multi-Font Synthetic Data (~80% of Dataset: `11,200` examples from ~3,000 pages)
1. **RTL Layout & Typography Rendering:**
   - **Full-Page Renderer (Headless Chromium / Playwright):** Render structured RTL HTML pages (`dir="rtl"`, varied page aspect ratios from pocketbooks to royal octavo, font sizes `11pt–18pt`, line-heights `1.4–2.1`, justified vs. ragged alignment, synthetic running `Page-Header` and `Page-Footer` folio numbers, bottom `Footnote` rules, poetry couplet indents, and **visual dotted-leader / two-column `Table-Of-Contents` templates**). Extract exact DOM `getBoundingClientRect()` coordinates per block to emit `~800` full-page `compact.encode(html)` examples and `~10,400` 4px-padded block crops.
   - **Fast Block Supplement (Pillow + Raqm/HarfBuzz):** Optionally generate additional tight single-block crops (`assert PIL.features.check("raqm")` — **never** combine `arabic_reshaper` or `python-bidi` with Raqm).
2. **Font Pool (12–15+ Fonts to Prevent Single-Font Overfitting):**
   - Bundle and sample evenly (~800–900 blocks/font) across `ALKATIP Basma` & `ALKATIP Basma Tom` (already in `clients/kitabim-ocr/preview/static/fonts/`), `ALKATIP Kitab`, `ALKATIP Tor`, `UKIJ Tuz`, `UKIJ Tuz Tom`, `UKIJ Basma`, `UKIJ Kitab`, `UKIJ Kufi`, `UKIJ Qolyazma`, `UKIJ Chiwer`, `Noto Naskh Arabic`, `Amiri`, and `Scheherazade New`.
3. **High-Density Linguistic & Hyphenation Supervision (Laptop Efficiency Multiplier):**
   - Deterministically hyphenate wrapped Uyghur words at valid syllable boundaries (`prefix-`) on **25% of lines** (~3,500+ hyphenated breaks), keeping literal `prefix-` in the HTML ground truth.
   - Oversample paragraphs rich in `ۆ`, `ۈ`, `ۇ`, `ڭ`, `ژ`, `ې`, `پ`, `چ` by **3–5×** (dropping low-information boilerplate blocks so every M2 Pro gradient step trains hard glyphs).
   - Inject **5–10% minimal-pair character swaps** (`قول`↔`قۇل`, `باش`↔`ياش`, word-final `پ`↔`ب`, `ي`↔`ې`) into both the rendered HTML and target string so the VLM must inspect diacritical dots visually rather than relying solely on lexical predictability.
4. **Uyghur Print & Scan Degradation Pipeline (`Augraphy` / OpenCV / Pillow):**
   - **Reverse-Page Bleed-Through (Critical):** Composite a horizontally mirrored, slightly blurred, low-opacity (`alpha = 0.04–0.12`) second rendered Uyghur page onto the paper background while keeping **only foreground blocks** in the target — directly teaching Surya 2.5 to ignore ghost bleed-through.
   - **Diacritical Dot & Ink Morphology:** Mild random morphological dilation/erosion, ink-bleed kernels, and speckle dropout simulating 3-dot fusion (`پ`, `چ`, `ژ`) and faint dot wear on 1980s–2000s paperbacks.
   - **Scanner & Optical Artifacts:** Warm/aged paper textures, uneven illumination & binding-gutter shadow, page skew (`±2°`), slight perspective curl, Gaussian/defocus blur, `110–220 DPI` downscale→upscale (matching `get_adaptive_page_zoom` scales), and JPEG compression (`quality = 35–85`).

#### 2.4 Track C — Verified Real-Scan Anchor Mix (~20% of Dataset: `2,800` examples)
- **Primary Real Source:** Use the **`2,683` human side-by-side reviewed pages (`status == "reviewed"`)** stored locally in `/Users/omarjan/kitabim-ocr-work` (paired with their local source PDFs, reserving ~300–500 pages across ≥5 held-out books for `uyghur_v1` evaluation and using ~1,000–1,500 non-ToC pages to yield `~2,600` aligned block crops + `~200` full-page compact examples).
- Render native page images via PyMuPDF (`fitz`) using `recognize.py`'s adaptive zoom (`get_adaptive_page_zoom`) and optional `enhance_dots_and_contrast`.
- Crop layout blocks with 4 px padding (matching `RecognitionPredictor._crop_block`) and align Surya's raw output against the human-reviewed text via `edlib` (`CER < 15%`), preserving diplomatic line-end `prefix-` tokens (dropping blocks with ambiguous line-break alignment).

---

### Phase 3: 100%-Local M2 Pro LoRA SFT Fine-Tuning
**File to create:**
- `scripts/train_surya_uyghur_lora.py`

**Backend Choice on Apple M2 Pro (100-Step Benchmark Gate):**
- **Option A — Apple MLX (`mlx-vlm` + `surya.scripts.build_mlx`):** Runs Qwen3.5's hybrid Gated DeltaNet linear-attention + full-attention layers natively on the 19-core Metal GPU without CPU fallback (~2× faster step time on M2 Pro). Convert base checkpoint via `python -m surya.scripts.build_mlx --checkpoint datalab-to/surya-ocr-2.5 --out-dir ./models/surya-2.5-base-mlx --dtype bfloat16` (which preserves Surya's character-level `WordLevel` `tokenizer.json` and fixes `eos_token_id`).
- **Option B — PyTorch `mps` (`transformers` + `peft` + `trl` with `PYTORCH_ENABLE_MPS_FALLBACK=1`):** Direct Hugging Face `Qwen3_5ForConditionalGeneration` `bf16` LoRA path; slightly slower per step due to MPS fallback on linear-attention ops, but merges directly via `model.merge_and_unload()` into `surya.scripts.build_gguf`.
- Run a **100-step timing & loss-curve check** (~5–10 mins) before Night 1 and pick whichever backend gives higher tokens/sec with clean character-level decoding on `uyghur_v1_dev`.

**Training Configuration:**
- **Base Checkpoint:** `datalab-to/surya-ocr-2.5` (pinned to match `surya-ocr==0.23.0`).
- **Precision:** **`bfloat16` LoRA** (`load_in_4bit=False`). Do **not** use 4-bit QLoRA — quantization degrades fine-grained diacritic and dot discrimination on Qwen3.5 VLMs, and 32 GB Unified RAM easily fits `bf16` (`~6–10 GB` peak).
- **LoRA Targets:** Apply LoRA (`r=16`, `lora_alpha=16`, `lora_dropout=0.05`) to **both** the vision encoder/merger (`qkv`, `proj`, `mlp` — essential for degraded Uyghur dot/bleed-through adaptation) and text decoder attention/MLP projections (`q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj`).
- **Loss Masking & Anti-Hallucination Regularization:** Compute cross-entropy loss strictly on assistant tokens (including `<|Label|><|x0|>...` compact headers in full-page examples), combined with minimal-pair visual swaps from Track B (`2–3%` optional target character perturbation) to weaken over-eager lexical auto-completion on hyphenated fragments.
- **Hyperparameters & Pause-Safe Checkpointing:**
  - Learning rate: `1e-4` to `2e-4` (cosine schedule, 5% warmup)
  - Effective batch size: `16` (`per_device_train_batch_size=2`, `gradient_accumulation_steps=8`)
  - Checkpointing: **`--save-steps 250`** (~20–30 mins per checkpoint) so training can be paused anytime during laptop daytime use and resumed with `--resume-from-checkpoint` without losing work; validate CER every `250–500` steps on a **real-scan dev split**.

**Two-Night Incremental Local Schedule (Zero Wasted Compute):**
1. **Night 1 — Fast Milestone (`4,000` mixed 80/20 samples: ~3,700 blocks + ~300 full pages, ~1.5–3 hrs on M2 Pro):**
   ```bash
   PYTORCH_ENABLE_MPS_FALLBACK=1 python scripts/train_surya_uyghur_lora.py \
     --model-id datalab-to/surya-ocr-2.5 \
     --train-data data/ocr_train/stage1_4k \
     --eval-data data/ocr_eval/uyghur_v1_dev \
     --output-dir models/surya-2.5-uyghur-lora \
     --save-steps 250 \
     --bf16
   ```
   *Gate:* Evaluate Night 1 checkpoint on `uyghur_v1_dev` — verify ~50–65% of expected CER drop (`ه→ە`, `ب→پ`, common vowel dots, basic `prefix-` retention) before running Night 2.
2. **Night 2 — Full Production Target (Resume from Night 1 on remaining `+10,000` → `14,000` total samples, ~4–9 hrs overnight on M2 Pro):**
   ```bash
   PYTORCH_ENABLE_MPS_FALLBACK=1 python scripts/train_surya_uyghur_lora.py \
     --model-id datalab-to/surya-ocr-2.5 \
     --train-data data/ocr_train/stage2_14k \
     --eval-data data/ocr_eval/uyghur_v1_dev \
     --output-dir models/surya-2.5-uyghur-lora \
     --resume-from-checkpoint latest \
     --save-steps 250 \
     --bf16
   ```

---

### Phase 4: Merge, GGUF / MLX Export & Local Client Integration

On macOS (`Apple Silicon`), `surya.settings.Settings` natively supports **both** `llama.cpp` (`SURYA_GGUF_LOCAL_MODEL_PATH`) and `mlx-vlm` (`SURYA_INFERENCE_BACKEND=mlx` + `SURYA_MLX_MODEL`).

1. **Merge LoRA Adapter into Base Weights:**
   - Merge via PEFT `model.merge_and_unload()` (or `mlx_vlm.lora --fuse` if trained in MLX) and save `model.safetensors` + `config.json` to `models/surya-2.5-uyghur-merged/`.
   - **Critical Tokenizer/EOS Parity Step:** Copy `tokenizer.json`, `tokenizer_config.json`, `chat_template.jinja`, `preprocessor_config.json`, and `processor_config.json` **verbatim** from the original `datalab-to/surya-ocr-2.5` snapshot rather than letting `processor.save_pretrained()` re-serialize them (`surya/scripts/build_gguf.py` and `surya/scripts/build_mlx.py` both enforce this exact character-level `WordLevel` tokenizer and `<|im_end|>` EOS id).

2. **Export Local Inference Artifact (`GGUF` Default or Native `MLX`):**
   - **Default (`llama.cpp` GGUF + `mmproj`):**
     ```bash
     clients/kitabim-ocr/.venv/bin/python -m surya.scripts.build_gguf \
       --checkpoint ./models/surya-2.5-uyghur-merged \
       --out-dir ./models/surya-2.5-uyghur-gguf \
       --name surya-2.5-uyghur \
       --outtype f16
     ```
   - **Optional Apple Silicon Native Alternative (`MLX`):**
     ```bash
     clients/kitabim-ocr/.venv/bin/python -m surya.scripts.build_mlx \
       --checkpoint ./models/surya-2.5-uyghur-merged \
       --out-dir ./models/surya-2.5-uyghur-mlx \
       --name surya-2.5-uyghur \
       --dtype bfloat16
     ```

3. **Verify Parity & Plug Into `clients/kitabim-ocr/.env`:**
   ```dotenv
   # Option 1 (default llama-server Metal backend):
   SURYA_GGUF_LOCAL_MODEL_PATH=/Users/Omarjan/Projects/kitabim-ai/models/surya-2.5-uyghur-gguf/surya-2.5-uyghur.gguf
   SURYA_GGUF_LOCAL_MMPROJ_PATH=/Users/Omarjan/Projects/kitabim-ai/models/surya-2.5-uyghur-gguf/surya-2.5-uyghur-mmproj.gguf

   # Option 2 (optional native MLX server backend on M2 Pro):
   # SURYA_INFERENCE_BACKEND=mlx
   # SURYA_MLX_MODEL=/Users/Omarjan/Projects/kitabim-ai/models/surya-2.5-uyghur-mlx/surya-2.5-uyghur

   # Safety stop string if character-level EOS ever spells <|im_end|> after punctuation:
   SURYA_STOP_STRINGS=<|im_end|>
   ```
   Re-run `scripts/eval_surya_uyghur.py` through `kitabim-ocr`'s full-page recognition pipeline to verify:
   - Exported runtime CER matches merged `bf16` CER within `<0.2%`.
   - Overall CER, confusable-letter accuracy, bleed-through suppression, and line-end hyphen preservation beat both stock Surya 2.5 and Phase 1 post-processing alone on **real scans**, with zero regression on full-page layout detection.

---

### Phase 5: Continuous Ground-Truth Flywheel (Optional Follow-Up)
Once Phase 4 is validated, add a lightweight `is_human_verified` flag and pre-edit `raw_ocr_text` snapshot on manual page edits in the Kitabim backend (and preserve diplomatic pre-reflow block crops in `kitabim-ocr-work` reviewed sessions) so every human-proofread page automatically feeds the 20% real-scan anchor and evaluation pools for future OCR iterations.
