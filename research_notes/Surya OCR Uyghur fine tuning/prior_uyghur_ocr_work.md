# Prior Work on Uyghur (UEY) OCR and Arabic-Script OCR Fine-Tuning

Research date: 2026-10-31. Tool budget was about 15 web calls, so some areas are thin. Those are listed under Gaps. Evidence-quality notes appear inline.

## Q1. Public Uyghur OCR datasets (printed and synthetic): sizes, licenses, availability

### Takeaway
No well-documented public benchmark for **printed Uyghur books** turned up. The public Uyghur data that exists is mostly **scene text**: SUST (synthetic) and RUST (real), from the Xinjiang-region academic groups. Tesseract's `uig` model ships with training text and a wordlist, but it was rendered with generic fonts and has no published accuracy. For a book-domain Surya fine-tune, the data will have to be built in-house: synthetic renders plus corrected real pages.

### Cited Findings
- **SUST & RUST** ("Two datasets for Uyghur Scene Text Recognition"). SUST is a synthetic Uyghur scene-text set and RUST a real one. The best model reached 96.8% accuracy on synthetic data, 9.0 points above a CRNN baseline. Training on synthetic data and testing on real data peaked at 86.4%, 8.2 points above CRNN. — [ResearchGate](https://www.researchgate.net/publication/375506947_SUST_RUST_Two_datasets_for_Uyghur_Scene_Text_Recognition). Only the listing page was seen, so the original venue is unverified.
- **Hugging Face mirror `lht12311/Uyghur_OCR_SUST_RUST`** (duplicate of `anke01/Uyghur_OCR_SUST_RUST`):
  - about 12 GB zip (`ug_dataset.zip`), with a single `train` split
  - Hub size category is 1M–10M samples, but no exact count is given
  - MIT license
  - the card does not say whether the data is printed, handwritten or synthetic, or whether it is line- or word-level, and lists no fonts
  - the dataset viewer is broken
  
  — [HF dataset card](https://huggingface.co/datasets/lht12311/Uyghur_OCR_SUST_RUST). The MIT label is a re-uploader's claim and the provenance is unclear.
- **Correlation-guided decoding (Complex & Intelligent Systems, 2024)** used 9,082 Uyghur scene images (7,267 train / 1,815 test) and reports accuracy, not CER. — [Springer](https://link.springer.com/article/10.1007/s40747-024-01689-5)
- **Scene Uyghur Recognition Based on Visual Prediction Enhancement (Sensors, 2023)** generated 50,000 synthetic images. Best accuracy in its ablation was 85.55% on a self-built set. — [MDPI Sensors](https://www.mdpi.com/1424-8220/23/20/8610)
- **Uyghur TrOCR model `patkaiist/Uyghur_TrOCR`.** A VisionEncoderDecoder (TrOCR-style) model with an empty model card and a **CC-BY-NC-ND-4.0** license (non-commercial, no derivatives, so it cannot be fine-tuned and redistributed). — [HF model](https://huggingface.co/patkaiist/Uyghur_TrOCR)
- **Tesseract `uig`.** Shipped in `tessdata_fast` and `tessdata_best` (Apache 2.0). It is packaged by distros as `uig.traineddata` (v4.1.0). — [Fedora package](https://packages.fedoraproject.org/pkgs/tesseract-tessdata/tesseract-langpack-uig), [MSYS2](https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-tesseract-data-uig)
- **Tesseract langdata for `uig`** contains `uig.training_text`, `uig.wordlist`, `uig.unicharset`, `uig.punc`, `uig.numbers`, `uig.singles_text`, `desired_characters`, `forbidden_characters` and `okfonts.txt`. — [langdata_lstm/uig](https://github.com/tesseract-ocr/langdata_lstm/tree/main/uig)
- Its `okfonts.txt` lists only generic fonts: Arial Unicode MS Regular, DejaVu Sans (+Bold), FreeMono Regular, FreeSerif (Regular/Bold), Lucida Sans (Regular/Oblique). **No UKIJ or other Uyghur book faces.** — [okfonts.txt](https://raw.githubusercontent.com/tesseract-ocr/langdata_lstm/main/uig/okfonts.txt)
- IronOCR sells a commercial Uyghur language pack for .NET. It is most likely Tesseract-derived (inference), and no accuracy figures are published. — [IronOCR Uyghur](https://ironsoftware.com/csharp/ocr/languages/uyghur/)

### Inferences
- Tesseract `uig` was trained only on Latin-oriented fallback fonts. It probably generalizes poorly to Xinjiang publishing-house typefaces (UKIJ Tuz / UKIJ Basma-style Naskh faces, Ekran, etc.) and is a weak baseline.
- The `uig.training_text` and `uig.wordlist` files (Apache 2.0) are still a free seed corpus for synthetic rendering and for building a character inventory or unicharset.
- SUST/RUST is scene text (signs, backgrounds). It may help robustness, but the domain gap to book pages is large. Treat it as auxiliary data, not core training data.

### Gaps
- Exact contents and sample count of the HF SUST_RUST zip were not inspected.
- No public **printed-book line-level** Uyghur dataset with ground truth was found. A Chinese-language thesis on printed Uyghur recognition is cited in other papers but was not located.
- No Kaggle Uyghur OCR dataset surfaced in searches.
- No published Tesseract `uig` CER on books was found.

## Q2. Published Uyghur OCR papers: architectures, reported metrics, error types, letter confusions

### Takeaway
Published Uyghur recognition work (roughly 2017–2024, mostly Xinjiang University and related groups) uses CRNN, CRNN+attention or ConvNeXt+BiLSTM+attention. It mostly reports **word or sequence accuracy** (about 78–97%) on self-built scene or word sets, not CER on printed books. No paper surfaced that analyzes the specific confusions ئو/ئۇ/ئۆ/ئۈ, ز/ژ or ك/ڭ. Numbers are not comparable across papers.

### Cited Findings
- **Li et al., Applied Sciences (Aug 2023), "A Three-Stage Uyghur Recognition Model Combining the Attention Mechanism and Different Convolutional Recurrent Networks".** The authors say the scarcity of public data and the strong-ligature script make the task hard. They built their own dataset, and their best result was **90.21% accuracy** with ConvNeXt + BiLSTM + attention. — [DOAJ](https://doaj.org/article/9ce0ea57fadc4c6f84d9887421c91002), [OUCI](https://ouci.dntb.gov.ua/works/4bwPK0al). Both returned 403, so these details come from the search snippet only.
- **"An Effective Method for Detection and Recognition of Uyghur Texts in Images with Backgrounds" (Information, 2022).** On synthetic data, an improved CRNN reached accuracy 0.864 with Average Edit Distance 0.204, against the original CRNN's 0.782 / 0.458. The authors themselves say accuracy is still too low for practical use. — [doi:10.3390/info13070332](https://doi.org/10.3390/info13070332)
- **Printed Uyghur character recognition (CCBR 2018).** HOG features + MLP gave 78.17% / 90.47% / 94.50% average accuracy for the CDF-2/4/8 feature variants. — [ResearchGate](https://www.researchgate.net/publication/326895105_Research_on_the_Methods_for_Extracting_the_Sensitive_Uyghur_Text-Images_for_Digital_Forensics_13th_Chinese_Conference_CCBR_2018_Urumqi_China_August_11-12_2018_Proceedings)
- **"A Deep-Learning Approach to OCR for Uighur Language" (IEEE Access 2021, Gebze TU repository).** The authors state that Uyghur OCR is difficult even for printed text because of the script's cursive nature. — [GTU repository](https://acikerisim.gtu.edu.tr/items/dc134f92-ca19-491e-80c5-fa82ef3bc067), [DOAJ](https://doaj.org/article/7a353e22ae114ea4b27ba9cc77253b7c)
- **Document-image work that bypasses recognition** includes keyword spotting (64% accuracy / 49% recall over 8 keywords in 100 documents) and SURF/SIFT-based retrieval. — [ACM 2020](https://dl.acm.org/doi/10.1145/3436369.3437411), [Springer SURF](https://link.springer.com/chapter/10.1007/978-3-030-03338-5_9)

### Inferences
- The literature offers **no transferable CER baseline** for printed Uyghur books. The project should define its own held-out page/line test set and report CER/WER plus per-confusion-pair counts.
- The confusion pairs differ mainly in small marks: the ۇ/ۆ/ۈ diacritics, the dots on ز/ژ, and the extra dots of ڭ versus ك. These are exactly the features that low resolution and bleed-through destroy, so training needs high-DPI line crops and degradation augmentation. (This inference is reinforced by the Arabic diacritics findings in Q4.)

### Gaps
- Full-text error analyses of the Li 2023 and Information 2022 papers were not retrieved (403 or out of scope).
- Whether any paper reports confusion matrices for Uyghur vowel letters is unknown.

## Q3. Uyghur orthography and typography facts relevant to OCR

### Takeaway
Modern Uyghur books **do hyphenate across line breaks**, which is unusual among Arabic-script orthographies. The mark is a short straight stroke like a tatweel/kashida, placed at the **line-end** side, which is the left edge of the line in RTL. It appears even after non-connecting letters, and the letters on each side keep their **joined** contextual forms. Older (pre-1980s/traditional) practice used no mark at all, only the joined forms. OCR output therefore needs a rule for when to de-hyphenate and re-join words split across lines.

### Cited Findings
- **Hahn, *Spoken Uyghur* (1991), via John Hudson (Tiro Typeworks) on W3C www-style, May 2014.**
  - Traditional practice: "No particular symbol is used to indicate end-of-line divisions."
  - Line-end side: "the last letter before a division appears in its initial or medial form."
  - Next-line side: "the first letter after a division appears in its medial or final form."
  - In modern books (Davamĕt 1993, Samsaḳ 1985) a mark "similar in form to a straight kashida (U+0640 ARABIC TATWEEL)" is "inserted after both left-connecting and non-connecting letters at line-end."
  - Hudson: "It is not known how this convention should be handled from an encoding … perspective."
  
  — [W3C www-style 2014May/0391](https://lists.w3.org/Archives/Public/www-style/2014May/0391.html). Evidence quality: an expert typographer citing published books, though the sample is small (two 1980s–90s books).
- **Arabic-derived Uyghur "requires marking of all vowels and uses hyphenation,"** unlike Arabic or Persian. Chinese national standard **GB/T 32411-2015** covers editing software for Uyghur, Kazakh and Kirghiz. The portions quoted in the issue only cover which punctuation may start or end a line. — [w3c/alreq issue #237](https://github.com/w3c/alreq/issues/237)
- **W3C i18n tests** check that a hyphen is produced (shape undefined) and that letters on either side of it keep their cursive joining forms. — [W3C word-break-shaping results](https://w3c.github.io/i18n-tests/results/word-break-shaping)
- A XeTeX mailing-list example shows a hyphenated Uyghur word with contextual forms changing across the break. — [TUG xetex 2021-March](https://tug.org/pipermail/xetex/2021-March/027895.html)
- **Hamza:** ئ marks word-initial vowels and is "usually ignored [in pronunciation] at the beginning of words" but read as /ʔ/ medially. Every vowel-initial word is written ئا ئە ئو ئۇ ئۆ ئۈ ئې ئى. — [Wikipedia: Uyghur Arabic alphabet](https://en.wikipedia.org/wiki/Uyghur_Arabic_alphabet)
- **ڧ / ف encoding drift:** Windows Vista/2008 keyboards used U+06A7 ڧ, while Windows 7+ use U+0641 ف, and "In the digital sphere, U+0641 ف is prevalent." Some Uyghur fonts map the ڧ shape onto U+0641. — [Wikipedia](https://en.wikipedia.org/wiki/Uyghur_Arabic_alphabet)
- **Uyghur-specific codepoints and joining types.** These come from the Unicode Standard. The UCD files were not fetched in this session, but these are standard values:

  | Letter | Codepoint | Name / note |
  |---|---|---|
  | ە | U+06D5 | AE; not ه U+0647 |
  | ې | U+06D0 | E |
  | ى | U+0649 | ALEF MAKSURA, used for Uyghur /i/ |
  | ي | U+064A | yeh; not Persian ی U+06CC |
  | ۇ | U+06C7 | U |
  | ۆ | U+06C6 | OE |
  | ۈ | U+06C8 | YU |
  | ۋ | U+06CB | VE |
  | ژ | U+0698 | |
  | ڭ | U+06AD | NG |
  | ك | U+0643 | Arabic kaf; not Persian keheh ک U+06A9 |
  | گ | U+06AF | |
  | ئ | U+0626 | |
  | ، | U+060C | comma |
  | ؛ | U+061B | semicolon |
  | ؟ | U+061F | question mark |

  **ې and ى are dual-joining.** The **right-joining-only (non-left-connecting)** set is ا د ر ز ژ و ۇ ۆ ۈ ۋ ە. — [Unicode ArabicShaping.txt](https://www.unicode.org/Public/UCD/latest/ucd/ArabicShaping.txt), [Unicode Arabic chart](https://www.unicode.org/charts/PDF/U0600.pdf). This is from my knowledge of the UCD, not fetched here, so verify programmatically with `unicodedata` plus ArabicShaping.txt.

### Inferences
- **De-hyphenation rule for OCR post-processing.** A line ending with a tatweel-like stroke (OCR'd as U+0640 ـ, '-' U+002D or U+2010) followed by a line starting mid-word is a split word, so join without a space. Because the mark also follows non-connecting letters (ر ز ۇ ...), "previous letter is in initial/medial form" cannot be the only test.
- **Pre-1985 books may have no hyphen mark at all.** Then the only signal is the contextual shape: a line ending in an initial or medial form. That shape is lost in Unicode text, so it has to be detected visually or with a lexicon (is the concatenation of the two fragments a known word?).
- The ambiguity between tatweel used as a hyphen and genuine kashida justification is a likely source of OCR noise. Normalize U+0640 out of the recognized text.
- Common normalization hazards for training labels and evaluation:
  - Arabic Presentation Forms (U+FB50–FDFF, FE70–FEFF) appear in PDFs extracted from old typesetters. Apply NFKC-like mapping for those ranges only, because full NFKC can change other things.
  - Swap pairs to fold: ه→ە, ی (U+06CC)→ى/ي depending on position and usage, and ک→ك.
  - Keep ئ as U+0626, not a decomposed ى + hamza (U+0654).
  - Map ڧ→ف.
  - Fix stray Latin punctuation (',', '?').
  
  Labels must be normalized consistently, or the CER will measure encoding differences instead of OCR errors.

### Gaps
- The exact hyphen glyph conventions in post-2000 Xinjiang publishing (Xinjiang People's Publishing House, Kashgar Uyghur Publishing) are not documented online. Whether the mark is drawn at the left edge as a tatweel stroke or as an ASCII-like short dash could not be confirmed beyond Hudson's two examples.
- The full text of GB/T 32411-2015 (which may specify hyphenation positions or syllable-break rules) was not obtained.
- Uyghur syllable-based hyphenation rules (where words may be split) were not found online.

## Q4. Fine-tuning case studies on comparable scripts (Surya, TrOCR, Tesseract, Kraken, VLMs)

### Takeaway
**No published Surya recognition fine-tune for any Arabic-script language was found.** Datalab publishes only a fine-tune dataset-format example, and Surya zero-shot Arabic was reported as very poor by a secondary source.

Comparable evidence comes from other models:
- **VLM LoRA fine-tunes on synthetic Arabic** (QARI-OCR on Qwen2-VL-2B, 10k–50k rendered samples) reach CER of about 0.06 on printed books.
- **Small in-domain sets** help a lot: 500 samples gave Urdu GPT-4o a 6-point WER gain.
- **Tesseract adaptation from a related script with small data** works for Kurdish.

The recurring lessons:
- use synthetic rendering across many fonts with degradation
- add a modest set of real in-domain pages
- watch for diacritics and repetition loops

### Cited Findings
- **Surya fine-tune format.** Datalab's `datalab-to/ocr_finetune_example` HF dataset shows the expected format for fine-tuning Surya OCR. The v0.5.0 release introduced the newer OCR model with automatic language detection. A community question about Arabic fine-tuning was unanswered. — [HF ocr_finetune_example](https://huggingface.co/datasets/datalab-to/ocr_finetune_example/commit/8dc55786ca042f901481c5e8bd0558251d95bca8), [surya v0.5.0](https://github.com/datalab-to/surya/releases/tag/v0.5.0), [HF discussion](https://huggingface.co/ketanmore/surya-layout-fine-tune-script/discussions/1)
- **Surya weights license.** A fork's README notes commercial-use revenue limits on the weights, so check the current license before commercial deployment. — [kielin/surya fork](https://github.com/kielin/surya)
- **Surya zero-shot Arabic** is reported as "very poor" (CER 4.95, WER 5.61, i.e. heavy insertions) on a 3,760-image set. Sinhala reached CER 0.0076 and Tamil 0.139. — [EmergentMind summary of arXiv 2408.15119](https://www.emergentmind.com/topics/surya), [arXiv 2408.15119](https://arxiv.org/abs/2408.15119v3). This is a secondary summary and the primary paper table was not verified.
- **QARI-OCR (Arabic).**
  - Setup: Qwen2-VL-2B-Instruct with LoRA rank 16 on vision and language modules, 1 epoch with Unsloth on a single A6000.
  - Data: fully synthetic HTML-rendered text in 12 Arabic fonts (Naskh to calligraphic), 14–100 px, with clean/moderate/heavy degradation. v0.2 used about 50k samples and v0.3 about 10k.
  - Result: v0.2 reached **CER 0.061 / WER 0.160** on a 200-page traditional-print test, beating open-source models. Generic Qwen baselines were much worse.
  - Diacritic-rich training text was the key to v0.2's gains.
  - 8-bit quantization kept quality, but 4-bit caused substantial drops.
  - Remaining weaknesses: dense layouts, non-standard numerals and page numbers.
  
  — [QARI-OCR, HF papers 2506.02295](https://huggingface.co/papers/2506.02295)
- **Urdu newspapers ("From Press to Pixels", 2025).** Gemini-2.5-Pro was best (WER 0.133). **Fine-tuning GPT-4o on 500 in-domain samples improved WER by 6.13 points absolute.** SwinIR super-resolution improved accuracy by about 50% on average. YOLOv11x handled layout. — [arXiv 2505.13943](https://arxiv.org/abs/2505.13943)
- **Urdu TrOCR fine-tune** for printed Nastaliq exists on HF. A 2025 Urdu study reports one model (named "Trock" in the snippet) at CER 0.177 on OpenITI-Nastaliq. — [qandeelasim13/urdu-ocr-trocr-si26](https://huggingface.co/qandeelasim13/urdu-ocr-trocr-si26). The snippet was garbled and the details are unverified.
- **Persian DeepSeek-OCR fine-tune (Unsloth).** 200k Persian samples cut mean CER from 149% to 60.8%. CER above 100% means hallucinated insertions. — [Unsloth DeepSeek-OCR tutorial](https://unsloth.ai/docs/models/tutorials/deepseek-ocr-how-to-run-and-fine-tune)
- **PaddleOCR Arabic recognizer** went from near-useless to upper-tier after fine-tuning on a 500k-sample corpus. — [medyas/arabic_PP-OCRv6_small_rec](https://huggingface.co/medyas/arabic_PP-OCRv6_small_rec)
- **Tesseract on Arabic-script languages.** An informal blog reports poor out-of-box accuracy for Persian/Kurdish/Urdu/Sindhi. Adding training text, fixing encoding issues and adding missing characters cut WER from 25% to 5%. — [Gofore blog 2020](https://gofore.com/?p=11030). This is a single informal experiment.
- **Sorani Kurdish Tesseract.** Training on Arabic and then fine-tuning with a small amount of Kurdish (Persian-Arabic script) text kept accuracy close to prior results, so script similarity can offset scarce data. — [IOS Press FAIA200623](https://ebooks.iospress.nl/pdf/doi/10.3233/FAIA200623)
- **Two-stage recipe template (Tatar Cyrillic Tesseract 5).** Fine-tuned from Russian on synthetic lines, then on real scans with degradation augmentation, reaching **1.84% CER on books**. — [yasalma/tatar-ocr-tesseract](https://huggingface.co/yasalma/tatar-ocr-tesseract)
- **Arabic VLM vs OCR cross-dataset study (2026).**
  - No single approach wins.
  - VLMs are close to Tesseract on line-level manuscripts and better at page level.
  - OCR-conditioned VLM correction helps on aged and clean print when the OCR output is still recoverable ("OCR-prior recoverability principle") and hurts when the prior is script-mismatched.
  - VLM-OCR is sensitive to diacritics, preprocessing, generation budget and **repetition loops**.
  
  — [arXiv 2608.22366](https://arxiv.org/abs/2608.22366)

### Inferences
- For Surya, a practical target is **10k–50k synthetic lines rendered in Uyghur book fonts** (QARI scale) plus **a few hundred to a few thousand hand-corrected real lines** from the project's own scans (the Urdu 500-sample and Tatar two-stage evidence). The real lines should be oversampled for pages with the ۇ/ۆ/ۈ, ژ, ڭ and hyphenated line-end cases.
- Surya's zero-shot Arabic insertion problem (CER above 1) is consistent with repetition-loop failures seen in VLM-OCR. The evaluation should track insertion rate separately from substitutions.
- An "LLM correction on top of OCR" stage (as the project already does with Gemini) is supported by the OCR-prior recoverability findings, but only when the base OCR is already decent.

### Gaps
- No Kraken or Calamari Uyghur, Persian or Urdu fine-tune numbers were retrieved within budget. Kraken/eScriptorium Arabic models (OpenITI) are known to exist but were not verified here.
- No Kazakh-Arabic (Xinjiang Kazakh) OCR work was found.
- No GOT-OCR or olmOCR Arabic-script fine-tunes were found.
- No Surya-specific Arabic-script fine-tune results were found anywhere, so there is no evidence on how many samples Surya needs.

## Q5. Uyghur text resources for synthetic rendering and language modeling; fonts

### Takeaway
Free text sources exist:
- Tesseract `uig` training text and wordlist (Apache 2.0)
- Uyghur Wikipedia dumps
- CC-100 and OSCAR Uyghur subsets

The project's own corrected book corpus is likely the best in-domain source. The licensing of UKIJ fonts (the Xinjiang University Unicode font family typical of Uyghur publishing) could not be verified in this session.

### Cited Findings
- Tesseract `uig.training_text`, `uig.wordlist` and `uig.unicharset` are in the Apache-2.0 langdata_lstm repo. — [langdata_lstm/uig](https://github.com/tesseract-ocr/langdata_lstm/tree/main/uig)
- Uyghur Wikipedia dumps (ugwiki) are published by Wikimedia. — [dumps.wikimedia.org/ugwiki](https://dumps.wikimedia.org/ugwiki/). Not fetched, so the size is unverified.
- CC-100 includes a Uyghur (ug) subset. — [CC-100 at statmt](https://data.statmt.org/cc-100/). Not fetched, so the size is unverified.

### Inferences
- Rendering synthetic lines with the fonts actually seen in the scanned books matters more than corpus size. Tesseract's uig model, trained on DejaVu/FreeSerif/Arial Unicode, is a cautionary example.
- Synthetic renders should include the hyphenated-line-end case (a word split with a tatweel-like mark at the left margin) so the model learns to emit it consistently for downstream de-hyphenation.

### Gaps
- License terms of UKIJ fonts (UKIJ Tuz, UKIJ Basma, UKIJ Ekran, etc.) and their current download source were not verified. The user should confirm before redistributing rendered data or fonts.
- OSCAR Uyghur subset size and license were not checked.
- No Uyghur OCR-specific language model or lexicon resource (beyond the Tesseract wordlist) was found.
