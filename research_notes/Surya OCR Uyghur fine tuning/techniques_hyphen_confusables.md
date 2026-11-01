# Techniques to fix line-end hyphen hallucination and confusable-diacritic errors in Surya-based Uyghur OCR

Scope note: the local client pins `surya-ocr==0.22.1` (clients/kitabim-ocr/requirements.txt). The current Surya GitHub README describes OCR as a shared ~690M-param "Qwen3.5-style" vision-language model. I did not verify which architecture 0.22.1 uses (see Gaps). Either way it is an autoregressive decoder with a language prior, which is the mechanism behind failure mode 1.

Evidence-strength legend: **[Strong]** peer-reviewed or primary paper with measured results. **[Moderate]** primary source or preprint, or tool docs without ablation. **[Weak]** thesis listing, forum, self-reported small test, or search snippet I did not open.

## 1. Synthetic data generation for Arabic-script line OCR (tools, fonts, degradation, hyphen fragments)

### Takeaway
Render with a real OpenType shaping stack (HarfBuzz via Pango or Pillow+Raqm), never with arabic_reshaper+bidi on top of Raqm, and degrade the ink layer (dilation/erosion, blur, bleed-through, JPEG) so that dots and marks are realistically lost or merged. No source I found studies synthetic line-end hyphen fragments, so that recipe is an engineering inference. It is cheap to build: render a fragment plus a hyphen and use the literal fragment plus hyphen as the label.

### Cited Findings
- Pillow wheels have bundled libraqm since 8.2, but libraqm loads FriBiDi at runtime, so the same wheel can be Raqm-enabled on one machine and not on another. Use `PIL.features.check("raqm")` to detect it. When Raqm is active, the common "arabic_reshaper + python-bidi" preprocessing double-processes the text and garbles it: reshape+bidi broke 14 of 15 test renders (5 strings × 3 fonts). Without Raqm, reshaping only partly helps, and diacritics, digits, and embedded Latin still fail. **[Weak: small self-reported test, filed upstream as python-arabic-reshaper#102]** — [HF discussion, arshape](https://huggingface.co/datasets/syamjithnk/arshape/discussions/2)
- An Arabic/Persian fork of TextRecognitionDataGenerator (trdg) exists, but I could not confirm how it shapes text. A separate Arabic synthetic generator depends on arabic_reshaper+bidi and may hit the same bug. — [amirmgh1375/TextRecognitionDataGenerator](https://github.com/amirmgh1375/TextRecognitionDataGenerator); [HGamal11/Arabic_Synthetic_Data_Generator](https://github.com/HGamal11/Arabic_Synthetic_Data_Generator)
- Persian Pixel (arXiv 2607.20385) uses SynthOCR-Gen, which pairs "a full OpenType shaping stack with a configurable degradation pipeline." It has 7 fonts (Vazirmatn, Sahel, Shabnam, Amiri, IranNastaliq, plus 2 unnamed), 343,246 image–text pairs, and more than 25 stochastic operators. The operators are geometric (rotation ±5°, shear, perspective, scale), photometric, noise/blur (Gaussian, salt-and-pepper, Poisson, speckle, motion and Gaussian blur, median), and document-specific (ink bleed via dilation, erosion/dilation for stroke width, yellowed paper, scan lines, random erasing, shadows). The paper argues that letters sharing a skeleton and differing only in dots are fragile under degradation, but it reports **no model, no CER, and no ablation**. **[Moderate for recipe, None for effectiveness]** — [Persian Pixel](https://arxiv.org/html/2607.20385)
- SynthOCR-Gen is an open-source generator for low-resource languages that segments text at character, word, n-gram, sentence, and line levels. Its demonstration is for Kashmiri, and Uyghur support is not confirmed. — [SynthOCR-Gen (arXiv 2601.16113)](https://scour.ing/p/https:/arxiv.org/abs/2601.16113)
- QARI-OCR (Qwen2-VL-2B fine-tuned on synthetic Arabic) scaled data in stages: v0.1 had 5k samples with no diacritics, and v0.2 had 50k samples with full diacritics and 10 fonts. Each image got one of three degradation levels to mimic scanning. In the SARD benchmark, Qari v0.2 had the best WER and BLEU, but it was fine-tuned on held-out SARD data while the other models ran zero-shot, so the comparison is not like-for-like. The model card warns that 4-bit quantization is not recommended for fine-grained recognition, which matters for dots and marks. **[Moderate]** — [QARI-OCR](https://arxiv.org/html/2506.02295v1); [SARD summary](https://www.emergentmind.com/topics/sard)
- Cross-Lingual SynthDocs randomly removes diacritics (light, medium, or heavy) and inserts them, to vary diacritic density. **[Moderate, no isolated ablation]** — [Cross-Lingual SynthDocs](https://arxiv.org/pdf/2511.04699)
- The Augraphy pipeline extracts an "ink" layer, degrades it in an Ink Phase (BleedThrough, LowInkLines, InkBleed, InkMottling), generates a Paper Phase separately, then merges and adds post-effects such as folds and shadows. The BleedThrough example uses intensity (0.1, 0.2) and kernel (17, 17). The Synth-JDoc Japanese OCR dataset uses InkBleed and InkMottling for robustness. The current PyPI version is 8.2.4, and the API may differ from the 2022 paper. **[Moderate: tool docs, no OCR ablation found]** — [Augraphy paper](https://arxiv.org/pdf/2208.14558); [BleedThrough docs](https://augraphy-doc.readthedocs.io/en/latest/_sources/doc/source/augmentations/bleedthrough.rst.txt); [Synth-JDoc](https://arxiv.org/pdf/2608.28248)
- Nougat's image augmentations are erosion, dilation, Gaussian noise, Gaussian blur, bitmap conversion, image compression, grid distortion, and elastic transform. — [Nougat](https://arxiv.org/pdf/2308.13418)
- UTRSet-Synth (Urdu, 20k lines) uses a custom generator that controls font, size, colour, resolution, orientation, noise, style, and background. It is a template for a Perso-Arabic line set. — [UTRNet paper](https://cdn.iiit.ac.in/cdn/ilocr.iiit.ac.in/dataset/static/assets/img/publication/printed/UTRNet.pdf)
- Uyghur fonts: the UKIJ family (Uyghur Computer Science Association) includes UKIJ Tuz, Tuz Tom, Ekran, Kufi, Diwani, and others. It is licensed under OFL/LGPL and packaged as Debian `fonts-ukij-uyghur`. UKIJ Ekran was designed for screen and installer UI, not book text. ALKATIP Basma and ALKATIP Gezit Tom are also cited as popular Uyghur fonts. — [Luc Devroye Uyghur type page](https://luc.devroye.org/uyghur.html); [Debian ITP](https://lists.alioth.debian.org/pipermail/pkg-fonts-devel/2011-April/006461.html); [Uyghur Font Beautifier listing](https://chromeboard.com/extension/uyghur-font-beautifier-cahlkmoiibhnfbdkhboicpdjhpgihfod)
- An MDPI Uyghur scene-text paper trained an improved CRNN on synthetic data from a self-built random-text generator. The dataset may not be public. A Hugging Face dataset "Uyghur_OCR_SUST_RUST" exists, but its provenance (real or synthetic) is unverified. — [MDPI](https://www.mdpi.com/1719886); [HF dataset](https://huggingface.co/datasets/lht12311/Uyghur_OCR_SUST_RUST)
- Hyphen transcription conventions: TEI/diplomatic practice records line-end hyphens explicitly, and the Balisage paper calls "transcribe the word as if whole" inaccurate. Crowd-transcription forums, by contrast, recommend rejoining words for searchability. Tesseract ground-truth lines must have no leading or trailing spaces. — [Balisage, Soft hyphens](https://balisage.net/Proceedings/vol17/html/Bauman01/BalisageVol17-Bauman01.html); [DTA guidelines](https://kaskade.dwds.de/~haaf/dtabf_en/silbentrennung.html); [Open History Hub](https://openhistoryhub.com/t/how-to-deal-with-split-words-with-hyphens/18999); [tesstrain #335](https://www.github.com/tesseract-ocr/tesstrain/issues/335)

### Inferences
- **Hyphen-fragment synthesis recipe (my design, unsourced).** Take running Uyghur text, wrap it to a line width, and for X% of lines (for example 20–30%) force a break inside the last word at a random point. Use syllable boundaries if a hyphenation rule is available, otherwise random points. Render the prefix followed by "-" at the visual line end, which is the leftmost position in RTL. Label = logical-order text ending with prefix + "-". Also render the matching next line that starts with the word's suffix (label = suffix ...). This teaches both halves as non-words.
  - Watch the shaping. A prefix before "-" must shape in its isolated or final form, because the hyphen is non-joining. HarfBuzz does this automatically if you shape the string "prefix-" rather than drawing glyphs by hand.
  - The label convention must match the convention in the real ground truth. The project's clean-up step already de-hyphenates in the client, so the model output should keep the hyphen.
  - Include both glued hyphens ("prefix-") and spaced hyphens ("prefix -"), plus variants with U+2010 or U+2011, Arabic tatweel, or en-dash, if those appear in the target books.
- **Random-cut fragments are the key ingredient.** They are, by construction, out-of-vocabulary strings, which directly counters the decoder's "complete the word" prior (see §3).
- **Diacritic-preserving degradation.** Apply dilation, erosion, and blur at strengths that sometimes do and sometimes do not destroy the marks on و/ۇ/ۆ/ۈ/ۋ. Keep the label as the true letter, but cap the strength (or check by re-rendering) so that you do not teach the model to read illegible marks as a specific letter. If a mark is truly destroyed, the image is label-noise. Prefer moderate kernels (for example 2–3 px at 300 DPI-equivalent) and downsample to 150–200 DPI equivalents to mimic low-resolution scans.
- **Font choice.** Prioritise the faces actually used in the scanned Uyghur books (likely UKIJ Tuz/Tuz Tom/Basma-like Naskh book faces and ALKATIP families). Ekran is a UI face and is lower priority. Collect font identity per book from the corpus if possible.

### Gaps
- I found no paper that measures the effect of dot- or diacritic-specific augmentation on Arabic-script dot-confusion error rates. Persian Pixel explicitly motivates it but reports no results.
- I found no published method or ablation for training on synthetic line-end hyphen fragments.
- "Alp Ekran" as a font name was not found in any source. SynthTIGER and synthdog were not researched in depth: no Arabic-shaping evidence was found for either.

## 2. Hard-example / confusion-focused data (oversampling, minimal pairs, weighted loss, curriculum)

### Takeaway
Evidence favours **data-side** fixes (targeted augmentation and synthesis of rare or confusable classes) over loss reweighting, which can hurt majority classes. Focal-style loss helped in one CTC study. Nothing I found tests minimal-pair synthesis for Arabic-script diacritics specifically.

### Cited Findings
- Fusing focal loss into CTC for Chinese OCR, to emphasise low-frequency samples, outperformed plain CTC by 3–9 percentage points of accuracy on average. **[Moderate; CTC, not seq2seq]** — [Complexity 2019 via DOAJ](https://doaj.org/article/8fc834f8bc5c4bb5ab5c93873dee3364)
- An oracle-bone character survey notes that network-side imbalance fixes (decoupled learning, DMC) can reduce majority-class performance. It presents data augmentation and generation (for example Diff-Oracle diffusion) as ways to boost minority classes without that cost. **[Moderate, survey]** — [Oracle character recognition survey](https://arxiv.org/pdf/2411.11354)
- For Hangul, decomposing characters into components was proposed to address long-tail class imbalance. This is analogous to treating base letter + mark separately. — [Character decomposition, Hangul OCR](https://arxiv.org/pdf/2208.06079)
- Persian Pixel identifies dot count and placement as the central confusion source for shared-skeleton letters, but does not test remedies. — [Persian Pixel](https://arxiv.org/html/2607.20385)

### Inferences
- **Minimal-pair synthesis (unsourced design).** From a Uyghur word-frequency list, find real words containing ۇ/ۆ/ۈ/و/ۋ, ز/ژ, ي/ې, ك/ڭ/گ. Render real lines containing them, and oversample them (for example 3–5×) relative to their natural frequency. Also generate "swap" strings where one confusable letter is replaced (ئۇ→ئۆ) so that the model sees the same skeleton with different marks and must rely on the mark. Swapped words are non-words, which also helps §3. Keep swaps to a minority of the data (for example under 10%) to avoid distorting the language prior too much.
- **Exploit Uyghur's Unicode decomposition.** Uyghur letters are pre-composed code points, not base + combining mark, so tokenisation sees ۇ and ۆ as unrelated tokens. Upweighting is per token. If Surya's training loop allows per-token loss weights, a modest weight (for example 2×) on the confusable code points is a cheap experiment. Check against the full-CER regression.
- **Curriculum.** Start with clean renders, then increase degradation, mirroring QARI's staged v0.1→v0.2 approach ([QARI-OCR](https://arxiv.org/html/2506.02295v1)). The staging there was not ablated.
- **Hard-example mining from real data.** Run the current model on real lines, compute per-line confusable-character errors against corrected GT, and oversample those lines. This is standard practice, not sourced specifically here.

### Gaps
- No quantified study of oversampling or minimal pairs for Arabic-script dot/diacritic confusions was found.
- No evidence on class-weighted cross-entropy in transformer OCR decoders specifically.

## 3. Reducing decoder language-model hallucination in seq2seq OCR

### Takeaway
The best-supported training-time fixes are **target-side perturbation** (randomly replace or skip ground-truth tokens: Nougat, LOCR) and **non-word/random-text training data**, which weakens the prior that "completes" words. Larger VLM decoders over-normalise more than small TrOCR-style decoders. Since the current Surya is a VLM, its prior risk is likely higher than an old TrOCR baseline.

### Cited Findings
- **Nougat** randomly replaces ground-truth tokens during training (a perturbation), which "significantly reduced" collapse into repetition loops. At inference it flags repetitive output via a moving average of logits that crosses a threshold. **[Strong-ish: primary paper, effect reported qualitatively]** — [Nougat](https://arxiv.org/pdf/2308.13418); detection described in [ÉCLAIR](https://arxiv.org/pdf/2502.04223)
- **LOCR** randomly skips 0–5 tokens (and their positions) in the ground truth during training, and reports this has "a more pronounced effect" than Nougat's replacement. **[Moderate: authors' own claim]** — [LOCR](https://arxiv.org/pdf/2403.02127)
- On ~10k historical English lines (trained on ~195k lines: 62k manual, 68k aligned, 65k synthetic), Qwen2.5-VL-7B beat TrOCR-large on CER (0.60% vs 1.05%). Qwen showed **lexically motivated over-normalisation** ("Antient"→"Ancient", "imploy"→"employ", "rigorouſly"→"merely"), while TrOCR errors stayed visually grounded but cascaded on long lines. Short lines were hardest for both (CER 3.93% Qwen, 5.79% TrOCR). Edit distance 1–2 covers about 78–82% of errors. Many real-word errors pass dictionary checks, which limits lexical post-correction. **[Strong: measured]** — [Error Patterns in Historical OCR (arXiv 2602.14524)](https://arxiv.org/html/2602.14524)
- PAR (ACL 2026) is a training-free inference method. It applies positional perturbation during decoding to reduce over-reliance on long-range context, which the paper names as the cause of "linguistic priors hallucination" (over-correction toward the internal language distribution). **[Moderate: targets MLLMs]** — [ACL 2026 long.1065](https://aclanthology.org/2026.acl-long.1065.pdf)
- "Seeing is Believing?" builds a degraded-document OCR-hallucination benchmark (KIE-HVQA). Its Qwen2.5-VL-7B-based model reports about 28% absolute improvement in hallucination-free accuracy over GPT-4o. It targets VQA-style extraction, not line OCR. — [arXiv 2506.20168](https://arxiv.org/html/2506.20168v2)
- Re-balancing contrastive decoding is another VLM-hallucination mitigation (general, not OCR-specific). — [arXiv 2409.06485](https://arxiv.org/pdf/2409.06485)

### Inferences
- **Highest-leverage fix for failure mode 1:** make line-end fragments common in training (§1). The model's prior then predicts "fragment + hyphen" at line end instead of a completed word. Add a share of random-character and random-syllable Uyghur lines (for example 5–15%) to further decouple reading from the prior. This is common practice in synthetic OCR, but I found no Uyghur-specific measurement.
- **Apply Nougat/LOCR-style target perturbation** (replace or skip a few % of target tokens) when fine-tuning Surya. This needs access to the training loop.
- **Inference-side checks.** Use greedy decoding (no sampling) and a length check (output char count vs. line image width/aspect ratio, flagging lines whose output is implausibly long). Use per-token confidence where available, and re-OCR low-confidence line-end tokens on a crop. Repetition penalties target looping, not single-word completion, so they are unlikely to fix failure mode 1.
- Short lines are the worst case for both architectures. Hyphenated last lines of paragraphs and short fragments deserve their own test slice.

### Gaps
- No paper measures "word completion of hyphenated fragments" as a hallucination type.
- I could not confirm whether surya-ocr 0.22.1 exposes per-token confidences or a supported fine-tuning script. The README has no training scripts and offers fine-tuning via datalab's managed service. Community resources: [datalab-to/ocr_finetune_example](https://huggingface.co/datasets/datalab-to/ocr_finetune_example) (image + text columns; pages, blocks, or lines can be mixed) and [Eleven19/arabic-surya-training](https://huggingface.co/datasets/Eleven19/arabic-surya-training) (439 Arabic block images, Colab, T4 for about 2–3 h, for "Surya OCR v1"). — [Surya README](https://github.com/datalab-to/surya)
- No evidence was found for constrained or lexicon-constrained decoding inside Surya.

## 4. Aligning noisy page-level text to line images; pseudo-labelling / self-training

### Takeaway
The proven Arabic-script recipe (KITAB/OpenITI) is: run an OCR to get line boxes and noisy line text, then align it with the clean page text (passim text-reuse alignment) and assign the clean span to each line. Pseudo-labelling works but needs care, because confidence filters bias against rare and hard lines, which are exactly the confusable-letter and hyphen lines this project needs.

### Cited Findings
- KITAB aligns clean OpenITI transcriptions with noisy Kraken OCR using **passim**. The OCR gives line positions, so the aligned clean text becomes approximate line ground truth, yielding (clean text, line image) pairs for training. The pipeline used Kraken 3.0.0.0b21 and the `ArabPersGeneralized` model. **[Moderate: project write-up]** — [KITAB: OpenITI, OCR and Textual Criticism](https://kitab-project.org/OpenITI,-OCR,-and-Textual-Criticism/); [KITAB OCR corpus](https://kitab-project.org/corpus/ocr)
- Kraken trains on line-image/line-text pairs. `ketos linegen` renders text to lines, and `ketos extract` pulls line pairs from corrected transcriptions. eScriptorium supports correcting lines and training Kraken from them. **[Moderate]** — [Digital Orientalist, Using Kraken](https://digitalorientalist.com/2019/11/05/using-kraken-to-train-your-own-ocr-models/); [eScriptorium/IIIF slides](https://projet.biblissima.fr/sites/default/files/stoekl_escriptorium_iiif.pdf)
- A Kraken case study on the Arabic journal *al-Abhath* finds Kraken can produce highly accurate Arabic-script OCR. It compares typeface-specific and generalised models, and calls for "a more systematic approach to producing training data" and better line segmentation. **[Moderate; I read only the abstract]** — [arXiv 2402.10943](https://arxiv.org/abs/2402.10943)
- In the historical-English study above, 68k of 195k training lines came from semi-automatic alignment of ECCO-TCP text to line images. This shows aligned GT at scale in a successful fine-tune. — [arXiv 2602.14524](https://arxiv.org/html/2602.14524)
- SoftCTC: pseudo-labels are usually erroneous, so the standard approach keeps only filtered ones. Seed models are often overconfident, which makes thresholds hard. Soft pseudo-labels matched a tuned filtering pipeline on handwriting. — [SoftCTC](https://arxiv.org/pdf/2212.02135)
- Adapting PP-OCRv6 to historical text: confidence filtering removed hard but correct lines and under-represented rare scripts and typefaces, so it was excluded from pretraining. **[Moderate, 2026 preprint]** — [arXiv 2609.20064](https://arxiv.org/pdf/2609.20064)
- OCR4all/Calamari: confidence correlates with accuracy, but networks overestimate it. Model selection by average confidence on the target book is used. — [OCR4all](https://arxiv.org/pdf/1909.04032); [arXiv 1606.05157](https://arxiv.org/pdf/1606.05157)
- An Indic printed OCR paper iteratively adapts a model to new domains using only high-confidence pseudo-labels. — [CVIT 2025](https://cdn.iiit.ac.in/cdn/cvit.iiit.ac.in/images/ConferencePapers/2025/No_Labels_No_Problem_Self_Supervised_Learning_for_Indic_Printed_OCR.pdf)

### Inferences
- **Recipe for kitabim.** The project already has corrected page text in Postgres (pages corrected via spell-check/LLM). Run Surya line detection and recognition per page. Then do a global character-level alignment (Needleman–Wunsch / `edlib` / passim) of the concatenated noisy line outputs to the corrected page text, and cut the corrected text at the line boundaries. Keep lines whose per-line CER between noisy and assigned text is under a threshold (for example ≤15%), and send the rest to manual review.
- **Hyphenation caveat.** If the corrected page text has been de-hyphenated (words rejoined), the aligned GT for a line-end fragment would wrongly contain the whole word. That would directly *teach* failure mode 1. The alignment step must re-split the word at the line boundary and re-insert the hyphen, using the image or noisy OCR as the guide. Otherwise, drop such lines.
- **Similar caveat for confusables.** If the "corrected" text was itself produced by an LLM or spell-check that may over-normalise, it is not trustworthy GT for ۇ/ۆ distinctions. Keep a human-verified subset.
- **Avoid pure confidence thresholds.** They will preferentially drop exactly the confusable and hyphen lines. Prefer agreement-based filtering (OCR output vs. aligned text) and stratified sampling.

### Gaps
- No Uyghur-specific alignment pipeline was found. I did not verify the passim parameters used by KITAB.

## 5. Post-OCR correction for confusable diacritics and de-hyphenation

### Takeaway
Use lexicon- and frequency-constrained correction restricted to the known confusion sets (a small, safe search space). Treat LLM correction as risky for Arabic script, where it failed in all setups in one 2026 study and over-correction is a recurring issue. ByT5 correction gives modest gains and mostly copies errors.

### Cited Findings
- LLM-based post-OCR correction for Arabic script "remains unsuccessful across all setups" in a CAWL 2026 study, which cites script switching, hallucination, and instruction-following failures. **[Moderate; snippet only, paper not opened]** — [ACL Anthology 2026.cawl-1.8](https://aclanthology.org/2026.cawl-1.8/)
- The ICDAR 2026 HIPE-OCRepair competition found that LLM-assisted correction can significantly improve OCR, but over-correction on low-noise inputs is a recurring challenge. Scoring was retrieval-oriented, not diplomatic. **[Moderate]** — [HIPE-OCRepair overview](https://www.alphaxiv.org/abs/2607.08143.md)
- A study of Arabic manuscript OCR with VLMs notes that LLM correction helps in some languages and fails in others. — [arXiv 2608.22366](https://arxiv.org/pdf/2608.22366)
- ByT5 post-correction: Guan & Greene (ACL Findings 2024) report CER reductions of 12.41–48.18% across 8 languages using synthetic training data, without manual annotation. A Twente thesis finds fine-tuned ByT5 beats the previous SOTA, while few-shot generative LLMs fail without fine-tuning. **[Strong for Guan & Greene; Weak for thesis]** — [arXiv 2408.02253](https://arxiv.org/html/2408.02253v2); [Twente thesis](https://essay.utwente.nl/essays/102117)
- An Ottoman Turkish ByT5 thesis (Arabic script) reports ~9.6% CER vs. a 10.51% baseline (8–8.5% relative). The model copies 85% of errors unchanged. Confidence-weighted training cut over-corrections by 19% without improving CER. **[Weak: thesis listing]** — [Sabancı event page](https://sabanciuniv.edu/en/events/detail/28390)
- Many real-word errors pass dictionary checks, which limits lexical correction. This applies directly to Uyghur pairs where both ۇ and ۆ variants are valid words. — [arXiv 2602.14524](https://arxiv.org/html/2602.14524)
- Rule-based rejoining of broken hyphenations works well but fails under certain noise. — [DTIC report](https://apps.dtic.mil/sti/tr/pdf/ADA561948.pdf)

### Inferences
- **Confusion-set lexicon corrector (unsourced design, low risk).** For each OCR token not in the `words` table, generate candidates by substituting only within confusion sets {و,ۇ,ۆ,ۈ,ۋ}, {ز,ژ}, {ي,ې}, {ك,ڭ,گ}, with up to 2 substitutions. If exactly one candidate is in-lexicon (or one dominates by frequency by a large margin), replace it. Otherwise leave it and flag. Do not touch in-lexicon tokens (real-word confusions), except with a bigram/LM score and a high margin. This bounds over-correction.
- **Character confusion matrix.** Compute it from the aligned eval set (§4/§6) and use the measured substitution probabilities as channel-model weights (noisy channel: P(word) × P(ocr|word)).
- **De-hyphenation.** Join a line-final fragment ending with "-" to the next line's first token. Accept the join if the joined form is in the lexicon (or has a valid suffix analysis). If not, try confusion-set variants of the joined form, and otherwise keep the hyphen. This matches the project's decision to de-hyphenate in the OCR client only (memory: dehyphenation_scope_decision). The project memory says not to touch the words table, so use it read-only.
- **LLM correction.** If used at all, restrict it to flagged tokens with a candidate list, ask it to choose rather than rewrite, and evaluate over-correction separately.

### Gaps
- No Uyghur-specific post-OCR correction study was found.

## 6. Evaluation (CER, confusion matrices, targeted test sets, held-out size)

### Takeaway
Report overall CER/WER plus (a) a per-character confusion matrix over the confusable sets, (b) CER and exact-match on a **hyphen-line slice**, (c) a short-line slice, and (d) an over-normalisation or over-correction rate. Hold out by **book**, not by line, as the historical-OCR study did.

### Cited Findings
- The historical-OCR comparison evaluated about 10k line images (about 200 pages) that were **disjoint from training at book level**. It reported CER/WER by condition (colour vs. B/W, short vs. long lines) and the edit-distance distribution, and recommends architecture-specific error profiles (locality, detectability, normalisation) beyond CER/WER. — [arXiv 2602.14524](https://arxiv.org/html/2602.14524)
- A Sanskrit post-OCR study used paired bootstrap with 10,000 resamples for confidence intervals. This is a reusable method for comparing two models on the same test lines. — [arXiv 2605.27750 snippet](https://arxiv.org/pdf/2605.27750)
- The SARD benchmark comparison shows how a fine-tuned vs. zero-shot mismatch inflates results. Keep the test-set provenance clean. — [SARD summary](https://www.emergentmind.com/topics/sard)

### Inferences
- **Suggested sizes (rule-of-thumb, unsourced).**
  - General held-out set: ≥1,000–2,000 real lines from ≥5 books not in training.
  - Hyphen slice: ≥200–300 real line-end-fragment lines. At a 10% error rate, n=300 gives about ±3.4 pp 95% CI.
  - Confusable slice: ≥100 occurrences per letter in each confusion set, positional variants included. Because ژ and ڭ are rare, build this slice by searching the corpus for those letters.
- **Metrics per slice.**
  - Hyphen lines: "fragment exact-match" (last token == fragment + "-"), and inserted-character count after the fragment.
  - Confusables: precision and recall per letter, and the confusion matrix restricted to sets.
  - Post-correction: over-correction rate (correct tokens changed).
- Also report on synthetic validation separately. Never mix synthetic and real lines in the test set.

### Gaps
- No published guidance on held-out set sizes for low-resource OCR fine-tuning was found. The sizes above are statistical rules of thumb.
