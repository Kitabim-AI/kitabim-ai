"""Vendored from packages/backend-core/app/utils/text.py (kitabim-ai main
repo). Copied, not imported, so this client stays free of backend-core's
FastAPI/SQLAlchemy/Neo4j dependency chain. Keep in sync manually if the
source functions change - the source of truth is the main repo."""

import re
import unicodedata
from collections import Counter

_PRES_FORM_MAP: dict[int, str] = {}
for _cp in range(0xFB50, 0xFE00):
    _nf = unicodedata.normalize("NFKC", chr(_cp))
    if _nf != chr(_cp):
        _PRES_FORM_MAP[_cp] = _nf
for _cp in range(0xFE70, 0xFF00):
    _nf = unicodedata.normalize("NFKC", chr(_cp))
    if _nf != chr(_cp):
        _PRES_FORM_MAP[_cp] = _nf


def normalize_uyghur_chars(text: str) -> str:
    if not text:
        return ""

    text = "".join(_PRES_FORM_MAP.get(ord(c), c) for c in text)

    return (
        text.replace("ئ", "ئ")  # ئ (Yeh + Hamza) -> ئ (Hamza seat)
        .replace("\u064a\u0654", "\u0626")
        .replace("ة", "ە")  # Arabic Teh Marbuta -> Uyghur E
        .replace("ہ", "ە")  # Urdu Heh Goal -> Uyghur E
        .replace("ے", "ې")  # Urdu Bari Ye -> Uyghur E
        .replace("‌", "")  # Remove ZWNJ
        .replace("‍", "")  # Remove ZWJ
        .replace("\u200b", "")  # Remove Zero-width space
        .replace("ـ", "")  # Remove Tatweel/Kashida
    )


_UYGHUR_VOWELS = r"[اەېىوئۆۇۈ]"

_ORTHOGRAPHY_CORRECTIONS: list[tuple[re.Pattern[str], str]] = [
    # Multilingual OCR models (like Surya) frequently substitute Arabic final beh
    # for Uyghur peh in common vocabulary loanwords. In Uyghur morphophonology,
    # stem-final peh only voices to beh when followed by a vowel suffix; when
    # followed by a consonant suffix or word end, it is always peh.
    (re.compile(r"\bمەكتەب(?!" + _UYGHUR_VOWELS + r")"), "مەكتەپ"),
    (re.compile(r"\bمەنسەب(?!" + _UYGHUR_VOWELS + r")"), "مەنسەپ"),
    (re.compile(r"\bتەلەب(?!" + _UYGHUR_VOWELS + r")"), "تەلەپ"),
    (re.compile(r"\bكەسىب(?!" + _UYGHUR_VOWELS + r")"), "كەسىپ"),
    (re.compile(r"\bئەدەب(?!" + _UYGHUR_VOWELS + r")"), "ئەدەپ"),
    (re.compile(r"\bغېرىب(?!" + _UYGHUR_VOWELS + r")"), "غېرىپ"),
    (re.compile(r"\bئەجەب\b"), "ئەجەپ"),
    (re.compile(r"\bلالىزار(?!" + _UYGHUR_VOWELS + r")"), "لالەزار"),
    # OCR models frequently mistake the terminal Uyghur question mark '؟'
    # following the interrogative suffix 'مۇ' for the Arabic letter mim ('م'),
    # producing '...مۇم' instead of '...مۇ؟' (e.g. 'قىلدىمۇم' -> 'قىلدىمۇ؟').
    (
        re.compile(r"(?<!ئۇ)(?<!ئو)(?<=\w)مۇم(?:\s*؟)?(?=[.,،!»\"”\)\s]|$)"),
        "مۇ؟",
    ),
]


def correct_uyghur_ocr_orthography(text: str) -> str:
    """Post-correct common OCR orthographic errors caused by Arabic/Persian bias.

    Multilingual models like Surya frequently confuse Arabic final beh with Uyghur peh
    in standard Uyghur loanwords, or mistake vowels in common compounds (e.g. Lalazar).
    """
    if not text:
        return ""
    for pattern, repl in _ORTHOGRAPHY_CORRECTIONS:
        text = pattern.sub(repl, text)
    return text


_OCR_MARKER_RE = re.compile(r"\s*\[(?:Header|Footer)\].*", re.IGNORECASE)


_PAGE_NUMBER_RE = re.compile(
    r"""^\s*
    (?:
        # Decorated / standalone digits: e.g. "- 4 -", "( 12 )", "[3]", "· 4 ·", "4", "— 123 —"
        (?:[-—–•·*#\(\[\{/\\~]\s*)*
        [0-9\u0660-\u0669\u06F0-\u06F9]{1,4}
        (?:\s*[-—–•·*#\)\]\}/\\~])*
        |
        # Uyghur / English page labels: e.g. "4 - بەت", "بەت: 4", "Page 4", "p. 4"
        (?:بەت|page|p\.)\s*[:\-\s]*[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}
        |
        [0-9\u0660-\u0669\u06F0-\u06F9]{1,4}\s*[:\-]?\s*(?:بەت|page)
    )\s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def is_isolated_page_number(text: str) -> bool:
    """Return True if text is a standalone page number, decorated digit, or page label."""
    if not text:
        return False
    return bool(_PAGE_NUMBER_RE.match(text.strip()))


def strip_page_numbers(text: str) -> str:
    """Strip isolated header and footer page numbers from the top and bottom of page text."""
    if not text:
        return ""

    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if not blocks:
        return ""

    # Strip trailing footer page numbers
    while blocks and is_isolated_page_number(blocks[-1]):
        blocks.pop()

    # Strip leading header page numbers
    while blocks and is_isolated_page_number(blocks[0]):
        blocks.pop(0)

    if not blocks:
        return ""

    # Check if the very last line of the last block is an isolated page number
    last_lines = [line for line in blocks[-1].split("\n") if line.strip()]
    if len(last_lines) > 1 and is_isolated_page_number(last_lines[-1]):
        last_lines.pop()
        blocks[-1] = "\n".join(last_lines)

    # Check if the very first line of the first block is an isolated page number
    first_lines = [line for line in blocks[0].split("\n") if line.strip()]
    if len(first_lines) > 1 and is_isolated_page_number(first_lines[0]):
        first_lines.pop(0)
        blocks[0] = "\n".join(first_lines)

    return "\n\n".join(b for b in blocks if b.strip())


def is_poem_block(lines: list[str], width_ratio: float | None = None) -> bool:
    """Return True if the given list of lines represents a poetic verse/stanza.

    Poetic verses in Uyghur literature (Aruz and Barmaq/Heja meters) exhibit:
    - High line length uniformity (low coefficient of variation).
    - Average line lengths matching typical hemistichs (18 to 80 characters).
    - No mid-line sentence stops (terminal periods/questions followed by text).
    - No prose dialogue dashes or markdown structural markers.
    - Narrow/centered column layout (width_ratio <= 0.75) when geometry is known.
    """
    if len(lines) < 2:
        return False

    clean_lines = [line.strip() for line in lines if line.strip()]
    if len(clean_lines) < 2:
        return False

    # Disqualify markdown structural elements, list items, and dialogue dashes
    for line in clean_lines:
        if line.startswith(("#", "|", "*", "•")) or re.match(r"^\d+[.)]", line):
            return False
        if line.startswith(("-", "—", "–")):
            return False
        # Mid-line terminal punctuation followed by text is a strong prose signal
        if re.search(r"[\.؟\!]\s+[\u0600-\u06FF\w]", line):
            return False

    lengths = [len(line) for line in clean_lines]
    mean_len = sum(lengths) / len(lengths)
    variance = sum((x - mean_len) ** 2 for x in lengths) / len(lengths)
    std_len = variance**0.5
    cv = std_len / mean_len if mean_len > 0 else 1.0
    min_len = min(lengths)
    max_len = max(lengths)
    ratio = min_len / max_len if max_len > 0 else 0

    is_narrow = (width_ratio is None) or (width_ratio <= 0.75)

    # 1. Standard stanzas (4+ lines)
    if len(clean_lines) >= 4:
        if 18 <= mean_len <= 80 and cv <= 0.22 and ratio >= 0.55 and is_narrow:
            return True

    # 2. Couplets / triplets (2-3 lines)
    if len(clean_lines) in (2, 3):
        # Verse lines frequently end with commas, question marks, exclamation marks,
        # periods, semicolons, ellipsis, quotes, or Uyghur interrogative clitic 'مۇ'
        has_verse_break = any(
            line.endswith(
                (
                    "،",
                    ",",
                    "؟",
                    "?",
                    "!",
                    "!",
                    ".",
                    "…",
                    "...",
                    "؛",
                    ";",
                    ":",
                    "»",
                    '"',
                    "”",
                )
            )
            or bool(re.search(r"(?:[،,؟?!.؛;…:]|\.\.\.|»|\"|”|مۇم?)$", line))
            for line in clean_lines[:-1]
        )
        # Check if lines share common rhyme/radif endings (common in mesnevi/qoshma/ghazal)
        rhymes = False
        words = [
            re.sub(r"[^\w\u0600-\u06FF]", "", word.split()[-1])
            for word in clean_lines
            if word.split()
        ]
        if len(words) == len(clean_lines):
            for i in range(len(words) - 1):
                w1, w2 = words[i], words[i + 1]
                if w1 == w2 and len(w1) >= 3:
                    rhymes = True
                    break
                c_len = 0
                while (
                    c_len < len(w1)
                    and c_len < len(w2)
                    and w1[-(c_len + 1)] == w2[-(c_len + 1)]
                ):
                    c_len += 1
                if c_len >= 4:
                    rhymes = True
                    break

        is_explicit_narrow = width_ratio is not None and width_ratio <= 0.70

        if (has_verse_break or rhymes) and 18 <= mean_len <= 75 and cv <= 0.20:
            return True
        if is_explicit_narrow and 18 <= mean_len <= 75 and cv <= 0.15 and ratio >= 0.75:
            return True

    return False


_KEY_VALUE_LINE_RE = re.compile(r"^\s*([^\n:：]{1,35})\s*[:：]")
_SPEECH_VERBS = frozenset(
    {
        "دېدى",
        "دەيدۇ",
        "دەپتۇ",
        "دەپتىكەن",
        "سورىدى",
        "سورايدۇ",
        "پىچىرلىدى",
        "قىچقىردى",
        "ۋارقىرىدى",
    }
)
# Dialogue attributions in play-script/interview-style text are a single pronoun
# or name followed by a colon (e.g. 'ئۇ:', 'مەن:') and must not be mistaken for
# a metadata/colophon key such as 'ئاپتورى:' or 'ISBN:'.
_PRONOUNS = frozenset({"ئۇ", "مەن", "سەن", "سىز", "بىز", "سىلەر", "سىزلەر", "ئۇلار"})


def is_key_value_line(line: str) -> bool:
    """Return True if line begins with a key-value label (e.g. 'ئاپتورى:', 'ISBN:')."""
    m = _KEY_VALUE_LINE_RE.match(line.strip())
    if not m:
        return False
    key = m.group(1).strip()
    words = key.split()
    if not (1 <= len(words) <= 5):
        return False
    if any(ch in key for ch in ",،.?!:;()[]{}"):
        return False
    if len(words) == 1 and key in _PRONOUNS:
        return False
    return words[-1] not in _SPEECH_VERBS


def is_metadata_or_key_value_block(lines: list[str]) -> bool:
    """Return True if lines represent a colophon, publishing metadata, or key-value list."""
    if len(lines) < 2:
        return False

    clean_lines = [line.strip() for line in lines if line.strip()]
    if len(clean_lines) < 2:
        return False

    kv_count = sum(1 for line in clean_lines if is_key_value_line(line))
    total = len(clean_lines)

    if total == 2:
        return kv_count == 2

    # For 3+ lines: at least 2 key-value lines and at least 30% of lines match
    return kv_count >= 2 and (kv_count / total) >= 0.30


def clean_uyghur_text(text: str) -> str:
    if not text:
        return ""

    # 1. Normalize characters
    text = normalize_uyghur_chars(text)

    # 2. Correct common OCR Arabic-bias orthographic substitutions
    text = correct_uyghur_ocr_orthography(text)

    # 3. Strip OCR markers
    text = "\n".join(_OCR_MARKER_RE.sub("", line) for line in text.splitlines())

    # 4. Strip header and footer page numbers
    text = strip_page_numbers(text)

    blocks = re.split(r"\n\s*\n", text)
    cleaned_blocks = []

    dot_leader_pattern = re.compile(r"(?:[\.·•∙⋅․﹒｡]\s*){3,}|…{2,}")
    list_marker_pattern = re.compile(r"^\s*([-—–*•]|\d+[.)])\s*")
    header_prefixes = ("[Header]", "[Footer]", "#", "|")

    for block in blocks:
        if not block.strip():
            continue

        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        if is_poem_block(lines) or is_metadata_or_key_value_block(lines):
            cleaned_blocks.append("\n".join(lines))
            continue

        block_max_len = max(len(ln.lstrip()) for ln in lines)

        result_block = ""
        for idx, line in enumerate(lines):
            if idx < len(lines) - 1:
                next_line = lines[idx + 1]
                raw_line = line.lstrip()
                raw_next = next_line.lstrip()

                # Paragraph boundary signals where a line break (\n) MUST be preserved:
                # 1. Current line ends with colon introducing dialogue, quote, or list
                is_colon_intro = bool(re.search(r"[:：]\s*$", line))

                # 2. Next line is a dialogue turn starting with a dash (—, -, –)
                is_next_dialogue = bool(raw_next and raw_next[0] in "-—–")

                # 3. Next line is a list item or numbered marker
                is_next_list_marker = bool(list_marker_pattern.match(raw_next))

                # 4. Markdown headers, table rows, TOC dot leaders, or colophon key-value lines
                is_markdown_header = raw_line.startswith(header_prefixes)
                is_next_markdown_header = raw_next.startswith(header_prefixes)
                is_toc_line = bool(dot_leader_pattern.search(line))
                is_next_toc_line = bool(dot_leader_pattern.search(next_line))
                is_key_value = is_key_value_line(raw_line)
                is_next_key_value = is_key_value_line(raw_next)

                # 5. Current line is much shorter than the block's longest line -
                # a print-width wrap should read close to the block's max width,
                # so a line well under that (and long enough for the ratio to be
                # meaningful) is very likely an intentional break instead.
                is_short_relative_line = (
                    block_max_len >= 15 and len(raw_line) <= 0.6 * block_max_len
                )

                if (
                    is_colon_intro
                    or is_next_dialogue
                    or is_next_list_marker
                    or is_markdown_header
                    or is_next_markdown_header
                    or is_toc_line
                    or is_next_toc_line
                    or is_key_value
                    or is_next_key_value
                    or is_short_relative_line
                ):
                    result_block += line + "\n"
                else:
                    # Same paragraph continuation -> merge lines with space
                    result_block += line + " "
            else:
                result_block += line

        cleaned_blocks.append(result_block)

    cleaned = "\n\n".join(cleaned_blocks)
    return strip_page_numbers(cleaned)


def is_toc_page(text: str) -> bool:
    if not text:
        return False

    if "مۇندەرىجە" in text:
        return True

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return False

    pipe_table_pattern = re.compile(r"^\|.*\|\s*\d+\s*\|?$")
    pipe_count = sum(1 for line in lines if pipe_table_pattern.match(line))
    if pipe_count >= 5 and (pipe_count / len(lines)) >= 0.5:
        return True

    dot_leader_pattern = re.compile(r"(\.{6,}|_{6,}|-{6,}|·{6,})")

    dot_digit_count = 0
    edge_digits = []

    for line in lines:
        has_dots = bool(dot_leader_pattern.search(line))
        digit_match = re.search(r"(^\d+)|(\d+$)", line)

        if has_dots and digit_match:
            dot_digit_count += 1
            edge_digits.append(int(digit_match.group()))
        elif digit_match:
            edge_digits.append(int(digit_match.group()))

    if len(edge_digits) >= 5 and dot_digit_count >= 3:
        non_decreasing = sum(
            1
            for i in range(len(edge_digits) - 1)
            if edge_digits[i + 1] >= edge_digits[i]
        )
        is_increasing = (non_decreasing / (len(edge_digits) - 1)) >= 0.8

        if is_increasing and dot_digit_count >= (len(lines) * 0.3):
            return True

    if dot_digit_count >= 5 and (dot_digit_count / len(lines)) >= 0.5:
        return True

    return False


_UYGHUR_VOWELS = frozenset("ەۇۆۈېىئ")
_COMMON_ARABIC_WORDS = re.compile(
    r"\b(في|من|على|إلى|عن|هذا|هذه|الذي|التي|ذلك|تلك|الله|كان|كانت|مع|قد|ما|لم|لن|بل|إن|أن)\b"
)


def is_block_repetition_loop(text: str) -> bool:
    """Detect if a block contains a runaway repetitive decoding loop (n-grams or words)."""
    if not text:
        return False
    words = [w for w in text.split() if w.strip()]
    if len(words) < 8:
        return False

    # Check consecutive identical words
    consecutive_repeats = 1
    for i in range(1, len(words)):
        if words[i] == words[i - 1]:
            consecutive_repeats += 1
            if consecutive_repeats >= 4:
                return True
        else:
            consecutive_repeats = 1

    # Check n-gram phrase loops (n = 2..6)
    for n in range(2, 7):
        if len(words) < n * 3:
            continue
        ngrams = [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]
        counts = Counter(ngrams)
        if counts:
            _, count = counts.most_common(1)[0]
            if count >= 3 and (count * n) >= len(words) * 0.35:
                return True
    return False


def is_hallucinated_arabic_block(text: str) -> bool:
    """Detect if a text block is hallucinated Arabic text from bleed-through/noise.

    Uyghur written in Arabic script has mandatory vowel letters (ە, ى, ۇ, ۆ, ۈ, ې, ئ)
    present in virtually every word (comprising 25%-45% of all letters).
    When OCR tries to read faint bleed-through or noise, it frequently hallucinates
    Standard Arabic vocabulary with near-zero Uyghur vowel characters.
    """
    if not text:
        return False
    words = text.split()
    if len(words) < 10:
        return False

    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False

    uyghur_vowels = sum(1 for ch in letters if ch in _UYGHUR_VOWELS)
    vowel_ratio = uyghur_vowels / len(letters)

    arabic_particles = len(_COMMON_ARABIC_WORDS.findall(text))
    if vowel_ratio < 0.08 and (arabic_particles >= 2 or "ة" in text or "ه" in text):
        return True
    return False


_MAX_SANE_OCR_CHARS = 10000


def is_degenerate_ocr_output(text: str) -> bool:
    if not text:
        return False
    if len(text) > _MAX_SANE_OCR_CHARS:
        return True

    words = [w for w in text.split() if any(ch.isalnum() for ch in w)]
    if len(words) < 30:
        return False

    if is_block_repetition_loop(text):
        return True

    _, most_common_count = Counter(words).most_common(1)[0]
    return most_common_count >= 20 and (most_common_count / len(words)) >= 0.2
