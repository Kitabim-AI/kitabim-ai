# Hugging Face Uyghur TTS API — Proof of Concept

**Branch:** `feature/implement-tts`  
**Script:** `scripts/poc_hf_uyghur_tts.py`  
**Generated Audio Samples:** `data/poc_tts/` (gitignored)

---

## 1. Test Input Passage (882 chars)

Literary Uyghur passage containing quotation marks (`«...»`), semicolons (`؛`), spaced em-dashes (`—`), an attribution line without a trailing period (`— بابۇر`), and an inline four-digit year (`1876 — يىلى`):

> «قولىڭدىن كەلسە، ئوتنى بۈگۈن ئۆچۈر؛ ناۋادا ئوت ئۇلغىيىپ كەتسە، جاھاننى كۆيدۈرۈدۇ. دۈشمەننى بىر ئوق بىلەن مىخلاپ قويۇش مۇمكىن ئىكەن، ئۆزۈڭنى ئۆز ياسىنى كېرىشكە ئىمكان بەرمە.»  
> — بابۇر  
>  
> مىلادى 1876 — يىلى باش كۈز. ئەقرەپ ئايلىرىنىڭ باشلىرىدا، بۇغدايلار سارغايىدى، چەكسىز كەتكەن يېپيېشىل زىرائەتلەرنىڭ خېلى كۆپ جايلىرىدا ساپسېرىق پارقىراق پارچىلار ھاسىل بولدى. بۇ بۇغدايلىقلار ئىدى. تاغ تەرەپتە سوزۇلۇپ ياتقان تۆپىلىكلەردىكى يېپيېشىل چۆپلەر ئۈستىدە ئوخشاش ۋە ساپسېرىق ئېچىلغان، دانە — دانە بولۇپ چاقناپ تۇرغان لېيلىقازاقلار كۆرۈنەتتى. يىراقتىكى بۇغدا چوققىسى خۇددىي بۇلۇتقا ئوخشاش، كۆك ئاسماننىڭ بىر چېتىگە يېپىشىپ تۇراتتى. ئاسماننىڭ يۈزى زادىلا ئېچىلىپ باقمايتتى، قاچانلا قارىسىڭىز، بىر — ئىككى پارچە ئاق بۇلۇت ياكى قارا بۇلۇت لەيلەپ يۈرەتتى. كۈندۈزلىرى قۇياشنىڭ ئوتتەك تەپتىدىن ئات — ئۇلاغلار ھاسىراپ كېتەتتى. ئىتلار تىللىرىنى ئۇزۇن ساڭگىلىتىپ يېتىشاتتى. ئاخشاملىرى بوران گۈركىرەيتتى.

---

## 2. Benchmark Results

| # | Output File | Provider / Space | Model / Voice | Status | Latency | Audio Dur | RTF | Sample Rate | Size |
| :- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 0 | *(none)* | `router.huggingface.co/hf-inference` | `facebook/mms-tts-uig-script_arabic` | Failed (`HTTP 401/404`) | 0.14s | — | — | — | — |
| 1 | `01_uyghurai_tts_mms.wav` | `UyghurAI/uyghurai-tts` (Docker REST) | `facebook/mms-tts-uig-script_arabic` | OK (single-shot) | 31.74s | 75.17s | 0.42× | 16 kHz | 2,349 KB |
| 2 | `02_piyazon_cv_unique2.wav` | `piyazon/Uyghur-TTS-Text-To-Speech` | `CV_Unique-2` (VITS fine-tune) | OK (single-shot) | 27.55s | 64.22s | 0.43× | 16 kHz | 2,007 KB |
| 3 | `03_piyazon_qutadgubilik.wav` | `piyazon/Uyghur-TTS-Text-To-Speech` | `QutadguBilik` (VITS fine-tune) | OK (single-shot) | 26.26s | 64.70s | 0.41× | 16 kHz | 2,022 KB |
| 4 | `04_piyazon_roman_girl.wav` | `piyazon/Uyghur-TTS-Text-To-Speech` | `Roman-Girl_Ug` (VITS fine-tune) | OK (single-shot) | 22.87s | 56.59s | 0.40× | 16 kHz | 1,769 KB |
| 5 | `05_piyazon_mms_tts.wav` | `piyazon/Uyghur-TTS-Text-To-Speech` | `MMS-TTS` + built-in normalizer | OK (single-shot) | 30.73s | 75.17s | 0.41× | 16 kHz | 2,349 KB |
| 6 | `06_k2fsa_omnivoice_uighur.wav` | `k2-fsa/OmniVoice` (ZeroGPU A10G) | `OmniVoice` (`lang="Uighur"`, raw input) | OK (single-shot) | **7.22s** | 72.33s | **0.10×** | **24 kHz** | 3,391 KB |
| 7 | `07_k2fsa_omnivoice_normalized.wav` | `k2-fsa/OmniVoice` (ZeroGPU A10G) | `OmniVoice` + Uyghur Pre-Normalizer | OK (single-shot) | **7.40s** | 76.00s | **0.10×** | **24 kHz** | 3,563 KB |

*(RTF = Real-Time Factor = `Latency / Audio Duration`; lower is faster.)*

---

## 3. Acoustic & Pronunciation Audit

1. **`k2-fsa/OmniVoice` + Uyghur Pre-Normalizer (`07_k2fsa_omnivoice_normalized.wav`) — Best Overall Quality & Speed**
   - **Audio quality:** Studio-clean 24 kHz output with zero vocoder buzz, crisp Uyghur uvular/velar consonants (`ق`, `غ`, `خ`), accurate vowel harmony, and natural literary pacing.
   - **Raw vs. Normalized (`06` vs. `07`):** On raw input (`06`), `OmniVoice` mumbled the unexpanded digits `1876` into gibberish and merged `— بابۇر` into `مىلادى`. Pre-normalizing `1876 — يىلى` to `مىڭ سەككىز يۈز يەتمىش ئالتىنچى يىلى`, adding a sentence break after `— بابۇر.`, and cleaning decorative punctuation (`«»`, `—`) in `07` completely resolved both issues.
   - **Multi-chunk consistency note:** `OmniVoice`'s `/_design_fn` samples a fresh speaker voice per request. For multi-chunk book narration, pass a fixed 5–10s narrator reference clip to `/_clone_fn` so voice identity stays constant across chunks/pages.

2. **`piyazon/Uyghur-TTS-Text-To-Speech` (`02`–`05`) — Best CPU-Friendly VITS Baselines + Built-in Number Normalization**
   - All four voices automatically converted `1876` into `مىڭ سەككىز يۈز يەتمىش ئالتە` via `piyazon`'s built-in Uyghur number normalizer.
   - **`CV_Unique-2` (`02`):** Calm male narrator; preserves final `-r` (`بۇغدايلار`, `پارچىلار`), occasional slight slurs (`ئۆزۈڭنى بىز ياسىنى`, `ساڭگىلىتىپ`), noticeable 16 kHz VITS grain.
   - **`QutadguBilik` (`03`):** Deep, dramatic audiobook-style male voice; expressive intonation, audible VITS metallic artifacts, and slight clipping on the final phoneme (`گۈركىرەيت-`) without trailing silence padding.
   - **`Roman-Girl_Ug` (`04`):** Female voice; brisk tempo (56.6s), slight consonant substitution at the end (`تۈركىرەيتتى` for `گۈركىرەيتتى`).
   - **`MMS-TTS` (`05`):** Base `facebook/mms-tts-uig-script_arabic` with number normalization; drops syllable-final `-r` (`بۇغدايلا`, `پارچىلا`, `ئىتلا`), characteristic of the MMS speaker dataset.

3. **`UyghurAI/uyghurai-tts` (`01`) — Simplest REST Wrapper, Incomplete Number Normalization**
   - Clean FastAPI JSON contract (`POST /tts/speak` -> `{"success": true, "audioUrl": "/outputs/....wav"}`), but its `/normalize` endpoint leaves `1876` untouched, causing the underlying MMS VITS model to skip the year entirely (`مىلادى ... يىلى باش كۈز`).

---

## 4. Commercially Licensed / Commercial-Ready Models PoC

Because both `facebook/mms-tts-uig-script_arabic` (`CC-BY-NC-4.0`) and `k2-fsa/OmniVoice` (`CC-BY-NC` weights) carry non-commercial restrictions, we also evaluated the commercially usable alternatives for free using `scripts/poc_commercial_uyghur_tts.py`:

| # | Output File | Provider / Model | License | Latency | Audio Dur | Sample Rate | Verdict |
| :- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 8 | `08_gemini38_flash_tts_raw.wav` | Google `gemini-3.8-flash-tts` (`Sadaltager`) | Commercial API (Google ToS) | **18.82s** | 75.04s | **24 kHz** | **Best overall commercial quality.** Native audiobook acting, natural breaths, dramatic pause on `— بابۇر`, and **natively pronounced raw `1876 — يىلى` as `بىر مىڭ سەككىز يۈز يەتمىش ئالتىنچى يىلى` with zero regex pre-normalization** (491 text input tokens, 1,877 audio output tokens). |
| 9 | `09_gemini38_flash_tts_normalized.wav` | Google `gemini-3.8-flash-tts` (`Sulafat`) | Commercial API (Google ToS) | **19.52s** | 78.20s | **24 kHz** | Warm female narrator voice, studio 24 kHz clarity; minor misread on one archaic phrase (`ئۆز ياسىنى`), whereas `Sadaltager` (`08`) read it verbatim. |
| — | *(in-repo sample audited)* | `Anadilorg/Anadil_Uyghur_TTS` (`VoxCPM2` LoRA) | `MIT` + `Apache-2.0` | — | — | 48 kHz | Audibly muffled/robotic even on in-training Common Voice reference clips; requires ~9 GB VRAM on CUDA. |
| — | *(local M2 Pro run)* | `ElgekAI/SLED-TTS-Uyghur-UAS-0.2B` | `MIT` | — | — | 24 kHz | Hit `float16` `NaN` numerical overflow on Apple Silicon MPS; requires CUDA GPU + clean 3–9s reference clip per speaker and 20s sentence chunking. |
| 10 | `10_qwen3_tts_uyghur_apache2_sample.wav` | `anke01/qwen3-tts-uyghur` (`Qwen3-TTS-0.6B`) | `Apache-2.0` | 35.64s (1 sent.) | 12.72s | 24 kHz | Unusable: under-trained checkpoint (0.55 epochs / loss ~4.5) outputs distorted static/babble and fails to emit EOS reliably. |

---

## 5. Recommended Production Direction for `feature/implement-tts`

1. **Primary Commercial Choice — Google `gemini-3.8-flash-tts`:**
   - Already authenticated via Kitabim's existing `GEMINI_API_KEY` (zero new vendor or GPU ops).
   - Supports **Uyghur** natively (130-language flagship tier), 30+ studio voices + custom Voice Design, Batch API (50% discount for pre-generating entire books), and handles raw digits/years (`1876`) and literary punctuation out of the box.
   - Pre-generate audio once per book page/chapter via the Batch or Interactions API, encode to `64 kbps` Opus/MP3, and cache permanently in Google Cloud Storage.
2. **Non-Commercial / Self-Hosted Alternative — `k2-fsa/OmniVoice` (`07`):**
   - If operating under `CC-BY-NC` (or with author permission), `k2-fsa/OmniVoice` paired with a Uyghur number/punctuation pre-normalizer delivers fast (~10× real-time), crisp 24 kHz narration on a dedicated \$0.40–\$1.00/hr GPU with scale-to-zero.

