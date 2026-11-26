"""
Dynamic Uyghur Morphological Analyzer & Validator (Analysis-by-Synthesis).

Validates agglutinative Uyghur surface words not explicitly materialized in the
`words` table by:
1. Peeling ordered suffix layers right-to-left (clitics, copulas/evidentials,
   relational `-دىكى/-نىڭكى` chains, case, possessive, plural, derivational
   `-لىق/-لۇق/-لىك/-لۈك` / `-سىز` / `-چە` / `-چىلىك`, and verb participles).
2. Restoring candidate stems (reversing open-syllable vowel raising `ا/ە -> ى/ې`
   and second-syllable epenthetic vowel syncope).
3. Forward re-inflecting each candidate `(root, suffix_chain)` under strict
   Modern Uyghur Imla rules (tongue harmony, labial rounding & disyllabic
   unrounding, open-syllable vowel raising, loanword final-stop devoicing, and
   uvular/velar dative dissimilation) and requiring exact surface equality.
4. Producing lightweight `MorphRequirement` anchor sets verifiable in a single
   batch lookup against the `words` table.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Phonological Inventory (Normalized Uyghur Unicode) ────────────────────────

BACK_VOWELS = frozenset({"ا", "و", "ۇ"})
FRONT_VOWELS = frozenset({"ە", "ۆ", "ۈ"})
NEUTRAL_VOWELS = frozenset({"ې", "ى"})
ALL_VOWELS = BACK_VOWELS | FRONT_VOWELS | NEUTRAL_VOWELS

BACK_ROUNDED = frozenset({"و", "ۇ"})
FRONT_ROUNDED = frozenset({"ۆ", "ۈ"})

BACK_VELARS = frozenset({"ق", "غ"})
FRONT_VELARS = frozenset({"ك", "گ"})

VOICELESS_CONSONANTS = frozenset({"پ", "ت", "چ", "خ", "س", "ش", "ف", "ق", "ك", "ھ"})
# Loanword final voiced stops/affricates devoice word-finally before consonant suffixes
FINAL_DEVOICED_STOPS = frozenset({"ب", "د", "ج"})
# Voiced uvular/velar dissimilate before dative/limitative (-غا/-گە -> -قا/-كە)
VELAR_DISSIMILATE = frozenset({"غ", "گ"})

STANDARD_UYGHUR_CHARS = frozenset("ئابپتجچخدرزژسشغفقكگڭلمنھئوۇۆۈۋېىيە")


@dataclass(frozen=True)
class MorphRequirement:
    """
    Declarative lexicon-membership requirement for one valid morphological parse.
    A parse is verified when:
      - every word in `all_of` exists in `words`, AND
      - `any_of` is empty OR at least one word in `any_of` exists in `words`, AND
      - no word in `none_of` exists in `words`.
    """

    root: str
    rule: str
    all_of: tuple[str, ...]
    any_of: tuple[str, ...] = ()
    none_of: tuple[str, ...] = ()


# ── Low-Level Phonological Helpers ────────────────────────────────────────────


def is_clean_uyghur_word(word: str) -> bool:
    return bool(word) and all(ch in STANDARD_UYGHUR_CHARS for ch in word)


def count_vowels(stem: str) -> int:
    return sum(1 for ch in stem if ch in ALL_VOWELS)


def last_vowel_info(stem: str) -> tuple[str | None, int]:
    for idx in range(len(stem) - 1, -1, -1):
        if stem[idx] in ALL_VOWELS:
            return stem[idx], idx
    return None, -1


def infer_tongue_harmony(stem: str, default: str = "front") -> str:
    lv, lv_idx = last_vowel_info(stem)
    if lv in BACK_VOWELS:
        return "back"
    if lv in FRONT_VOWELS:
        return "front"

    tail_start = max(0, lv_idx - 1) if lv_idx >= 0 else 0
    tail = stem[tail_start:]
    if any(c in FRONT_VELARS for c in tail):
        return "front"
    if any(c in BACK_VELARS for c in tail):
        return "back"

    for idx in range(lv_idx - 1, -1, -1):
        ch = stem[idx]
        if ch in BACK_VOWELS:
            return "back"
        if ch in FRONT_VOWELS:
            return "front"

    for idx in range(len(stem) - 1, -1, -1):
        if stem[idx] in BACK_VELARS:
            return "back"
        if stem[idx] in FRONT_VELARS:
            return "front"

    return default


def is_devoiced_ending(stem: str) -> bool:
    return bool(stem) and (
        stem[-1] in VOICELESS_CONSONANTS or stem[-1] in FINAL_DEVOICED_STOPS
    )


def get_epenthetic_high_vowel(stem: str, disyllabic_i_suffix: bool = False) -> str:
    if disyllabic_i_suffix:
        return "ى"
    lv, _ = last_vowel_info(stem)
    if lv in BACK_ROUNDED:
        return "ۇ"
    if lv in FRONT_ROUNDED:
        return "ۈ"
    return "ى"


def raise_open_low_vowel(
    stem: str,
    for_vowel_initial_suffix: bool,
    fixed_stress: bool = False,
) -> str:
    if fixed_stress:
        return stem
    n_vowels = count_vowels(stem)
    if n_vowels == 0:
        return stem

    if stem[-1] in ("ا", "ە"):
        repl = "ې" if n_vowels == 1 else "ى"
        return stem[:-1] + repl

    if (
        for_vowel_initial_suffix
        and len(stem) >= 2
        and stem[-1] not in ALL_VOWELS
        and stem[-2] in ("ا", "ە")
    ):
        repl = "ې" if n_vowels == 1 else "ى"
        return stem[:-2] + repl + stem[-1]

    return stem


# ── Forward Morpheme Builders (Synthesis) ─────────────────────────────────────


def forward_plural(
    stem: str, harmony: str, fixed_stress: bool = False
) -> tuple[str, str]:
    base = raise_open_low_vowel(
        stem, for_vowel_initial_suffix=False, fixed_stress=fixed_stress
    )
    return base + ("لار" if harmony == "back" else "لەر"), harmony


def forward_possessive(
    stem: str,
    person: str,
    harmony: str,
    fixed_stress: bool = False,
    syncope_stem: str | None = None,
) -> tuple[str, str]:
    if person == "none":
        return stem, harmony

    ends_in_vowel = stem[-1] in ALL_VOWELS
    if ends_in_vowel:
        if person == "1sg":
            return stem + "م", harmony
        if person == "2sg":
            return stem + "ڭ", harmony
        if person == "2pl":
            # '-ڭلار' starts with CC cluster 'ڭل', closing the final syllable
            return stem + "ڭلار", "back"

        raised = raise_open_low_vowel(
            stem, for_vowel_initial_suffix=False, fixed_stress=fixed_stress
        )
        if person == "2sg_pol":
            return raised + "ڭىز", harmony
        if person == "1pl":
            return raised + "مىز", harmony
        if person == "3":
            return raised + "سى", harmony
        raise ValueError(person)

    base = (
        syncope_stem
        if syncope_stem
        else raise_open_low_vowel(
            stem, for_vowel_initial_suffix=True, fixed_stress=fixed_stress
        )
    )
    if person == "3":
        return base + "ى", harmony
    if person == "1pl":
        v = get_epenthetic_high_vowel(base, disyllabic_i_suffix=True)
        return base + v + "مىز", harmony
    if person == "2sg_pol":
        v = get_epenthetic_high_vowel(base, disyllabic_i_suffix=True)
        return base + v + "ڭىز", harmony

    v = get_epenthetic_high_vowel(stem, disyllabic_i_suffix=False)
    if person == "1sg":
        return base + v + "م", harmony
    if person == "2sg":
        return base + v + "ڭ", harmony
    if person == "2pl":
        return base + v + "ڭلار", "back"
    raise ValueError(person)


def forward_case(
    stem: str,
    case_code: str,
    harmony: str,
    fixed_stress: bool = False,
) -> tuple[str, str]:
    if case_code == "nom":
        return stem, harmony

    base = raise_open_low_vowel(
        stem, for_vowel_initial_suffix=False, fixed_stress=fixed_stress
    )
    vl = is_devoiced_ending(base)
    vd = base[-1] in VELAR_DISSIMILATE

    if case_code == "gen":
        return base + "نىڭ", harmony
    if case_code == "acc":
        return base + "نى", harmony
    if case_code == "dat":
        use_vl = vl or vd
        suf = (
            ("قا" if use_vl else "غا")
            if harmony == "back"
            else ("كە" if use_vl else "گە")
        )
        return base + suf, harmony
    if case_code == "loc":
        suf = ("تا" if vl else "دا") if harmony == "back" else ("تە" if vl else "دە")
        return base + suf, harmony
    if case_code == "abl":
        return base + ("تىن" if vl else "دىن"), harmony
    if case_code == "lim":
        use_vl = vl or vd
        suf = (
            ("قىچە" if use_vl else "غىچە")
            if harmony == "back"
            else ("كىچە" if use_vl else "گىچە")
        )
        return base + suf, harmony
    if case_code == "sim":
        return base + ("تەك" if vl else "دەك"), "front"
    if case_code == "rel":
        return base + ("تىكى" if vl else "دىكى"), "front"
    raise ValueError(case_code)


def forward_deriv_luq(root: str, harmony: str, fixed_stress: bool = False) -> str:
    base = raise_open_low_vowel(
        root, for_vowel_initial_suffix=False, fixed_stress=fixed_stress
    )
    lv, _ = last_vowel_info(root)
    if harmony == "back":
        suf = "لۇق" if lv in BACK_ROUNDED else "لىق"
    else:
        suf = "لۈك" if lv in FRONT_ROUNDED else "لىك"
    return base + suf


def forward_clitic(
    word: str, clitic_type: str, harmony: str, fixed_stress: bool = False
) -> str:
    raised = raise_open_low_vowel(
        word, for_vowel_initial_suffix=False, fixed_stress=fixed_stress
    )
    if clitic_type in ("مۇ", "لا", "چۇ"):
        return raised + clitic_type
    if clitic_type == "غۇ":
        vl = is_devoiced_ending(raised) or (raised[-1] in VELAR_DISSIMILATE)
        if harmony == "back":
            return raised + ("قۇ" if vl else "غۇ")
        return raised + ("كۇ" if vl else "گۇ")
    raise ValueError(clitic_type)


# ── Reverse Peeling Tables ────────────────────────────────────────────────────

_CASE_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("غىچە", "lim"),
    ("گىچە", "lim"),
    ("قىچە", "lim"),
    ("كىچە", "lim"),
    ("دىكى", "rel"),
    ("تىكى", "rel"),
    ("نىڭ", "gen"),
    ("دىن", "abl"),
    ("تىن", "abl"),
    ("دەك", "sim"),
    ("تەك", "sim"),
    ("نى", "acc"),
    ("غا", "dat"),
    ("گە", "dat"),
    ("قا", "dat"),
    ("كە", "dat"),
    ("دا", "loc"),
    ("دە", "loc"),
    ("تا", "loc"),
    ("تە", "loc"),
)

_COPULA_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("كەنسىلەر", "كەنسىلەر"),
    ("كەنمەن", "كەنمەن"),
    ("كەنسەن", "كەنسەن"),
    ("كەنسىز", "كەنسىز"),
    ("كەنمىز", "كەنمىز"),
    ("سىلەر", "سىلەر"),
    ("مىكىن", "مىكىن"),
    ("مىدۇ", "مىدۇ"),
    ("دۇر", "dur"),
    ("تۇر", "dur"),
    ("كەن", "كەن"),
    ("مەن", "مەن"),
    ("سەن", "سەن"),
    ("سىز", "سىز"),
    ("مىز", "مىز"),
)


def _peel_case_options(stem: str) -> list[tuple[str, str]]:
    """Return all `(pre_case_stem, case_code)` options including `('nom')`."""
    options = [(stem, "nom")]
    for suf, code in _CASE_SUFFIXES:
        if len(stem) > len(suf) + 1 and stem.endswith(suf):
            options.append((stem[: -len(suf)], code))
    return options


def _peel_possessive_options(stem: str) -> list[tuple[str, str, bool]]:
    """
    Return `(pre_poss_stem, person_code, vowel_initial_poss)` options.
    """
    out: list[tuple[str, str, bool]] = [(stem, "none", False)]

    # 2pl: -ىڭلار / -ۇڭلار / -ۈڭلار (after C) or -ڭلار (after V)
    for v in ("ى", "ۇ", "ۈ"):
        suf = v + "ڭلار"
        if len(stem) > len(suf) + 1 and stem.endswith(suf):
            out.append((stem[: -len(suf)], "2pl", True))
    if len(stem) > 5 and stem.endswith("ڭلار") and stem[-5] in ALL_VOWELS:
        out.append((stem[:-4], "2pl", False))

    # 2sg_pol: -ىڭىز (after C) or -ڭىز (after V)
    if len(stem) > 5 and stem.endswith("ىڭىز"):
        out.append((stem[:-4], "2sg_pol", True))
    if len(stem) > 4 and stem.endswith("ڭىز") and stem[-4] in ALL_VOWELS:
        out.append((stem[:-3], "2sg_pol", False))

    # 1pl: -ىمىز (after C) or -مىز (after V)
    if len(stem) > 5 and stem.endswith("ىمىز"):
        out.append((stem[:-4], "1pl", True))
    if len(stem) > 4 and stem.endswith("مىز") and stem[-4] in ALL_VOWELS:
        out.append((stem[:-3], "1pl", False))

    # 3rd: -سى (after V) or -ى (after C)
    if len(stem) > 3 and stem.endswith("سى") and stem[-3] in ALL_VOWELS:
        out.append((stem[:-2], "3", False))
    if len(stem) > 2 and stem.endswith("ى") and stem[-2] not in ALL_VOWELS:
        out.append((stem[:-1], "3", True))

    # 1sg: -ىم / -ۇم / -ۈم (after C) or -م (after V)
    for v in ("ى", "ۇ", "ۈ"):
        suf = v + "م"
        if len(stem) > 3 and stem.endswith(suf) and stem[-3] not in ALL_VOWELS:
            out.append((stem[:-2], "1sg", True))
    if len(stem) > 2 and stem.endswith("م") and stem[-2] in ALL_VOWELS:
        out.append((stem[:-1], "1sg", False))

    # 2sg: -ىڭ / -ۇڭ / -ۈڭ (after C) or -ڭ (after V)
    for v in ("ى", "ۇ", "ۈ"):
        suf = v + "ڭ"
        if len(stem) > 3 and stem.endswith(suf) and stem[-3] not in ALL_VOWELS:
            out.append((stem[:-2], "2sg", True))
    if len(stem) > 2 and stem.endswith("ڭ") and stem[-2] in ALL_VOWELS:
        out.append((stem[:-1], "2sg", False))

    return out


def _peel_plural_options(
    stem: str, followed_by_vowel_poss: bool
) -> list[tuple[str, bool]]:
    """Return `(singular_stem, is_plural)` options."""
    out: list[tuple[str, bool]] = [(stem, False)]
    if followed_by_vowel_poss:
        if len(stem) > 4 and stem.endswith("لىر"):
            out.append((stem[:-3], True))
    else:
        if len(stem) > 4 and (stem.endswith("لار") or stem.endswith("لەر")):
            out.append((stem[:-3], True))
    return out


def _restore_root_candidates(
    stem: str,
    opened_by_vowel_suffix: bool,
    opened_by_syllabic_suffix: bool,
) -> list[tuple[str, str | None]]:
    """
    Given potentially raised/syncopated `stem`, yield `(candidate_root, syncope_stem)` pairs.
    """
    candidates: list[tuple[str, str | None]] = [(stem, None)]
    seen: set[tuple[str, str | None]] = {(stem, None)}

    def add(r: str, syn: str | None = None):
        if len(r) >= 2 and count_vowels(r) >= 1 and (r, syn) not in seen:
            seen.add((r, syn))
            candidates.append((r, syn))

    n_vowels = count_vowels(stem)

    # 1. Vowel-final stem raised before syllabic suffix: ...ى -> ...ا / ...ە (or ې -> ا/ە)
    if opened_by_syllabic_suffix and stem:
        if stem[-1] == "ى" and n_vowels >= 2:
            add(stem[:-1] + "ا")
            add(stem[:-1] + "ە")
        elif stem[-1] == "ې" and n_vowels == 1:
            add(stem[:-1] + "ا")
            add(stem[:-1] + "ە")

    # 2. Consonant-final stem raised before vowel-initial suffix: ...ىC / ...ېC -> ...اC / ...ەC
    if opened_by_vowel_suffix and len(stem) >= 2 and stem[-1] not in ALL_VOWELS:
        if stem[-2] == "ى" and n_vowels >= 2:
            add(stem[:-2] + "ا" + stem[-1])
            add(stem[:-2] + "ە" + stem[-1])
        elif stem[-2] == "ې" and n_vowels == 1:
            add(stem[:-2] + "ا" + stem[-1])
            add(stem[:-2] + "ە" + stem[-1])

        # 3. Syncope restoration: CVCC -> CVC(ى/ۇ/ۈ)C (e.g. كەسپ -> كەسىپ, ئوغل -> ئوغۇل)
        if n_vowels == 1 and len(stem) >= 3 and stem[-2] not in ALL_VOWELS:
            for ep_v in ("ى", "ۇ", "ۈ"):
                add(stem[:-1] + ep_v + stem[-1], syn=stem)

    return candidates


def _build_noun_requirements_for_np_base(
    np_stem: str,
    validate_fn,
    rule_suffix: str,
) -> list[MorphRequirement]:
    """
    Decompose a Number+Possessive(+Derivational) nominal stem `np_stem`, run
    `validate_fn(rebuilt_np_stem, np_harmony, fixed_stress)` to verify exact full-word
    synthesis match, and emit `MorphRequirement` anchor specifications.
    """
    reqs: list[MorphRequirement] = []
    seen_reqs: set[MorphRequirement] = set()

    def emit(req: MorphRequirement):
        if req not in seen_reqs:
            seen_reqs.add(req)
            reqs.append(req)

    for pre_poss, poss_code, vowel_poss in _peel_possessive_options(np_stem):
        poss_is_syllabic = poss_code not in ("none", "1sg", "2sg", "2pl")
        for pre_pl, is_pl in _peel_plural_options(pre_poss, vowel_poss):
            # Layer: bare root OR derived `-لۇق/-لىق/-لۈك/-لىك`
            deriv_variants: list[tuple[str, str | None]] = [(pre_pl, None)]
            for luq_suf in ("لۇق", "لىق", "لۈك", "لىك"):
                if len(pre_pl) > 5 and pre_pl.endswith(luq_suf):
                    deriv_variants.append((pre_pl[:-3], "luq"))

            for raw_stem, deriv_kind in deriv_variants:
                if deriv_kind == "luq":
                    opened_v = False
                    opened_syl = True
                else:
                    opened_v = (not is_pl) and vowel_poss
                    opened_syl = is_pl or ((not is_pl) and poss_is_syllabic)

                # Also pass down outer-suffix syllabic opening when no plural/possessive
                outer_syl = opened_syl or (not is_pl and poss_code == "none")

                for cand_root, syn_stem in _restore_root_candidates(
                    raw_stem,
                    opened_by_vowel_suffix=opened_v,
                    opened_by_syllabic_suffix=outer_syl,
                ):
                    # ── Verb Participle Branch (-غان/-گەن/-قان/-كەن & -مىغان/-مىگەن) ──
                    if deriv_kind is None and syn_stem is None:
                        for part_suf, v_h, is_neg in (
                            ("مىغان", "back", True),
                            ("مىگەن", "front", True),
                            ("غان", "back", False),
                            ("قان", "back", False),
                            ("گەن", "front", False),
                            ("كەن", "front", False),
                        ):
                            if len(cand_root) > len(
                                part_suf
                            ) + 1 and cand_root.endswith(part_suf):
                                v_stem = cand_root[: -len(part_suf)]
                                if count_vowels(v_stem) >= 1:
                                    use_vl = is_devoiced_ending(v_stem) or (
                                        v_stem[-1] in VELAR_DISSIMILATE
                                    )
                                    pos_part = v_stem + (
                                        ("قان" if use_vl else "غان")
                                        if v_h == "back"
                                        else ("كەن" if use_vl else "گەن")
                                    )
                                    expected_part = (
                                        v_stem + ("مىغان" if v_h == "back" else "مىگەن")
                                        if is_neg
                                        else pos_part
                                    )
                                    if expected_part == cand_root:
                                        inf = v_stem + (
                                            "ماق" if v_h == "back" else "مەك"
                                        )
                                        cur, cur_h = cand_root, v_h
                                        if is_pl:
                                            cur, cur_h = forward_plural(
                                                cur, cur_h, fixed_stress=False
                                            )
                                        cur, cur_h = forward_possessive(
                                            cur, poss_code, cur_h, fixed_stress=False
                                        )
                                        if validate_fn(cur, cur_h, False):
                                            emit(
                                                MorphRequirement(
                                                    root=inf,
                                                    rule=f"VerbPart({part_suf})+{rule_suffix}",
                                                    all_of=(inf, pos_part),
                                                )
                                            )

                    # ── Nominal Root Branch ──
                    def_h = infer_tongue_harmony(cand_root)
                    lv_cand, _ = last_vowel_info(cand_root)
                    # Try both harmonies when the root has only neutral vowels OR ends in a
                    # neutral vowel syllable (e.g. `ۋاسىتىچى` < `ۋاسىتە + چى`, front harmony
                    # masked after `ە -> ى` raising)
                    harmonies = (
                        (def_h, "back" if def_h == "front" else "front")
                        if lv_cand in NEUTRAL_VOWELS
                        else (def_h,)
                    )
                    fs_options = (False, True) if syn_stem is None else (False,)

                    for h in harmonies:
                        for fs in fs_options:
                            if deriv_kind == "luq":
                                cur = forward_deriv_luq(cand_root, h, fixed_stress=fs)
                                cur_h = h
                                cur_fs = False
                                cur_syn = None
                            else:
                                cur = cand_root
                                cur_h = h
                                cur_fs = fs
                                cur_syn = syn_stem

                            if is_pl:
                                cur, cur_h = forward_plural(
                                    cur, cur_h, fixed_stress=cur_fs
                                )
                                cur_fs = False
                                cur_syn = None

                            cur, cur_h = forward_possessive(
                                cur,
                                poss_code,
                                cur_h,
                                fixed_stress=cur_fs,
                                syncope_stem=cur_syn,
                            )

                            if not validate_fn(
                                cur,
                                cur_h,
                                cur_fs if poss_code == "none" and not is_pl else False,
                            ):
                                continue

                            # Build lexical anchor requirements for `cand_root`
                            pl_anchor, _ = forward_plural(cand_root, h, fixed_stress=fs)
                            poss3_anchor, _ = forward_possessive(
                                cand_root,
                                "3",
                                h,
                                fixed_stress=fs,
                                syncope_stem=syn_stem,
                            )
                            poss1_anchor, _ = forward_possessive(
                                cand_root,
                                "1sg",
                                h,
                                fixed_stress=fs,
                                syncope_stem=syn_stem,
                            )
                            dat_anchor, _ = forward_case(
                                cand_root, "dat", h, fixed_stress=fs
                            )
                            loc_anchor, _ = forward_case(
                                cand_root, "loc", h, fixed_stress=fs
                            )

                            all_req = [cand_root]
                            any_req: list[str] = []
                            none_req: list[str] = []

                            # Only enforce raising/fixed-stress `poss3_anchor` when a suffix actually
                            # opened `cand_root`'s final low-vowel syllable!
                            stem_vowel_tested = (
                                cand_root[-1] in ("ا", "ە") and outer_syl
                            ) or (
                                opened_v
                                and len(cand_root) >= 2
                                and cand_root[-1] not in ALL_VOWELS
                                and cand_root[-2] in ("ا", "ە")
                            )
                            if syn_stem is not None:
                                all_req.append(poss3_anchor)
                            elif stem_vowel_tested:
                                all_req.append(poss3_anchor)
                                if count_vowels(cand_root) == 1 and not fs:
                                    # Monosyllabic `ا/ە -> ې` raising: require `poss1_anchor` (e.g. `گېپىم`, `بېشىم`)
                                    # so pronouns/homophones like `سەن -> سېنى` or fixed-stress `سان -> سانى` cannot
                                    # falsely validate `سېنىمدىكى`
                                    all_req.append(poss1_anchor)
                                    fixed_poss1, _ = forward_possessive(
                                        cand_root, "1sg", h, fixed_stress=True
                                    )
                                    if fixed_poss1 != poss1_anchor:
                                        none_req.append(fixed_poss1)
                            else:
                                if cand_root[-1] == "ڭ" and is_pl:
                                    # Prevent 2sg-possessed stems (e.g. `ئېشىڭ` < `ئاش`) from taking plural
                                    # `-لار/-لىرى` after `-ڭ` (`ئېشىڭلىرىنى`), since `ئېشىڭلار` exists as 2pl
                                    # possessive (`ئاش + ىڭلار`). Genuine `ڭ`-final nouns (`رەڭ`, `تاڭ`, `چاڭ`)
                                    # have 3sg possessive `poss3_anchor` (`رېڭى`, `تېڭى`, `چېڭى`).
                                    all_req.append(poss3_anchor)

                                if h != def_h:
                                    any_req.extend([pl_anchor, dat_anchor, loc_anchor])
                                elif cand_root[-1] == "ى":
                                    # Prevent 3sg-possessed forms (e.g. `ئاپىتى` < `ئاپەت`) from pretending
                                    # to be bare `ى`-final roots (`ئاپىتىم` collides with `ئاپەت+1sg`):
                                    # real `ى`-final roots (`خىزمەتچى`, `ۋاسىتىچى`) have `-لار/-لەر` or `-سى`.
                                    any_req.extend([pl_anchor, poss3_anchor])
                                elif not is_pl and poss_code not in ("none", "3"):
                                    any_req.extend([pl_anchor, poss1_anchor])
                                else:
                                    any_req.extend(
                                        [
                                            pl_anchor,
                                            poss3_anchor,
                                            dat_anchor,
                                            loc_anchor,
                                        ]
                                    )

                            if deriv_kind == "luq":
                                derived_head = forward_deriv_luq(
                                    cand_root, h, fixed_stress=fs
                                )
                                # Either the derived `-luq` noun itself OR the base noun + nominal anchor exists
                                any_req = [derived_head, pl_anchor, poss3_anchor]

                            emit(
                                MorphRequirement(
                                    root=cand_root,
                                    rule=rule_suffix,
                                    all_of=tuple(dict.fromkeys(all_req)),
                                    any_of=tuple(dict.fromkeys(any_req)),
                                    none_of=tuple(dict.fromkeys(none_req)),
                                )
                            )

    return reqs


def _unraise_before_clitic(stem: str) -> list[str]:
    out = [stem]
    if len(stem) >= 4 and stem[-1] == "ى":
        out.append(stem[:-1] + "ا")
        out.append(stem[:-1] + "ە")
    return out


def analyze_uyghur_word(word: str) -> list[MorphRequirement]:
    """
    Analyze a normalized Uyghur word into verifiable `MorphRequirement`s.
    Returns `[]` if the word has no grammatically & orthographically valid
    agglutinative decomposition under Modern Uyghur Imla rules.
    """
    if len(word) < 4 or not is_clean_uyghur_word(word):
        return []

    results: list[MorphRequirement] = []
    seen: set[MorphRequirement] = set()

    def record_all(items: list[MorphRequirement]):
        for it in items:
            if it not in seen:
                seen.add(it)
                results.append(it)

    # ── Step 1: Optional Outer Clitic (-مۇ, -لا, -غۇ/-قۇ/-گۇ/-كۇ, -چۇ) ────────
    clitic_layers: list[tuple[str, str | None]] = [(word, None)]
    for cl_suf, cl_code in (
        ("مۇ", "مۇ"),
        ("لا", "لا"),
        ("چۇ", "چۇ"),
        ("غۇ", "غۇ"),
        ("قۇ", "غۇ"),
        ("گۇ", "غۇ"),
        ("كۇ", "غۇ"),
    ):
        if len(word) >= len(cl_suf) + 3 and word.endswith(cl_suf):
            for unraised in _unraise_before_clitic(word[: -len(cl_suf)]):
                clitic_layers.append((unraised, cl_code))

    for pre_clitic, cl_code in clitic_layers:
        # Direct shortcut when an outer clitic attaches to an already-known inflected word `pre_clitic`!
        if cl_code is not None and len(pre_clitic) >= 4:
            est_h = infer_tongue_harmony(pre_clitic)
            for h_try in (est_h, "back" if est_h == "front" else "front"):
                if forward_clitic(pre_clitic, cl_code, h_try) == word:
                    # Only emit direct shortcut if harmony matches `pre_clitic` (for -غۇ/-قۇ/-گۇ/-كۇ)
                    if cl_code != "غۇ" or h_try == est_h:
                        req = MorphRequirement(
                            root=pre_clitic,
                            rule=f"Clitic({cl_code})",
                            all_of=(pre_clitic,),
                        )
                        if req not in seen:
                            seen.add(req)
                            results.append(req)

        def _matches_outer(built_core: str, core_h: str, core_fs: bool = False) -> bool:
            if cl_code is None:
                return built_core == word
            return (
                forward_clitic(built_core, cl_code, core_h, fixed_stress=core_fs)
                == word
            )

        # ── Branch A: Core Nominal Case (including Nom) on Number+Possessive(+luq) ──
        for pre_case, case_code in _peel_case_options(pre_clitic):
            # Skip `nom` with `cl_code is None` ONLY when `pre_case == word` and no inner suffix exists?
            # Wait: `pre_case` can still have Plural + Possessive + `-luq` (e.g. `ئاپتورلىرىڭىز`, `ئاپتورلۇقۇم`)!
            def _val_case(
                np_built: str,
                np_h: str,
                np_fs: bool,
                _cc: str = case_code,
            ) -> bool:
                cased, ch = forward_case(np_built, _cc, np_h, fixed_stress=np_fs)
                if cased == word and cl_code is None and np_built == word:
                    # Bare root with zero suffixes at all — nothing to decompose
                    pass
                return _matches_outer(cased, ch, core_fs=(np_fs and _cc == "nom"))

            for r in _build_noun_requirements_for_np_base(
                pre_case,
                _val_case,
                f"Case({case_code})" + (f"+Clitic({cl_code})" if cl_code else ""),
            ):
                if r.root != word:
                    record_all([r])

        # ── Branch B: Second-Order Relational `-نىڭكى` & `-دىكى / -تىكى` ──────────
        if cl_code in (None, "مۇ", "لا"):
            # B1: `... + نىڭكى + [لەر] + [case]`
            idx_nk = pre_clitic.rfind("نىڭكى")
            if idx_nk >= 2:
                nk_base = pre_clitic[:idx_nk]
                nk_tail = pre_clitic[idx_nk + 5 :]
                # Valid tails on `نىڭكى`: '', 'لەر', or case, or 'لەر' + case
                nk_pl = False
                if nk_tail.startswith("لەر"):
                    nk_pl = True
                    nk_tail = nk_tail[3:]

                for _, t_case in _peel_case_options("كى" + nk_tail):
                    rebuilt_tail, _ = forward_case(
                        "نىڭكىلەر" if nk_pl else "نىڭكى", t_case, "front"
                    )
                    if rebuilt_tail == "نىڭكى" + ("لەر" if nk_pl else "") + nk_tail:

                        def _val_nk(
                            np_built: str,
                            np_h: str,
                            np_fs: bool,
                            _rt: str = rebuilt_tail,
                        ) -> bool:
                            gen_form, _ = forward_case(
                                np_built, "gen", np_h, fixed_stress=np_fs
                            )
                            full_nk = gen_form[:-3] + _rt
                            return _matches_outer(full_nk, "front")

                        record_all(
                            _build_noun_requirements_for_np_base(
                                nk_base, _val_nk, f"SubstGen(-ningki)+{t_case}"
                            )
                        )

            # B2: `... + (دىكى|تىكى) + [سى|لەر] + [case]`
            for diki_str in ("دىكى", "تىكى"):
                idx_dk = pre_clitic.rfind(diki_str)
                if idx_dk >= 2:
                    dk_base = pre_clitic[:idx_dk]
                    dk_tail = pre_clitic[idx_dk + 4 :]
                    if not dk_tail:
                        continue  # Bare `-دىكى` already handled by `case_code == 'rel'` in Branch A
                    if dk_tail == "چە":

                        def _val_dk_che(
                            np_built: str,
                            np_h: str,
                            np_fs: bool,
                        ) -> bool:
                            rel_form, _ = forward_case(
                                np_built, "rel", np_h, fixed_stress=np_fs
                            )
                            return _matches_outer(rel_form + "چە", "front")

                        record_all(
                            _build_noun_requirements_for_np_base(
                                dk_base, _val_dk_che, "Rel(-diki)+Deriv(-che)"
                            )
                        )
                        continue
                    nom_ext = ""
                    rem_tail = dk_tail
                    if rem_tail.startswith("سى"):
                        nom_ext = "سى"
                        rem_tail = rem_tail[2:]
                    elif rem_tail.startswith("لەر"):
                        nom_ext = "لەر"
                        rem_tail = rem_tail[3:]

                    for _, t_case in _peel_case_options("كى" + rem_tail):
                        if nom_ext == "" and t_case not in ("abl", "sim"):
                            continue
                        rebuilt_dk_tail, _ = forward_case(
                            diki_str + nom_ext, t_case, "front"
                        )
                        if rebuilt_dk_tail == diki_str + dk_tail:

                            def _val_dk(
                                np_built: str,
                                np_h: str,
                                np_fs: bool,
                                _ext: str = nom_ext,
                                _tc: str = t_case,
                            ) -> bool:
                                rel_form, _ = forward_case(
                                    np_built, "rel", np_h, fixed_stress=np_fs
                                )
                                full_dk, _ = forward_case(rel_form + _ext, _tc, "front")
                                return _matches_outer(full_dk, "front")

                            record_all(
                                _build_noun_requirements_for_np_base(
                                    dk_base, _val_dk, f"Rel(-diki{nom_ext})+{t_case}"
                                )
                            )

        # ── Branch C: Copula & Evidential Predicates (`-مەن`, `-كەن`, `-دۇر`, `-مىكىن`...) ─
        if cl_code in (None, "غۇ"):
            for cop_suf, cop_kind in _COPULA_SUFFIXES:
                if len(pre_clitic) >= len(cop_suf) + 3 and pre_clitic.endswith(cop_suf):
                    cop_base = pre_clitic[: -len(cop_suf)]

                    def _val_cop(
                        np_built: str,
                        np_h: str,
                        np_fs: bool,
                        _cs: str = cop_suf,
                        _ck: str = cop_kind,
                    ) -> bool:
                        if _ck == "dur":
                            expected_cop = (
                                "تۇر" if is_devoiced_ending(np_built) else "دۇر"
                            )
                            if _cs != expected_cop:
                                return False
                            full_cop = np_built + expected_cop
                            cop_h = np_h
                        elif _cs.startswith("كەن"):
                            base_for_ken = raise_open_low_vowel(
                                np_built,
                                for_vowel_initial_suffix=False,
                                fixed_stress=np_fs,
                            )
                            full_cop = base_for_ken + _cs
                            cop_h = "front"
                        else:
                            full_cop = np_built + _cs
                            cop_h = "front" if "ە" in _cs else np_h
                        return _matches_outer(full_cop, cop_h)

                    record_all(
                        _build_noun_requirements_for_np_base(
                            cop_base, _val_cop, f"Copula({cop_suf})"
                        )
                    )

        # ── Branch D: Privative & Equative (`-سىز`, `-سىزلىق`, `-چە`, `-چىلىك`) ───────
        if cl_code in (None, "مۇ", "لا"):
            # `-سىزلىق / -سىزلىك` + Case
            for pre_case, case_code in _peel_case_options(pre_clitic):
                for szl, sz_h in (("سىزلىق", "back"), ("سىزلىك", "front")):
                    if len(pre_case) >= len(szl) + 2 and pre_case.endswith(szl):
                        sz_root = pre_case[: -len(szl)]
                        if infer_tongue_harmony(sz_root, sz_h) == sz_h:
                            built_szl = raise_open_low_vowel(sz_root, False) + szl
                            cased_szl, ch = forward_case(built_szl, case_code, sz_h)
                            if _matches_outer(cased_szl, ch) and sz_root != word:
                                pl_a, _ = forward_plural(sz_root, sz_h)
                                p3_a, _ = forward_possessive(sz_root, "3", sz_h)
                                record_all(
                                    [
                                        MorphRequirement(
                                            root=sz_root,
                                            rule=f"Deriv(-{szl})+{case_code}",
                                            all_of=(sz_root,),
                                            any_of=(sz_root + "سىز", pl_a, p3_a),
                                        )
                                    ]
                                )

            # `-سىز`, `-چە`, `-چىلىك` on Sg / Pl / 3Poss
            for eq_suf, eq_h_out in (
                ("سىز", None),
                ("چىلىك", "front"),
                ("چە", "front"),
            ):
                if len(pre_clitic) >= len(eq_suf) + 2 and pre_clitic.endswith(eq_suf):
                    eq_base = pre_clitic[: -len(eq_suf)]

                    def _val_eq(
                        np_built: str,
                        np_h: str,
                        np_fs: bool,
                        _es: str = eq_suf,
                        _eh: str | None = eq_h_out,
                    ) -> bool:
                        b = raise_open_low_vowel(np_built, False, fixed_stress=np_fs)
                        return _matches_outer(b + _es, _eh or np_h)

                    record_all(
                        _build_noun_requirements_for_np_base(
                            eq_base, _val_eq, f"Deriv(-{eq_suf})"
                        )
                    )

        # ── Branch E: Negative 2nd-Person Verb Imperatives (`-ماڭ/-مەڭ`, `-ماڭلار/-مەڭلەر`) ─
        if cl_code is None:
            for imp_suf, imp_h, inf_suf in (
                ("ماڭلار", "back", "ماق"),
                ("مەڭلەر", "front", "مەك"),
                ("ماڭىز", "back", "ماق"),
                ("مەڭىز", "front", "مەك"),
                ("ماڭ", "back", "ماق"),
                ("مەڭ", "front", "مەك"),
            ):
                if len(pre_clitic) >= len(imp_suf) + 2 and pre_clitic.endswith(imp_suf):
                    v_stem = pre_clitic[: -len(imp_suf)]
                    if infer_tongue_harmony(v_stem, imp_h) == imp_h:
                        record_all(
                            [
                                MorphRequirement(
                                    root=v_stem + inf_suf,
                                    rule=f"NegImp(-{imp_suf})",
                                    all_of=(v_stem + inf_suf,),
                                )
                            ]
                        )

    return results


def is_word_verified_by_lexicon(
    reqs: list[MorphRequirement], known_lexicon: set[str]
) -> bool:
    """Return True if at least one `MorphRequirement` is satisfied by `known_lexicon`."""
    for req in reqs:
        if (
            all(w in known_lexicon for w in req.all_of)
            and (not req.any_of or any(w in known_lexicon for w in req.any_of))
            and not any(w in known_lexicon for w in req.none_of)
        ):
            return True
    return False


def collect_lexicon_probes(reqs_by_word: dict[str, list[MorphRequirement]]) -> set[str]:
    """Collect all unique `words`-table probe strings needed across a batch of analyses."""
    probes: set[str] = set()
    for reqs in reqs_by_word.values():
        for req in reqs:
            probes.update(req.all_of)
            probes.update(req.any_of)
            probes.update(req.none_of)
    return probes
