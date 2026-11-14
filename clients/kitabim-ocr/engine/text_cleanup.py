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

    text = text.replace("\x00", "")
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


_OCR_MARKER_RE = re.compile(r"\s*\[(?:Header|Footer)\].*", re.IGNORECASE)
_SURYA_COMPACT_TOKEN_RE = re.compile(r"<\|(?:\d{1,4}|box|[A-Za-z-]+)\|>")

_DIGIT_TRANSLATION = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_digits(text: str) -> str:
    """Normalize Arabic-Indic (٠-٩) and Persian (۰-۹) digits to ASCII 0-9."""
    if not text:
        return ""
    return text.translate(_DIGIT_TRANSLATION)


_DIGITS_1_4 = r"[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}"
_PAGE_NUMBER_RE = re.compile(
    rf"""^\s*
    (?:
        # Bare standalone digits: e.g. "4", "123", "١٢"
        {_DIGITS_1_4}
        |
        # Paired brackets / parentheses: e.g. "( 12 )", "[3]", "{{ 4 }}"
        \(\s*{_DIGITS_1_4}\s*\)
        |
        \[\s*{_DIGITS_1_4}\s*\]
        |
        \{{\s*{_DIGITS_1_4}\s*\}}
        |
        # Symmetric dashes / dots / stars / tildes / slashes: e.g. "- 4 -", "— 12 —", "· 4 ·", "~ 15 ~"
        [-—–•·*~/\\]+\s*{_DIGITS_1_4}\s*[-—–•·*~/\\]+
        |
        # Uyghur / English page labels: e.g. "4 - بەت", "بەت: 4", "Page 4", "p. 4"
        (?:بەت|page|p\.)\s*[:\-\s]*{_DIGITS_1_4}
        |
        {_DIGITS_1_4}\s*[:\-]?\s*(?:بەت|page)
    )\s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def is_isolated_page_number(text: str) -> bool:
    """Return True if text is a standalone page number, decorated digit, or page label."""
    if not text:
        return False
    return bool(_PAGE_NUMBER_RE.match(text.strip()))


def extract_standalone_page_number(text: str) -> int | None:
    """Extract printed page number from header or footer if it represents a standalone page number.

    Supports ASCII, Uyghur, and Arabic numeral scripts (e.g., '1', '١', '- 1 -', '~ 15 ~').
    Never applies Latin letter-to-digit substitution to multi-word running headers.
    """
    if not text or not text.strip():
        return None

    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    if not lines:
        return None

    candidate_lines = lines[:2] + lines[-2:]
    for line in candidate_lines:
        if is_isolated_page_number(line):
            ascii_line = normalize_digits(line)
            m = re.search(r"(\d{1,4})", ascii_line)
            if m:
                num = int(m.group(1))
                if 1 <= num <= 5000:
                    return num
        ascii_line = normalize_digits(line)
        match = re.search(
            r"^\s*(?:[-~—\s]*|page\s*)?(\d{1,4})\s*[-~—\s]*$",
            ascii_line,
            re.IGNORECASE,
        )
        if match:
            num = int(match.group(1))
            if 1 <= num <= 5000:
                return num

    return None


def strip_page_numbers_with_capture(text: str) -> tuple[str, int | None]:
    """Strip isolated header/footer page numbers and return `(stripped_text, detected_page_number)`.

    Prefers bottom/footer standalone page numbers over top/header standalone page numbers.
    """
    if not text:
        return "", None

    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if not blocks:
        return "", None

    footer_num: int | None = None
    header_num: int | None = None

    # Strip trailing footer page numbers
    while blocks and is_isolated_page_number(blocks[-1]):
        cand = extract_standalone_page_number(blocks.pop())
        if footer_num is None and cand is not None:
            footer_num = cand

    # Strip leading header page numbers
    while blocks and is_isolated_page_number(blocks[0]):
        cand = extract_standalone_page_number(blocks.pop(0))
        if header_num is None and cand is not None:
            header_num = cand

    if not blocks:
        return "", footer_num if footer_num is not None else header_num

    # Check if the very last line of the last block is an isolated page number
    last_lines = [line for line in blocks[-1].split("\n") if line.strip()]
    if len(last_lines) > 1 and is_isolated_page_number(last_lines[-1]):
        cand = extract_standalone_page_number(last_lines.pop())
        if footer_num is None and cand is not None:
            footer_num = cand
        blocks[-1] = "\n".join(last_lines)

    # Check if the very first line of the first block is an isolated page number
    first_lines = [line for line in blocks[0].split("\n") if line.strip()]
    if len(first_lines) > 1 and is_isolated_page_number(first_lines[0]):
        cand = extract_standalone_page_number(first_lines.pop(0))
        if header_num is None and cand is not None:
            header_num = cand
        blocks[0] = "\n".join(first_lines)

    cleaned = "\n\n".join(b for b in blocks if b.strip())
    return cleaned, (footer_num if footer_num is not None else header_num)


def strip_page_numbers(text: str) -> str:
    """Strip isolated header and footer page numbers from the top and bottom of page text."""
    return strip_page_numbers_with_capture(text)[0]


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

    # 2. Strip OCR markers and any leaked Surya compact coordinate/tag tokens
    cleaned_lines = []
    for line in text.splitlines():
        line = _OCR_MARKER_RE.sub("", line)
        if "<|" in line:
            line = re.sub(r" {2,}", " ", _SURYA_COMPACT_TOKEN_RE.sub("", line))
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    # 3. Strip header and footer page numbers
    text = strip_page_numbers(text)

    # Lines are kept exactly as OCR'd within each block - never reflowed/
    # merged into flowing prose with spaces, and never split apart into
    # separate paragraphs. The text should read exactly as it appears on
    # the printed page.
    blocks = re.split(r"\n\s*\n", text)
    cleaned_blocks = []

    for block in blocks:
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        cleaned_blocks.append("\n".join(lines))

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

    pipe_table_pattern = re.compile(
        r"^\|.*\|\s*[0-9\u0660-\u0669\u06F0-\u06F9]+\s*\|?$"
    )
    pipe_count = sum(1 for line in lines if pipe_table_pattern.match(line))
    if pipe_count >= 5 and (pipe_count / len(lines)) >= 0.5:
        return True

    two_col_pipe_pattern = re.compile(
        r"^\|\s*[^|]+?\s*\|\s*([0-9\u0660-\u0669\u06F0-\u06F9]{1,4})\s*\|?$"
    )
    table_sep_pattern = re.compile(r"^\|\s*[:\-]+\s*\|")
    if not any(table_sep_pattern.match(line) for line in lines):
        two_col_nums = [
            int(
                m.group(1).translate(
                    str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
                )
            )
            for line in lines
            if (m := two_col_pipe_pattern.match(line))
        ]
        if len(two_col_nums) >= 3 and (len(two_col_nums) / len(lines)) >= 0.5:
            non_dec = sum(
                1
                for i in range(len(two_col_nums) - 1)
                if two_col_nums[i + 1] >= two_col_nums[i]
            )
            if non_dec / (len(two_col_nums) - 1) >= 0.75:
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
# Consonants present in Uyghur/Turkic/Persian script that never occur in Standard Arabic
_UYGHUR_SPECIFIC_CONSONANTS = frozenset("پچژگڭۋ")
# Arabic vocalization marks (harakat / tashkeel) found in printed Quranic/Hadith quotations
_ARABIC_TASHKEEL = frozenset("\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652\u0670")
_COMMON_ARABIC_WORDS = re.compile(
    r"\b(في|من|على|إلى|عن|هذا|هذه|الذي|التي|ذلك|تلك|الله|كان|كانت|مع|قد|ما|لم|لن|بل|إن|أن)\b"
)
_ALPHA_WORD_RE = re.compile(r"(?:[^\W\d_]|[\u064B-\u065F])+")
_ALNUM_WORD_RE = re.compile(r"(?:[^\W_]|[\u064B-\u065F])+")
# Productive Uyghur suffix-boundary sequences that legitimately repeat 2-3 letters across morphemes
_UYGHUR_MORPH_REPEAT_RE = re.compile(
    r"(?:ىشىش|ۈشۈش|ۇشۇش|ىشلا|نغانغا|نگەنگە|ردۇر|لارلا|لەرلە|نىمنى|نىڭنى|لىكلىك|لىقلىق|لۇقلۇق|لۈكلۈك)"
)
_PUNCT_SEP_CHARS = frozenset(".,،;؛!؟?-—–…·•_~")


def _normalize_words_for_span(text: str) -> list[str]:
    return _ALNUM_WORD_RE.findall(text)


def extract_word_spans(
    text: str,
    min_words: int = 8,
) -> list[tuple[str, ...]]:
    words = _normalize_words_for_span(text)
    if len(words) < min_words:
        return []
    return [tuple(words[i : i + min_words]) for i in range(len(words) - min_words + 1)]


def add_word_spans(
    text: str,
    seen_spans: set[tuple[str, ...]],
    min_words: int = 8,
) -> None:
    """Add all ``min_words`` word spans from ``text`` into ``seen_spans``."""
    for span in extract_word_spans(text, min_words=min_words):
        seen_spans.add(span)


def has_repeated_word_span(
    text: str,
    min_words: int = 8,
    seen_spans: set[tuple[str, ...]] | None = None,
) -> bool:
    """True if any run of ``min_words`` consecutive words occurs twice in ``text``,
    or matches any span already present in ``seen_spans``.

    Catches both intra-block decoder loops (re-emitting a line inside a block)
    and cross-block repetition loops (repeating a stanza or sentence from
    earlier on the page at the bottom/margin).
    """
    spans = extract_word_spans(text, min_words=min_words)
    if not spans:
        return False
    local_seen: set[tuple[str, ...]] = set()
    for span in spans:
        if span in local_seen:
            return True
        if seen_spans is not None and span in seen_spans:
            return True
        local_seen.add(span)
    return False


def _is_pipe_table_block(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    pipe_lines = sum(1 for line in lines if "|" in line)
    return pipe_lines >= 2 and pipe_lines >= len(lines) * 0.5


_DOT_LEADER_LINE_RE = re.compile(r"\.{4,}|·{4,}|…{3,}")


def _is_dot_leader_toc_block(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    leader_lines = sum(1 for line in lines if _DOT_LEADER_LINE_RE.search(line))
    return leader_lines >= 2 and leader_lines >= len(lines) * 0.4


def is_block_repetition_loop(text: str) -> bool:
    """Detect if a block contains a runaway repetitive decoding loop (n-grams or words)."""
    if not text:
        return False

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if (
        _is_pipe_table_block(lines)
        or _is_dot_leader_toc_block(lines)
        or (
            len(lines) >= 2
            and (is_poem_block(lines) or is_metadata_or_key_value_block(lines))
        )
    ):
        return False

    # Check consecutive identical words.
    # Distinguish unpunctuated token loops ('چىسىم چىسىم چىسىم چىسىم') from punctuated
    # literary vocalizations/onomatopoeia ('تاك..... تاك..... تاك..... تاك.....',
    # 'ياق، ياق، ياق، ياق!', 'ھۈ - ھۈ - ھۈ ...') where punctuation or dashes separate repeats.
    unpunct_repeats = 0
    punct_repeats = 0
    prev_word = ""
    had_sep = False
    for tok in text.split():
        letters = "".join(_ALPHA_WORD_RE.findall(tok))
        has_leading_sep = bool(tok) and tok[0] in _PUNCT_SEP_CHARS
        has_trailing_sep = bool(tok) and tok[-1] in _PUNCT_SEP_CHARS
        if not letters:
            had_sep = True
            unpunct_repeats = 0
            continue
        if letters == prev_word:
            punct_repeats += 1
            if had_sep or has_leading_sep:
                unpunct_repeats = 1
            else:
                unpunct_repeats += 1
            if len(letters) >= 3 and unpunct_repeats >= 4:
                return True
            if len(letters) == 2 and unpunct_repeats >= 6:
                return True
            if len(letters) >= 3 and punct_repeats >= 8:
                return True
        else:
            prev_word = letters
            unpunct_repeats = 1
            punct_repeats = 1
        had_sep = has_trailing_sep

    words = _ALNUM_WORD_RE.findall(text)
    if len(words) < 8:
        return False

    # Check 1: Tandem (back-to-back) phrase loops of period L = 2..12.
    # Autoregressive decoder loops repeat a phrase immediately back-to-back without
    # varying nouns/clauses in between, whereas human enumerations, recipes, and
    # rhetorical parallelism vary the words between repeated refrains/units.
    max_period = min(12, len(words) // 2)
    for period in range(2, max_period + 1):
        min_tandem = 4 if period == 2 else (3 if period <= 7 else 2)
        if len(words) < period * min_tandem:
            continue
        idx = 0
        while idx <= len(words) - period * min_tandem:
            unit = words[idx : idx + period]
            # Repeated single short interjection ('ھۈ', 'ھا') is handled by word check above
            if len(set(unit)) == 1 and len(unit[0]) <= 3:
                idx += 1
                continue
            copies = 1
            while (
                idx + (copies + 1) * period <= len(words)
                and words[idx + copies * period : idx + (copies + 1) * period] == unit
            ):
                copies += 1
            if copies >= min_tandem:
                if (
                    period >= 8
                    and copies == 2
                    and (copies * period) < len(words) * 0.55
                ):
                    idx += 1
                    continue
                return True
            idx += 1

    # Check 2: Non-adjacent phrase loop with severe overall vocabulary collapse
    # (e.g. numbered decoder loops '(8) X ... (9) X ... (10) X ...').
    colon_count = text.count(":") + text.count("：")
    vocab_ratio = len(set(words)) / len(words)
    if colon_count < 3 and vocab_ratio < 0.32:
        for n in range(4, 7):
            if len(words) < n * 4:
                continue
            counts = Counter(tuple(words[i : i + n]) for i in range(len(words) - n + 1))
            for ng, raw_count in counts.most_common(2):
                if raw_count < 4:
                    break
                non_overlap = 0
                idx = 0
                while idx <= len(words) - n:
                    if tuple(words[idx : idx + n]) == ng:
                        non_overlap += 1
                        idx += n
                    else:
                        idx += 1
                if non_overlap >= 4 and (non_overlap * n) >= len(words) * 0.55:
                    return True
    return False


def is_hallucinated_arabic_block(text: str) -> bool:
    """Detect if a text block is hallucinated Arabic text from bleed-through/noise.

    Uyghur written in Arabic script has mandatory vowel letters (ە, ى, ۇ, ۆ, ۈ, ې, ئ)
    present in virtually every word (comprising 25%-45% of all letters).
    When OCR tries to read faint bleed-through or noise, it frequently hallucinates
    unvocalized Standard Arabic vocabulary with near-zero Uyghur vowel characters.
    """
    if not text:
        return False
    words = text.split()
    if len(words) < 10:
        return False

    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False

    # Standard Arabic never contains Uyghur/Turkic-specific consonants (پ, چ, ژ, گ, ڭ, ۋ);
    # older Uyghur orthography or OCR 'ه'-for-'ە' substitutions still carry these letters.
    turkic_consonants = sum(1 for ch in letters if ch in _UYGHUR_SPECIFIC_CONSONANTS)
    if turkic_consonants >= 2:
        return False

    # Vocalized Arabic quotations (Quranic verses / Hadiths printed with harakat/tashkeel)
    # are genuine book content, whereas Surya bleed-through hallucinations are unvocalized.
    tashkeel_count = sum(1 for ch in text if ch in _ARABIC_TASHKEEL)
    if (tashkeel_count / len(letters)) >= 0.15:
        return False

    uyghur_vowels = sum(1 for ch in letters if ch in _UYGHUR_VOWELS)
    vowel_ratio = uyghur_vowels / len(letters)

    arabic_particles = len(_COMMON_ARABIC_WORDS.findall(text))
    if vowel_ratio < 0.08 and (
        arabic_particles >= 2
        or (
            arabic_particles >= 1
            and vowel_ratio < 0.04
            and ("ة" in text or "ه" in text)
        )
    ):
        return True
    return False


# High-frequency Uyghur postpositions, auxiliaries, and copulas that legitimately
# repeat across parallel clauses (e.g. 'X ئۈچۈن، Y ئۈچۈن، Z ئۈچۈن', 'مۇقام دېمەك — سۆيگۈ دېمەك')
_UYGHUR_GRAMMATICAL_REPEATS = frozenset(
    {
        "ئۈچۈن",
        "بىلەن",
        "دېمەك",
        "كېرەك",
        "لازىم",
        "بولۇپ",
        "بولدى",
        "بولسا",
        "بولمايدۇ",
        "ئەمەس",
        "قانداق",
        "شۇنداق",
        "بۇنداق",
    }
)


def is_hallucinated_ghost_text(text: str) -> bool:
    """Detect if a block is pseudo-Uyghur hallucination from bleed-through or visual noise.

    When Surya decodes faint show-through, it often hallucinates garbled pseudo-Uyghur words
    with severe internal syllable repetition loops (e.g. 'رختسملىملىم', 'قىلىمىلىم', 'رەسمىلىملىم')
    or heavily repeated words across a block (e.g. 4 copies of 'بىلىملىرى' plus repeated stems).
    """
    if not text:
        return False

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if _is_pipe_table_block(lines) or _is_dot_leader_toc_block(lines):
        return False
    if len(lines) >= 2 and (
        is_poem_block(lines) or is_metadata_or_key_value_block(lines)
    ):
        return False

    alpha_words = [w for w in _ALPHA_WORD_RE.findall(text) if len(w) >= 2]
    if len(alpha_words) < 6:
        return False
    alnum_tokens = [w for w in _ALNUM_WORD_RE.findall(text) if len(w) >= 1]
    denom = max(len(alpha_words), len(alnum_tokens))

    # Check 1: Syllable repetition loops inside garbled words (e.g. رختسملىملىم, قىلىملىم, نەچەچە)
    # Excludes productive Uyghur suffix combinations (e.g. -ىشىش, -لانغانغا) and normal words
    # written in older 'ه' orthography that have no internal syllable loop.
    has_foreign_heh = "\u0647" in text
    repetition_word_count = 0
    for w in alpha_words:
        if _UYGHUR_MORPH_REPEAT_RE.search(w):
            continue
        if re.search(r"([^\W\d_]{2,3})\1\1", w):
            repetition_word_count += 1
        elif len(w) >= 8 and re.search(r"^.{2,}([^\W\d_]{3})\1", w):
            repetition_word_count += 1
        elif has_foreign_heh and len(w) >= 6 and re.search(r"^.{1,}([^\W\d_]{2})\1", w):
            repetition_word_count += 1

    if (
        repetition_word_count >= 2
        and (repetition_word_count / len(alpha_words)) >= 0.20
    ):
        return True

    # Check 2: Heavy duplication of multi-letter lexical content words (len >= 4).
    # Rule-of-three exclamations ('ئالدىراڭلار! ئالدىراڭلار!! ئالدىراڭلار!!', 'ئەنۋەر! ئەنۋەر! ... ئەنۋەر')
    # and single-pivot anaphora ('توققۇز ئاي، توققۇز كۈن، توققۇز سائەت، توققۇز مىنۇت') are normal
    # prose/dialogue; ghost-text bleed-through repeats multiple distinct words or >=55% of one word.
    content_words = [w for w in alpha_words if len(w) >= 4]
    lexical_counts = Counter(
        w for w in content_words if w not in _UYGHUR_GRAMMATICAL_REPEATS
    )
    all_content_counts = Counter(content_words)
    if lexical_counts and len(alpha_words) >= 8:
        _, top_count = lexical_counts.most_common(1)[0]
        if top_count >= 5 and (top_count / denom) >= 0.55:
            return True
        distinct_repeated = sum(1 for c in all_content_counts.values() if c >= 2)
        repeated_content_tokens = sum(c for c in all_content_counts.values() if c >= 2)
        if (
            top_count >= 4
            and distinct_repeated >= 2
            and (top_count / denom) >= 0.28
            and (repeated_content_tokens / denom) >= 0.50
        ):
            return True

    # Check 3: Extreme vocabulary collapse across medium/long blocks
    if 12 <= len(content_words) <= 80:
        if (len(all_content_counts) / len(content_words)) < 0.28:
            return True

    return False


_MAX_SANE_OCR_CHARS = 10000


def _has_consecutive_identical_units(units: list[str], min_repeats: int = 4) -> bool:
    """Return True if at least ``min_repeats`` consecutive non-trivial lines/blocks are identical."""
    streak = 0
    prev = ""
    for u in units:
        norm = " ".join(_ALNUM_WORD_RE.findall(u))
        if len(norm.split()) < 2:
            streak = 0
            prev = ""
            continue
        if norm == prev:
            streak += 1
            if streak >= min_repeats:
                return True
        else:
            prev = norm
            streak = 1
    return False


def is_degenerate_ocr_output(text: str) -> bool:
    if not text:
        return False
    if len(text) > _MAX_SANE_OCR_CHARS:
        return True

    alnum_words = _ALNUM_WORD_RE.findall(text)
    if len(alnum_words) < 30:
        return False

    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if any(is_block_repetition_loop(b) for b in blocks):
        return True

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if _has_consecutive_identical_units(
        blocks, min_repeats=4
    ) or _has_consecutive_identical_units(lines, min_repeats=4):
        return True

    multi_char_words = [w for w in alnum_words if len(w) >= 2]
    if not multi_char_words:
        return False
    _, most_common_count = Counter(multi_char_words).most_common(1)[0]
    return most_common_count >= 20 and (most_common_count / len(alnum_words)) >= 0.2
