# Fine-tuning Surya OCR text recognition for Uyghur: how it works (as of 2026-10-31)

Research method: I read the installed `surya-ocr==0.22.1` package in `/Users/Omarjan/Projects/kitabim-ai/venv` and `clients/kitabim-ocr/.venv`, and its embedded README (METADATA). I pulled the HF `config.json`, `tokenizer.json` and `LICENSE` for `datalab-to/surya-ocr-2` and `datalab-to/surya-ocr-2.5` and tested the tokenizers locally on Uyghur text. I also used the GitHub releases and issues APIs, the v0.17.1 tag of the repo, the HF model cards and the Datalab blog. Repo URLs below use `datalab-to/surya`. The older `VikParuchuri/surya` URLs redirect there.

**Most important finding:** "Surya recognition" is now a different kind of model. From v0.20.0 (May 2026), Surya is a ~650-690M-param Qwen3.5-architecture VLM (vision-language model) served through vLLM or llama.cpp. Every piece of fine-tuning guidance written for 0.x (Donut-style `surya_rec`/`surya_rec2`, the "foundation" model, `finetune_ocr.py`) applies only to the old v0.15-0.17 models. **Datalab has not published a training script for Surya 2 or 2.5.**

---

## Q1. What is the current release and architecture, and how did it evolve? Is Uyghur supported?

### Takeaway
The newest release is `surya-ocr` **v0.23.0 (2026-10-29)**, which defaults to **Surya 2.5** (`datalab-to/surya-ocr-2.5`). Kitabim pins **v0.22.1 (2026-07-20)**, which uses **Surya 2** (`datalab-to/surya-ocr-2`). Both are `Qwen3_5ForConditionalGeneration` VLMs with a ViT vision encoder and a 24-layer hybrid linear/full-attention decoder. The tokenizer is character-level, and each Uyghur letter is one token. Uyghur ("ug") is in the 91-language internal benchmark, but it scores very low: **34.1% (Surya 2) and 32.9% (Surya 2.5)**.

### Cited Findings
**Version history**
- **v0.20.0 (2026-05-27), "Surya 2", a ground-up rework.** One 650M-param model now handles OCR, layout and table recognition, served by `vllm` (NVIDIA) or `llama.cpp` (CPU/Apple Silicon). Text detection and OCR-error detection remain separate small torch models. It had breaking API changes: `SuryaInferenceManager` replaces `FoundationPredictor`, and the output field `text_lines` became `blocks` (each with `html`). — [v0.20.0 release](https://github.com/datalab-to/surya/releases/tag/v0.20.0)
- **v0.21.0 (2026-07-08)** added a fast layout model that runs on CPU. **v0.22.0 (2026-07-17)** swapped to a "spawn + server" model instead of one model per process. **v0.22.1 (2026-07-20)** is the version Kitabim pins. — [GitHub releases](https://github.com/datalab-to/surya/releases)
- **v0.23.0 (2026-10-29)** defaults to Surya 2.5. Datalab claims 1.7x the pages/s of Surya 2 on one H100 and 85.9 on OmniParseBench. They say it "almost never loops": 0.1% of requests hit the output limit at 192 DPI, against 3.8% for Surya 2 with MTP. Surya 2.5 has no row/column table geometry, and you can stay on Surya 2 with `SURYA_MODEL_CHECKPOINT=datalab-to/surya-ocr-2`. It also adds an experimental MLX backend. — [v0.23.0 release](https://github.com/datalab-to/surya/releases/tag/v0.23.0)
- **Older line (v0.x to v0.17.1, 2024 to Jan 2026).**
  - Recognition used a separate model loaded from S3 checkpoints. In v0.17.1, `FOUNDATION_MODEL_CHECKPOINT` and `RECOGNITION_MODEL_CHECKPOINT` were both `s3://text_recognition/2025_09_23`, and layout used `s3://layout/2025_09_23`. — [v0.17.1 settings.py](https://raw.githubusercontent.com/datalab-to/surya/v0.17.1/surya/settings.py)
  - v0.17.0 (2025-09-23) introduced a "new unified tokenizer" (PR #442) and a new layout model. v0.16.5 added the "Foundation predictor". — [GitHub releases](https://github.com/datalab-to/surya/releases)
  - In 0.x, recognition consumed **detected text-line crops** and used **script tokens**, for example `SCRIPT_TOKEN_MAPPING = {"latin": "<SCRIPT-LATIN>", ...}`. — [v0.17.1 common/util.py](https://raw.githubusercontent.com/datalab-to/surya/v0.17.1/surya/common/util.py)
  - The very old v0.4.x had an explicit language list that included `'ug': 'Uyghur'`. Its RTL helper returned true for `["ar","fa","ps","ug","ur"]`. — [v0.4.14 languages.py](https://raw.githubusercontent.com/datalab-to/surya/v0.4.14/surya/languages.py)

**Surya 2 architecture** (from `config.json`, [surya-ocr-2](https://huggingface.co/datalab-to/surya-ocr-2/resolve/main/config.json))
- `architectures: ["Qwen3_5ForConditionalGeneration"]`, `model_type: qwen3_5`, built with transformers 5.2.0.
- **Text decoder:** 24 layers, hidden size 1024, intermediate size 3584, 8 attention heads with 2 KV heads, head_dim 256.
  - `layer_types` alternates 3× `linear_attention` then 1× `full_attention`, so `full_attention_interval=4`.
  - Uses M-RoPE (`mrope_section [11,11,10]`) and `max_position_embeddings 262144`.
  - Has 1 MTP (multi-token prediction) layer.
  - `vocab_size 65425`, with tied embeddings.
- **Vision encoder:** depth 12, hidden 768, 12 heads, `patch_size 16`, `spatial_merge_size 2`, output 1024.

**Surya 2.5 architecture** ([config.json](https://huggingface.co/datalab-to/surya-ocr-2.5/resolve/main/config.json))
- Same backbone, but `vocab_size 88526`, `mtp_num_hidden_layers 0` (no MTP head), and transformers 5.12.1.
- The model card says "689M param OCR model" / "~690M params", "Qwen3.5-style architecture", and a "character-level vocabulary". — [HF model card](https://huggingface.co/datalab-to/surya-ocr-2.5)
- The blog says the vocabulary grew to 88,526 tokens, adding emoji, styled math letters and ~20,000 common multi-character units, and that a page takes 2.6x fewer tokens to write. — [Datalab blog: Surya 2.5](https://www.datalab.to/blog/surya-2-5)
- The packaged README says the model is "trained on diverse document images to emit either a layout JSON or a full-page HTML output, depending on prompt" and credits Qwen3-VL. — README in `surya_ocr-0.22.1.dist-info/METADATA` (same text in the [GitHub README](https://github.com/datalab-to/surya))

**How tasks are handled.** Tasks are selected by fixed prompts, not by language tags. From `surya/inference/prompts.py` (v0.22.1, local):
- `BLOCK_PROMPT = "OCR this block image to HTML."`
- `HIGH_ACCURACY_BBOX_PROMPT = "OCR this image to HTML. Each block is a div with data-label and data-bbox (x0 y0 x1 y1, normalized 0-1000)."`
- A layout JSON prompt and a table-rec prompt.
- The file says: "The exact wording is the model's training-time contract — do not paraphrase without retraining."
- There is no language parameter in Surya 2.

**Uyghur and Arabic-script scores**
- Master `static/docs/multilingual.md` (Surya 2 / Surya 2.5):

  | Language | Surya 2 | Surya 2.5 |
  |---|---:|---:|
  | **Uyghur (ug)** | **34.1%** | **32.9%** |
  | Arabic | 46.0% | 45.4% |
  | Persian | 63.8% | 67.9% |
  | Urdu | 48.2% | 39.3% |
  | Pashto | 18.9% | 18.9% |
  | Sindhi | 53.9% | 52.1% |

  The overall score is 74.9% (Surya 2.5) vs 74.5% (Surya 2) over 36,089 tests. — [multilingual.md](https://raw.githubusercontent.com/datalab-to/surya/master/static/docs/multilingual.md)
- **Conflict:** the v0.22.1 README lists Arabic at **72.7%** and Persian at **82.3%**, with "87.2% across 91 languages". The newer table gives Arabic 46.0% for the same Surya 2 model, which suggests the benchmark was re-scored or made harder. Use the newer table for comparison. — v0.22.1 README (local METADATA) vs [multilingual.md](https://raw.githubusercontent.com/datalab-to/surya/master/static/docs/multilingual.md)
- The Surya 2.5 blog calls Arabic a hard case: 45.4% vs 46.0% for Surya 2, "essentially level". — [Datalab blog](https://www.datalab.to/blog/surya-2-5)

**Tokenizer test.** I ran the published `tokenizer.json` files locally with HF `tokenizers`.
- Both tokenizers are `WordLevel` with a pre-tokenizer of `Split` regex `[\s\S]`, so every character becomes one token. The decoder is `Fuse`, not byte-level BPE.
- Every Uyghur letter is a **single in-vocab token**, with identical IDs in both models: ئ U+0626, ە U+06D5, ۆ U+06C6, ۇ U+06C7, ۈ U+06C8, ۋ U+06CB, ې U+06D0, ى U+0649, ڭ U+06AD, ژ U+0698, ھ U+06BE, گ, چ, پ.
- Also in the vocab: combining hamza U+0654, tatweel, ZWNJ/ZWJ, the presentation forms U+FBEA and U+FEEB, `-`, soft hyphen U+00AD, and U+2010.
- The string "تۆخۇمى بەھۇداندە ئۇيغۇرچە كىتاب، ئۈرۈمچى" (40 chars) became 40 tokens and round-tripped exactly.
- The ~25k added tokens in Surya 2.5 contain **zero** Arabic-script multi-character units. — local test against [surya-ocr-2 tokenizer.json](https://huggingface.co/datalab-to/surya-ocr-2/resolve/main/tokenizer.json) and [surya-ocr-2.5 tokenizer.json](https://huggingface.co/datalab-to/surya-ocr-2.5/resolve/main/tokenizer.json)

**What Kitabim uses** (`/Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/`)
- `requirements.txt` pins `surya-ocr==0.22.1`, so Surya 2 and `datalab-to/surya-ocr-2`. The installed `surya/settings.py` has `SURYA_MODEL_CHECKPOINT = "datalab-to/surya-ocr-2"` and the GGUF repo `datalab-to/surya-ocr-2-gguf` (`surya-2.gguf` + `surya-2-mmproj.gguf`).
- `engine/recognize.py` calls `RecognitionPredictor()` with the default manager, which auto-spawns llama.cpp on a Mac or vLLM on a GPU. It then calls `predictor([image], full_page=True)`.
- When a full-page decode loops, it falls back to block mode: `predictor([image], [LayoutResult], full_page=False)`, which uses `BLOCK_PROMPT` on the crops.
- `engine/config.py` caps `SURYA_MAX_TOKENS_FULL_PAGE` at 2500 by default. The package default is 12288.

### Inferences
- Uyghur has full character coverage, so a tokenizer change is **not** needed to fine-tune for Uyghur. The weakness (~33-34%) is in visual and language modelling, not vocabulary. This removes the main risk older encoder-decoder OCR models carried.
- Surya 2.5 added multi-character units only for other scripts. Uyghur pages therefore still cost about one token per character, so they don't get the 2.6x compression and remain relatively long, loop-prone sequences.
- Kitabim's 2500-token full-page cap is about 2500 Arabic-script characters. A dense Uyghur page can exceed that, causing truncation that looks like a failure. Worth checking whether some "loops" or empty pages are really cap hits.
- Upgrading Kitabim to v0.23.0 / Surya 2.5 would not improve Uyghur accuracy (32.9 vs 34.1) but may reduce looping. Any fine-tune should pick one base model (2 or 2.5) and keep the prompt and chat template exactly as that version expects.

### Gaps
- Datalab has not documented the training data mix, how much Uyghur was in it, or the exact base checkpoint (built from scratch vs initialized from a Qwen3.5 checkpoint). The README says only "Qwen3.5-style architecture".
- I found no per-language breakdown of character error rate (CER). The scores are "pass rates" on an internal benchmark whose methodology is not described.

---

## Q2. Is there official or community training code?

### Takeaway
For **Surya 2 / 2.5 there is no official fine-tuning script**. The repo's `surya/scripts/` contains only inference, GGUF/MLX build and app scripts, and the README sends fine-tuning requests to hi@datalab.to. An official `finetune_ocr.py` did exist for the **old foundation model (v0.15 to v0.17)**, but it was buggy and is now obsolete. Fine-tuning Surya 2.x today would mean treating it as a standard Qwen3.5 VLM and using generic VLM SFT tooling (HF Trainer/TRL, Unsloth, ms-swift). That route is untested by Datalab.

### Cited Findings
- **Current repo tree (master):** `surya/scripts/` has `build_gguf.py`, `build_mlx.py`, `config.py`, `detect_layout.py`, `detect_text.py`, `ocr_text.py`, the streamlit and screenshot apps and `table_recognition.py`. No training or fine-tuning files exist. — [GitHub API tree](https://api.github.com/repos/datalab-to/surya/git/trees/master?recursive=1)
- **README "Training" section (v0.22.1 and master):** "If you want help finetuning Surya on your own data, or to use our managed training stack, reach us at hi@datalab.to." — [README](https://github.com/datalab-to/surya); [HF card surya-ocr-2.5](https://huggingface.co/datalab-to/surya-ocr-2.5)
- **The Surya 2.5 card and blog** give no fine-tuning recipe. — [HF card](https://huggingface.co/datalab-to/surya-ocr-2.5); [blog](https://www.datalab.to/blog/surya-2-5)
- **The model loads in plain transformers:** `AutoProcessor.from_pretrained("datalab-to/surya-ocr-2.5")` and `AutoModelForMultimodalLM.from_pretrained(...)`, then `apply_chat_template` with an image plus a text prompt, then `generate`. — [HF card](https://huggingface.co/datalab-to/surya-ocr-2.5)
  - Both repos ship `chat_template.jinja`, `processor_config.json`, `preprocessor_config.json`, `tokenizer.json` and a single `model.safetensors`. — [HF API surya-ocr-2](https://huggingface.co/api/models/datalab-to/surya-ocr-2); [HF API surya-ocr-2.5](https://huggingface.co/api/models/datalab-to/surya-ocr-2.5)

**Old official script (v0.15 to v0.17 only)**
- The README section "Finetuning Surya OCR" pointed to `surya/scripts/finetune_ocr.py`, built on the HF Trainer with all TrainingArguments, torchrun and deepspeed supported. The tested command was "Tested on 1xH100 GPU":

  ```
  python surya/scripts/finetune_ocr.py --output_dir $OUTPUT_DIR --dataset_name datalab-to/ocr_finetune_example --per_device_train_batch_size 64 --gradient_checkpointing true --max_sequence_length 1024
  ```

  Datalab described it as "a minimal training script". Their internal stack adds "character bounding box finetuning, sliding window attention with specialized attention masks, custom kernels, augmentations". — [v0.17.1 README](https://raw.githubusercontent.com/datalab-to/surya/v0.17.1/README.md)
- **What the script did** (126 lines): it built a dataset of `{image, text}` rows. It prepended script tokens computed by `get_top_scripts(text)` to the ground truth and used `TaskNames.ocr_with_boxes`. It truncated `input_ids/attention_mask/position_ids` to `max_sequence_length`, masked labels at the task BOS token, and loaded `SuryaModel` with `SuryaOCRProcessor`. Its arguments were `pretrained_checkpoint_path`, `dataset_name` (default `datalab-to/ocr_finetune_example`), `num_loading_proc=16`, `max_sequence_length` and `remove_unused_columns=False`. — [v0.17.1 finetune_ocr.py](https://raw.githubusercontent.com/datalab-to/surya/v0.17.1/surya/scripts/finetune_ocr.py)

**Bugs in the old script**
- **#465 (2025-09):** "Image tokens were present in the input but no input images were provided" and `NameError: SPECIAL_TOKENS`. Maintainer tarun-menta replied: "We updated the model and this script has gone out-of-sync. Will fix shortly." — [Issue #465](https://github.com/datalab-to/surya/issues/465)
- **#474 (2025-11):** `ValueError: input_ids, position_ids, and cache_position must be specified... provide either (image_tiles and grid_thw) or image_embeddings`.
  - User whynotkimhari posted a working fork at [whynotkimhari/surya finetune_ocr.py](https://github.com/whynotkimhari/surya/blob/master/surya/scripts/finetune_ocr.py).
  - Another user reported "no improvement in finetune model" after a workaround.
  - Another said "the fine_tune script provided in the code only works on version 15."
  - Source: [Issue #474](https://github.com/datalab-to/surya/issues/474)
- **#482 (2026-01):** the same error when fine-tuning on a Persian-digits dataset (`Dark6273/surya-persian-number`), while the example dataset worked. A second user hit "exactly the same problem with Persian text". There has been no maintainer answer. — [Issue #482](https://github.com/datalab-to/surya/issues/482)

**Community repos**
- [Ollsoft-ai/surya-finetuning](https://github.com/Ollsoft-ai/surya-finetuning) targets the old recognizer. It has a line-dataset generator plus a fine-tune folder. It is self-declared **deprecated**: "Surya OCR now has its own fine-tuning script... No future updates are planned." It was offered for the Arabic fine-tuning request in [Issue #294](https://github.com/datalab-to/surya/issues/294).
- [ketanmore/surya-layout-fine-tune-script](https://huggingface.co/ketanmore/surya-layout-fine-tune-script) is a **layout**-only notebook pinned to Surya v0.4.14 (commit f7c6c04), with no predefined loss. Its discussion thread includes someone asking how to fine-tune for Arabic, with no resolution.
- Long-standing open requests show demand but no official answer for the old models: #146 (2024), #189, #184, #58 (Ancient Spanish), #439 (Modi/Sanskrit script, asking how to add CER validation), and #43 / #32 (training details). — [GitHub issues search](https://github.com/datalab-to/surya/issues?q=finetune)

**Generic Qwen3.5 VLM tooling (applies to Surya 2.x architecture, not tested on Surya by anyone I found)**
- Unsloth supports vision fine-tuning of Qwen3.5 (0.8B to 27B) with bf16 LoRA. It reports ~3 GB VRAM for the 0.8B model. It advises **against QLoRA 4-bit** for Qwen3.5 because of quantization differences. Export to GGUF (llama.cpp) or vLLM is supported. It warns that the chat template and EOS token must match between training and inference. — [Unsloth Qwen3.5 fine-tune docs](https://unsloth.ai/docs/models/qwen3.5/fine-tune)

### Inferences
- Because Surya 2.x is a stock `Qwen3_5ForConditionalGeneration` checkpoint in safetensors, tools that support Qwen3.5-VL (Unsloth, TRL `SFTTrainer`, ms-swift, LLaMA-Factory) should be able to load and train it by pointing at `datalab-to/surya-ocr-2`. Surya-2.5 is similar with mild architecture adjustments.
- The fine-tuned model would then need converting to GGUF plus mmproj. Surya ships `surya/scripts/build_gguf.py` for this. Kitabim would then point at it with `SURYA_GGUF_LOCAL_MODEL_PATH` / `SURYA_GGUF_LOCAL_MMPROJ_PATH`, which are settings in v0.22.1 `surya/settings.py`. This is my inference from the code, not a documented workflow.
- The ~650M size is about the 0.8B Qwen3.5 tier, so Unsloth's ~3 GB bf16 LoRA footprint is a reasonable lower bound. A full fine-tune of 0.7B params in bf16 with AdamW needs roughly 0.7B × ~16 bytes ≈ 11-12 GB before activations, which fits a 24 GB GPU. That figure is my estimate, not a reported one.
- Do **not** use the v0.17 `finetune_ocr.py`, Ollsoft or whynotkimhari code with v0.22.1. They target the retired foundation model and an incompatible processor and checkpoint format.

### Gaps
- I found **no public report** (GitHub, HF, blogs) of anyone fine-tuning Surya 2 or 2.5 since May 2026. No hyperparameters, results or gotchas exist for the current model.
- It is unconfirmed whether the MTP layer (Surya 2) survives HF Trainer/PEFT round-trips and GGUF conversion. vLLM uses MTP for speculative decoding; Surya 2.5 has no MTP.
- Datalab's managed training stack (pricing, whether it handles Uyghur, whether weights are returned) is undocumented publicly.

---

## Q3. What input data format is needed? Line crops, blocks or full pages? How are RTL text and Arabic-script tokens handled?

### Takeaway
- **Old (≤0.17) recognizer:** trained on `{image, text}` rows. Images could be lines, blocks or full pages, and the text was plain with script tokens prepended automatically.
- **Surya 2.x:** a chat-format VLM. Training pairs must reproduce one of its prompt contracts:
  - **block mode:** a block crop, `"OCR this block image to HTML."`, and an HTML snippet as the target;
  - **full page:** a page image, the full-page prompt, and `<div data-label data-bbox>` HTML with 0-1000 normalized boxes.
- RTL is handled implicitly: text is emitted in logical (Unicode) order, one token per character. No special RTL token exists in 2.x.

### Cited Findings
- **Example dataset `datalab-to/ocr_finetune_example` (old script):**
  - Two columns, `image` and `text`, with 4 rows.
  - Images range from ~461 px wide to 4K.
  - Text is plain, with math as `<math display="inline|block">` LaTeX.
  - The card says Surya accepts full pages, cropped blocks and single lines, and that they can be mixed.
  - Source: [HF dataset](https://huggingface.co/datasets/datalab-to/ocr_finetune_example)
- **The old script prepended script tokens:** `gt_text = self.get_script_text(gt_text) + gt_text`, using `SCRIPT_TOKEN_MAPPING`. — [v0.17.1 finetune_ocr.py](https://raw.githubusercontent.com/datalab-to/surya/v0.17.1/surya/scripts/finetune_ocr.py)

**Surya 2.x prompt and output contract** (v0.22.1, local `surya/inference/prompts.py`)
- `BLOCK_PROMPT = "OCR this block image to HTML."` and the full-page `HIGH_ACCURACY_BBOX_PROMPT` with `data-label` and `data-bbox` in 0-1000 normalized coordinates.
- `ALLOWED_TAGS` includes p, br, div, span, table, h1-h5, math, b, i and others. `ALLOWED_ATTRIBUTES` includes `data-bbox`, `data-label` and `class`.
- Layout labels are Text, Section-Header, Page-Header, Page-Footer, Footnote, List-Group, Table, Table-Of-Contents and others.
- The comment says: "do not paraphrase without retraining."

**How the predictor uses Surya 2.x** (v0.22.1, local `surya/recognition/__init__.py`)
- `RecognitionPredictor` runs full-page OCR (one VLM call per page). Alternatively, given a `LayoutResult`, it crops each block with 4 px padding (`_crop_block`) and runs `BLOCK_PROMPT`.
- It drops blank text blocks that it identifies as hallucinated.
- An optional full-page regeneration schedule retries at temperature `min(0.2*(n+1),0.8)` with top_p 0.95, for up to 6 rounds (`SURYA_FULLPAGE_REGEN`).
- In 2.x, line-level text detection is a **separate** EfficientViT segformer. The VLM does not take detected line images by default; it reads whole pages or layout blocks. — README "Training" section (local METADATA / [GitHub](https://github.com/datalab-to/surya))

**Tokenizer handling of Uyghur:** every Uyghur letter, including hamza-seat ئ (U+0626) and the combining hamza U+0654, is a single token. Text is split character by character, with no byte fallback. — local tokenizer test, [surya-ocr-2 tokenizer.json](https://huggingface.co/datalab-to/surya-ocr-2/resolve/main/tokenizer.json)

**Earlier RTL complaints (0.x only)**
- [Issue #431](https://github.com/datalab-to/surya/issues/431) is a feature request: "words_from_chars RTL and LTR adaption".
- In [Issue #294](https://github.com/datalab-to/surya/issues/294), a Hebrew user reports that look-alike letters get swapped and that right-aligned table-of-contents headers are dropped to the end of the line.

### Inferences
- For Kitabim, the most practical Surya 2.x fine-tune is in **block mode**. Kitabim already has page images plus corrected Uyghur text, which can be cut into paragraph or block crops. Train on (crop, `"OCR this block image to HTML."`, `<p>…</p>` target). Block crops avoid having to produce correct `data-bbox` values.
  - A full-page fine-tune would also need correct layout labels and normalized boxes for every block. Without them, the model's full-page behaviour could break.
  - Mixing in some full-page examples labelled with the current model's own boxes (corrected text only) would help preserve full-page mode. This is my inference.
- Ground truth must be in **logical Unicode order** with standard Uyghur code points: U+06D5 ە (not U+0647 ه), U+06C6/U+06C7/U+06C8, U+0649 ى (not U+064A for final ى). It must not contain presentation forms. Inconsistent normalization in targets will teach the model inconsistent outputs.
- Line-end hyphens: the vocab contains `-`, U+2010 and the soft hyphen. Whatever convention the targets follow (keep the glued hyphen, or de-hyphenate), the model will learn it. Kitabim does de-hyphenation in the OCR client (`engine/text_cleanup.py`), so targets should be the raw printed text, keeping hyphens, so the existing cleanup stays valid.

### Gaps
- Datalab has not published whether Surya 2's own training targets for Arabic-script blocks use `<p dir="rtl">` or other attributes. Inspecting raw model output on Uyghur pages would show the convention to copy. Kitabim's `recognize.py` already parses the HTML output.
- I found no public Uyghur OCR fine-tuning dataset formatted for Surya.

---

## Q4. What hyperparameters, GPU memory and dataset sizes have been reported? LoRA or full fine-tune? Can the encoder be frozen?

### Takeaway
Almost nothing has been reported. The only official number is from the **old** script: 1×H100, batch 64, gradient checkpointing, max_sequence_length 1024. No one has reported Surya 2.x fine-tuning numbers. The generic Qwen3.5-0.8B guidance is bf16 LoRA at ~3 GB VRAM and no QLoRA.

### Cited Findings
- **Old official settings:** "Tested on 1xH100 GPU", `--per_device_train_batch_size 64 --gradient_checkpointing true --max_sequence_length 1024`. — [v0.17.1 README](https://raw.githubusercontent.com/datalab-to/surya/v0.17.1/README.md)
- **Old-model user reports:** one user saw "no improvement" after a patched fine-tune on local data ([#474](https://github.com/datalab-to/surya/issues/474)). Another asked how to add train/val CER callbacks ([#439](https://github.com/datalab-to/surya/issues/439)). No dataset sizes or CER deltas were reported.
- **Qwen3.5 LoRA VRAM (Unsloth):** 0.8B: 3 GB, 2B: 5 GB, 4B: 10 GB, 9B: 22 GB. QLoRA is not recommended. — [Unsloth docs](https://unsloth.ai/docs/models/qwen3.5/fine-tune)
- **Inference memory reference:** Surya 2's vLLM defaults are `VLLM_MAX_MODEL_LEN=18000`, `VLLM_GPU_MEMORY_UTILIZATION=0.85` and `VLLM_DTYPE=bfloat16`, with a note that Turing cards such as the T4 need float16. Throughput is 5.35 pages/s on an RTX 5090 at concurrency 128, and 0.108 pages/s on Apple Silicon via llama.cpp. — local `surya/settings.py` and README (v0.22.1)

### Inferences
- The model is a separable ViT encoder (12 layers, 768-d) plus a merger plus a 24-layer decoder. **Freezing the vision encoder** and training the decoder (LoRA or full) is mechanically straightforward with PEFT target modules or `requires_grad=False` on `model.visual`.
- For a new script style (Uyghur print fonts, old scans), the visual side is probably part of the problem. Datalab's low Uyghur score despite full vocab coverage points that way. Training at least the merger and the upper vision layers, or applying LoRA to vision attention too, is advisable. This is an inference, untested.
- The sequence length for block crops is short, a few hundred tokens. Full pages are long: Uyghur at one token per character can be 2-4k+ tokens. Each image also costs tokens: with patch 16 and merge 2, one token covers a 32×32 px region, so a 1000×1400 page is about 1.4k image tokens.

### Gaps
- No public dataset-size or CER-improvement data exists for any Surya 2.x fine-tune.
- No public guidance from Datalab exists on learning rate, epochs, or catastrophic forgetting of layout and table tasks.

---

## Q5. What are the known issues? Hallucination and repetition, hyphens, Arabic-script accuracy, and issues filed for Uyghur, Persian, Urdu and Arabic.

### Takeaway
Repetition loops are a known Surya 2 failure mode. Datalab measured 3.8% of requests hitting the output cap with MTP, and says Surya 2.5 cut this to 0.1%. A Uyghur-specific bug filed on v0.22.1 (#561) shows exactly this on dense two-column Uyghur pages. Arabic-script languages are Surya's weakest group, and no GitHub issue mentions hyphens.

### Cited Findings
- **Loop rates:** "It almost never loops (0.1% of requests reach the output limit at 192 DPI, against 3.8% for Surya 2 with MTP)." — [v0.23.0 release](https://github.com/datalab-to/surya/releases/tag/v0.23.0); [blog](https://www.datalab.to/blog/surya-2-5)
- **Issue #561 (closed, filed 2026-09-18)**, "Surya fails on the left column of a dense Uyghur two-column contents page":
  - Environment: v0.22.1, llama.cpp, macOS Apple Silicon, full-page mode, ctx 20488.
  - The right column OCRs fine. The left column gives "No text recognized on a non-blank page", and smaller crops give "runaway repetition/reasoning-leak loop".
  - The page has dense small text, dotted leaders and page numbers.
  - The issue was closed with 0 comments.
  - Source: [Issue #561](https://github.com/datalab-to/surya/issues/561)
- **Surya 2's own mitigations** (v0.22.1 local code):
  - A block-mode fallback "only fires on page-length repetition loops", per a Kitabim comment in `engine/recognize.py`.
  - A blank-region filter drops hallucinated text blocks in margins (`_drop_blank_text_blocks`).
  - An opt-in regeneration at rising temperature (`SURYA_FULLPAGE_REGEN`).
- **Other loop-related issues:** [#544](https://github.com/datalab-to/surya/issues/544) (text inside Figure/Diagram regions is never OCR'd in full_page mode) and [#555](https://github.com/datalab-to/surya/issues/555) (nothing happens on starting OCR).
- **Arabic-script issues (mostly 0.x):**
  - [#294](https://github.com/datalab-to/surya/issues/294): fine-tuning for Arabic, poor results on Arabic scans.
  - [#28](https://github.com/datalab-to/surya/issues/28): Arabic detection with mixed font sizes.
  - [#344](https://github.com/datalab-to/surya/issues/344): the Arabic character list.
  - [#508](https://github.com/datalab-to/surya/issues/508): an output bug involving Arabic and Persian, 2026-04.
  - [#545](https://github.com/datalab-to/surya/issues/545): the bbox schema regex used `\d`, which matches non-ASCII digits such as Arabic-Indic numerals; fixed to `[0-9]`.
  - [#6](https://github.com/datalab-to/surya/issues/6): Urdu not detected, 2024, closed.
- **Hyphens:** searching the repo's issues for "hyphen" returned 0 results. — [GitHub issue search](https://github.com/datalab-to/surya/issues?q=hyphen)
- **Hacker News anecdote:** an Arabic practitioner said Surya, Tesseract and a fine-tuned Nougat did not match Google OCR on Arabic. — [HN comments by aliosm](https://news.ycombinator.com/threads?id=aliosm) (surfaced via a search mirror; secondary source)

### Inferences
- The 2500-token cap in Kitabim's client may make dense Uyghur pages look like loops, because each character is one token. Separating "hit cap" from "looped" in logs would help tell model failures from configuration limits.
- Fine-tuning on dense Uyghur blocks, including table-of-contents pages with dotted leaders, directly targets the #561 failure class.

### Gaps
- I found no Datalab statement on whether Surya 2.5's looping reduction holds for Arabic-script text, which gets no token compression.
- I found no public measurement of Surya's CER on Uyghur specifically, beyond the ~33-34% pass rate.

---

## Q6. What do the licence terms mean for fine-tuning and using derived weights?

### Takeaway
The code is Apache-2.0. The weights for Surya 2 and 2.5 use a **modified OpenRAIL-M**: free for research, personal use, and organizations under $5M revenue **and** under $5M raised. It **forbids use by anyone offering a product or service that competes with Datalab**. Fine-tuned weights count as "Derivatives of the Model" and inherit the licence through a **share-alike** clause, including attribution and the use restrictions.

### Cited Findings
- **Headline terms:** "The Surya code is licensed under Apache 2.0. The model weights use a modified AI Pubs Open Rail-M license (free for research, personal use, and startups under $5M funding/revenue)." HF metadata lists `license: openrail`. — [README](https://github.com/datalab-to/surya); [HF API](https://huggingface.co/api/models/datalab-to/surya-ocr-2.5)
- **Commercial restrictions (LICENSE, Attachment A, §2).** Use is forbidden:
  - (a) "if You (your employer, or the entity you are affiliated with) generated more than five million US Dollars ($5,000,000) in gross revenue in the prior year, except where Your Use is limited to personal use or research purposes";
  - (b) the same for more than $5M "total equity or debt funding";
  - (c) "for any purpose if You ... provides or otherwise makes available any product or service that competes with any product or service offered by or made available by Licensor or any of its affiliates."

  Source: [surya-ocr-2.5 LICENSE](https://huggingface.co/datalab-to/surya-ocr-2.5/resolve/main/LICENSE)
- **Fine-tuning is explicitly a covered use.** "Use may include creating any content with, fine-tuning, updating, running, training, evaluating and/or re-parametrizing the Model." "Derivatives of the Model" include modifications and models trained by distillation or on synthetic data generated by the Model. — [LICENSE](https://huggingface.co/datalab-to/surya-ocr-2.5/resolve/main/LICENSE)
- **Share-alike (§8):** "You agree to apply this License (to the exclusion of all others) to any and all copies of the Model, Derivatives of the Model... and to the Output and any derivatives... of the Output." — [LICENSE](https://huggingface.co/datalab-to/surya-ocr-2.5/resolve/main/LICENSE)
- **Attribution (§7)** applies to Output and Distribution. **Distribution (§4)**, including hosting as a service, requires passing on the use restrictions and a copy of the licence. — [LICENSE](https://huggingface.co/datalab-to/surya-ocr-2.5/resolve/main/LICENSE)

### Inferences
- A Kitabim fine-tune would remain under Datalab's licence. If Kitabim (or its operating entity) exceeds $5M revenue or funding, or is judged to offer a competing product (Datalab sells document OCR and parsing), a commercial licence is needed.
- §8 extends the licence to **Output** as well. Text produced by Surya and stored in Kitabim's corpus arguably carries the share-alike and attribution obligations. Kitabim should get a legal reading before publishing or redistributing fine-tuned weights or OCR'd corpora at scale.
- Any distillation, such as using Surya output to train a different OCR model, is also captured by the "Derivatives" definition.

### Gaps
- I found no public Datalab guidance on what counts as "competes". The licence text as reviewed is from the 2.5 repo; I did not diff the Surya 2 `LICENSE`, but both repos declare `openrail`.

---

## Q7. What are the alternatives if fine-tuning Surya is impractical? (brief)

### Takeaway
The closest drop-in alternative is to fine-tune an **Apache-licensed small VLM of the same architecture family**, such as Qwen3.5-0.8B or 2B, with Unsloth or TRL LoRA. That gives the same training mechanics without Datalab's licence. Classic per-line OCR engines (Kraken, Tesseract LSTM, PaddleOCR rec) are cheaper to train on Uyghur line crops but need a separate line-detection and layout stage.

### Cited Findings
- **Qwen3.5 VLM fine-tuning:** Unsloth supports 0.8B to 27B vision LoRA (0.8B ≈ 3 GB VRAM, bf16; QLoRA discouraged), with export to GGUF and vLLM. — [Unsloth docs](https://unsloth.ai/docs/models/qwen3.5/fine-tune)
- **Surya 2's README benchmark table** lists comparable small open OCR VLMs on olmOCR-bench:
  - LightOnOCR 2-1B: 83.2 (different methodology);
  - dots.mocr 3B: 83.9;
  - Datalab's Chandra OCR 2 (4B): 85.9;
  - GOT OCR 0.6B: 48.3.

  Source: v0.22.1 README (local METADATA / [GitHub](https://github.com/datalab-to/surya))
- **Kitabim's own history:** PaddleOCR was spiked and fully removed on 2026-10-03, and Kitabim settled on Surya. This comes from project memory (`kitabim_ocr_engine_choice.md`), not from an external source.

### Inferences
- Because Surya 2.x *is* a Qwen3.5-architecture VLM, the engineering work (data prep in chat format, LoRA, GGUF export) is almost the same for Surya and for a base Qwen3.5 model. The decision comes down to two things:
  - **Starting accuracy:** Surya's document pretraining vs Qwen's general vision-language pretraining, measured on a held-out Uyghur set.
  - **Licence:** OpenRAIL-M with a $5M cap and a non-compete, vs Apache-2.0.
- Kraken/eScriptorium and Tesseract LSTM have mature Arabic-script line-training workflows. They suit a line-crop dataset, which Kitabim could derive from Surya's detector boxes plus corrected text.

### Gaps
- The Uyghur accuracy of Qwen3.5 base, LightOnOCR, dots.mocr and Chandra is unmeasured here.
- I did not research Kraken, Tesseract or PaddleOCR Uyghur training specifics, per the brief's "brief only" scope.
