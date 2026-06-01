import re
import unicodedata

# Uyghur spelling correction mapping from OCR_PROMPT in app/core/prompts.py
REPLACEMENTS = {
    "ئولار": "ئۇلار",
    "ئونىڭغا": "ئۇنىڭغا",
    "ئونىڭ": "ئۇنىڭ",
    "خوشال": "خۇشال",
    "ئولارنىڭ": "ئۇلارنىڭ",
    "ئولارغا": "ئۇلارغا",
    "ئونىڭدىن": "ئۇنىڭدىن",
    "تويۇقسىز": "تۇيۇقسىز",
    "بونداق": "بۇنداق",
    "ئوزاق": "ئۇزاق",
    "ئونداق": "ئۇنداق",
    "ئەسرنىڭ": "ئەسىرنىڭ",
    "ئويان": "ئۇيان",
    "ئۈزۈن": "ئۇزۇن",
    "موشۇ": "مۇشۇ",
    "ئودۇل": "ئۇدۇل",
    "يوقىرىدا": "يۇقىرىدا",
    "ھوزۇر": "ھۇزۇر",
    "خوراسان": "خۇراسان",
    "يوقىرىغا": "يۇقىرىغا",
    "ئوزاقتىن": "ئۇزاقتىن",
    "يوقىرىدىكى": "يۇقىرىدىكى",
    "ئوزاققىچە": "ئۇزاققىچە",
    "ئوستام": "ئۇستام",
    "ئۆنداق": "ئۇنداق",
    "ئابرويى": "ئابرۇيى",
    "خوشخۇي": "خۇشخۇي",
    "روسلاپ": "رۇسلاپ",
    "جەمئى": "جەمئىي",
    "ئوزاققا": "ئۇزاققا",
    "ئئوچقاندەك": "ئۇچقاندەك",
    "گۇياكى": "گوياكى",
    "بونچە": "بۇنچە",
    "خوشى": "خۇشى",
    "رەسمى": "رەسمىي",
    "ئابرويىنى": "ئابرۇيىنى",
    "بوقا": "بۇقا",
    "قەتئىنەزەر": "قەتئىينەزەر",
    "تېگىرقاپ": "تېڭىرقاپ",
    "ھوجرا": "ھۇجرا",
    "سۆرلۈك": "سۈرلۈك",
    "مولايىم": "مۇلايىم",
    "بۈگۈنكىچە": "بۈگۈنگىچە",
    "كۆچلۈك": "كۇچلۈك",
    "مۆرىسىدىن": "مۈرىسىدىن",
    "ئوسۇل": "ئۇسۇل",
    "ژورنىلى": "ژۇرنىلى",
    "سەمىز": "سېمىز",
    "قومۇلدا": "قۇمۇلدا",
    "ئولارمۇ": "ئۇلارمۇ",
}

# Single-pass regex compiler using word boundaries that are safe for Unicode/Arabic script
# (?<!\w) asserts that the character immediately preceding is not a word character.
# (?!\w) asserts that the character immediately following is not a word character.
CORRECTION_PATTERN = re.compile(
    r'(?<!\w)(' + '|'.join(re.escape(k) for k in REPLACEMENTS.keys()) + r')(?!\w)'
)

# Repeated punctuation noise regex (e.g. ,,,,, or ...... or ----- but preserving ellipses dots and markdown separators)
REPEATED_PUNCTUATION = re.compile(r'([,-—–_])\1+')


def apply_corrections(text: str) -> str:
    """Apply deterministic Uyghur spell corrections in a single pass."""
    if not text:
        return ""
    return CORRECTION_PATTERN.sub(lambda m: REPLACEMENTS[m.group(0)], text)


def clean_repeated_punctuation(text: str) -> str:
    """Remove repeating scan/noise punctuation characters."""
    if not text:
        return ""
    # Simplify repeated dashes/commas
    text = REPEATED_PUNCTUATION.sub(r'\1', text)
    # Strip spaces around structural headers/footers
    text = re.sub(r'\[\s*(Header|Footer)\s*\]', r'[\1]', text, flags=re.IGNORECASE)
    return text


def postprocess_text(text: str) -> str:
    """Full postprocessing pipeline for extracted Uyghur text."""
    if not text:
        return ""
    
    # 1. Standard Unicode normalization (NFC)
    text = unicodedata.normalize("NFC", text)
    
    # 2. Cleanup repeated scan artifacts and punctuation
    text = clean_repeated_punctuation(text)
    
    # 3. Apply spelling corrections
    text = apply_corrections(text)
    
    return text
