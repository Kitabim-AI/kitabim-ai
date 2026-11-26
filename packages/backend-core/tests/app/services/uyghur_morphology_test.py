import pytest
from app.services.uyghur_morphology import (
    analyze_uyghur_word,
    is_word_verified_by_lexicon,
)

BASE_LEXICON = {
    # `ئاپتور` (rounded back stem)
    "ئاپتور",
    "ئاپتورلار",
    "ئاپتورى",
    "ئاپتورۇم",
    "ئاپتورغا",
    "ئاپتوردا",
    "ئاپتورلۇق",
    "ئاپتورسىز",
    # `كىتاب` (final-devoiced `ب` loanword)
    "كىتاب",
    "كىتابلار",
    "كىتابى",
    "كىتابتا",
    "كىتابقا",
    # `مەكتەپ` (polysyllabic raising `ە -> ى`)
    "مەكتەپ",
    "مەكتەپلەر",
    "مەكتىپى",
    "مەكتەپتە",
    # `گەپ` (monosyllabic raising `ە -> ې`)
    "گەپ",
    "گەپلەر",
    "گېپى",
    "گېپىم",
    # `سان` (fixed-stress monosyllable, plus homophone `سېنى` "you")
    "سان",
    "سانلار",
    "سانى",
    "سانىم",
    "سەن",
    "سەنلەر",
    "سېنى",
    "سېنىدە",
    # `قول` / `كۆز` (rounded monosyllables)
    "قول",
    "قوللار",
    "قولى",
    "قولۇم",
    "كۆز",
    "كۆزلەر",
    "كۆزى",
    "كۆزۈم",
    # `تاغ` (uvular `غ` dative dissimilation)
    "تاغ",
    "تاغلار",
    "تېغى",
    "تاغدا",
    "تاغقا",
    # `ئانا` / `ئاپەت` (vowel-final raising & underlying front harmony retention)
    "ئانا",
    "ئانىلار",
    "ئانىسى",
    "ئانام",
    "ئاپەت",
    "ئاپەتلەر",
    "ئاپىتى",
    "ئاپىتىم",
    # `كەسىپ` (second-syllable syncope)
    "كەسىپ",
    "كەسىپلەر",
    "كەسپى",
    "كەسپىم",
    # Verbs
    "جازالىماق",
    "جازالىغان",
    "ئولتۇرماق",
    "ئولتۇرغان",
    "ئۆتكۈزمەك",
    "رەنجىمەك",
    # Possessed homograph guard (`ئاش -> ئېشىڭ / ئېشىڭلار`)
    "ئاش",
    "ئېشى",
    "ئېشىم",
    "ئېشىڭ",
    "ئېشىڭلار",
}


@pytest.mark.parametrize(
    "valid_word",
    [
        # Core inflections, possessives, cases on `ئاپتور`
        "ئاپتورۇمنىڭ",
        "ئاپتورۇڭغا",
        "ئاپتورىڭىزنىڭ",
        "ئاپتورۇڭلارغا",
        "ئاپتورىمىزدىن",
        "ئاپتورلىرىمنىڭ",
        "ئاپتورلىرىڭىزغا",
        "ئاپتورلىرىڭلاردىن",
        # Relational `-دىكى` & Substantive Genitive `-نىڭكى`
        "ئاپتورۇمدىكى",
        "ئاپتوردىكىلەرنىڭ",
        "ئاپتورىڭىزنىڭكىگە",
        "ئاپتورلىرىمىزنىڭكىلەردىن",
        # Clitics (`-مۇ`, `-لا`, `-غۇ`, `-چۇ`) with open-syllable raising
        "ئاپتوردىلا",
        "ئاپتوردىغۇ",
        "ئاپتوردىچۇ",
        "ئاپتورۇمغىمۇ",
        # Copulas & Evidentials
        "ئاپتورمەن",
        "ئاپتوركەنسىز",
        "ئاپتورىمىزدۇر",
        "ئاپتورلىرىكەن",
        # Derivational `-لۇق`, `-سىزلىق`, `-چە`, `-چىلىك`
        "ئاپتورلۇقۇمنىڭ",
        "ئاپتورلۇقىمىزغا",
        "ئاپتورلۇققىمۇ",
        "ئاپتورسىزلىقتىن",
        "ئاپتورلارچە",
        "ئاپتورچىلىك",
        # Vowel raising, rounding/unrounding, syncope, devoicing, verb participles
        "كىتابلىرىمىزغا",
        "مەكتىپىمىزدىكى",
        "گېپىمىزدىكى",
        "قولىمىزغا",
        "كۆزىڭىزنىڭ",
        "تاغقىچە",
        "ئانىلىرىمىزغا",
        "ئاناڭلارنىڭ",
        "ئاپىتىمگە",
        "كەسپىمىزگە",
        "جازالىغانلىرىمنى",
        "ئولتۇرمىغانلىرىنى",
        "ئاپتوردىكىچە",
        "ئۆتكۈزمەڭلەر",
        "رەنجىمەڭلەر",
    ],
)
def test_accepts_valid_uyghur_extended_forms(valid_word: str):
    reqs = analyze_uyghur_word(valid_word)
    assert is_word_verified_by_lexicon(
        reqs, BASE_LEXICON
    ), f"Should accept {valid_word}"


@pytest.mark.parametrize(
    "invalid_word",
    [
        "كىتابلېرى",  # Wrong polysyllabic `ې` instead of `ى`
        "كىتابدا",  # Wrong voiced `-دا` after final-devoiced `ب`
        "كىتابغا",  # Wrong voiced `-غا` after final-devoiced `ب`
        "تاغغا",  # Missing uvular dissimilation `غ+غ -> غق`
        "ئاپتورۇمىز",  # Missing disyllabic unrounding on `-ىمىز`
        "قولۇمىز",  # Missing disyllabic unrounding on `-ىمىز`
        "كۆزۈڭىز",  # Missing disyllabic unrounding on `-ىڭىز`
        "ئاپتورلەر",  # Wrong front harmony on back stem
        "ئاپتورداغۇ",  # Missing open-syllable raising before `-غۇ`
        "مەكتەپى",  # Missing polysyllabic vowel raising
        "ئانالار",  # Missing vowel-final open-syllable raising
        "ئاپىتىمغا",  # Lost underlying front harmony of `ئاپەت`
        "سېنىمدىكى",  # Fixed-stress `سان` / pronoun `سەن` collision
        "ئاپتورلىرىكىزغا",  # OCR `ك` for `ڭ`
        "ئېشىڭلىرىنى",  # Cannot attach plural `-لىرى` after 2sg possessive `-ڭ`
    ],
)
def test_rejects_misspelled_uyghur_forms(invalid_word: str):
    reqs = analyze_uyghur_word(invalid_word)
    assert not is_word_verified_by_lexicon(
        reqs, BASE_LEXICON
    ), f"Should reject {invalid_word}"
