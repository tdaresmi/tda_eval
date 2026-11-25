"""Test group 5: Turkish normalization. Examples stored in categories.json are executed against the real code."""
import unicodedata

import pytest

from tda_eval.normalize import normalize, score_exact_match, tr_lower, tr_upper


def _examples(cats, profile):
    return [(e["input"], e["output"]) for e in cats["normalization_profiles"][profile]["examples"]]


@pytest.mark.parametrize("profile", ["tr_text", "tr_text_case_sensitive", "none"])
def test_examples_in_categories_json(cats, profile):
    for given, expected in _examples(cats, profile):
        assert normalize(given, profile) == expected, (profile, given)


@pytest.mark.parametrize("given,expected", [
    ("I", "ı"), ("İ", "i"), ("ı", "ı"), ("i", "i"),
    ("ISPARTA", "ısparta"), ("İSTANBUL", "istanbul"), ("Iğdır", "ığdır"), ("IŞIK", "ışık"),
    ("ÇAĞRI ÖĞRENCİ ÜÇ", "çağrı öğrenci üç"),
])
def test_turkish_lowercase_table(given, expected):
    assert tr_lower(given) == expected
    assert normalize(given, "tr_text") == expected


def test_python_default_lowering_is_wrong_for_turkish_which_is_why_we_do_not_use_it():
    assert "İ".lower() != "i" and len("İ".lower()) == 2
    assert "I".lower() == "i"  # would merge distinct Turkish letters
    assert tr_lower("I") != tr_lower("İ")
    assert normalize("I", "tr_text") != normalize("İ", "tr_text")  # ı vs i stay different letters


@pytest.mark.parametrize("given", ["İstanbul", "İstanbul", "i̇stanbul", "istanbul"])
def test_decomposed_dotted_capital_i_and_combining_dot_artifact(given):
    assert normalize(given, "tr_text") == "istanbul"


def test_nfc_is_applied_and_nfkc_is_not():
    decomposed = "ç" + "a" + "ğ"  # ç + a + ğ in NFD
    assert normalize(decomposed, "tr_text") == "çağ"
    assert unicodedata.is_normalized("NFC", normalize(decomposed, "tr_text"))
    assert normalize("CO₂", "tr_text") != normalize("CO2", "tr_text")  # CO₂ is not CO2 (no NFKC)
    assert normalize("ﬁ", "tr_text") == "ﬁ"  # 'ﬁ' ligature untouched (no compatibility folding)


@pytest.mark.parametrize("a,b", [("kâr", "kar"), ("sık", "sik"), ("şu", "su"), ("ağa", "aga"), ("güzel", "guzel"),
                                 ("çok", "cok"), ("ölçü", "olcu"), ("dûr", "dur"), ("îman", "iman")])
def test_meaning_bearing_letters_are_never_merged(a, b):
    assert normalize(a, "tr_text") != normalize(b, "tr_text")
    assert normalize(a, "tr_text_case_sensitive") != normalize(b, "tr_text_case_sensitive")


def test_circumflex_letters_are_kept():
    assert normalize("KÂR", "tr_text") == "kâr"
    assert normalize("Hâlâ", "tr_text") == "hâlâ"


@pytest.mark.parametrize("given", ["a​b", "a‌b", "a‍b", "a⁠b", "a﻿b"])
def test_zero_width_characters_are_removed(given):
    assert normalize(given, "tr_text") == "ab"
    assert normalize(given, "tr_text_case_sensitive") == "ab"


@pytest.mark.parametrize("given", ["a b", "a b", "a \t\n b", "a b", "  a   b  "])
def test_whitespace_is_collapsed_to_single_spaces(given):
    assert normalize(given, "tr_text") == "a b"


@pytest.mark.parametrize("given", ["izmir’de", "izmir‘de", "izmirʼde", "izmir'de"])
def test_apostrophes_are_unified(given):
    assert normalize(given, "tr_text") == "izmir'de"


def test_trimming_only_touches_the_ends():
    assert normalize("«Selanik».", "tr_text") == "selanik"
    assert normalize("a. b, c", "tr_text") == "a. b, c"
    assert normalize("(Selanik)", "tr_text") == "(selanik)"


def test_none_profile_is_the_identity():
    exotic = "  İzmir’de ​  İ ç̧  \n"
    assert normalize(exotic, "none") is exotic
    assert normalize("", "none") == ""


def test_case_sensitive_profile_keeps_case_and_dotted_letters():
    assert normalize("İzmir’de.", "tr_text_case_sensitive") == "İzmir'de"
    assert normalize("Iğdır", "tr_text_case_sensitive") == "Iğdır"


@pytest.mark.parametrize("profile", ["tr_text", "tr_text_case_sensitive"])
@pytest.mark.parametrize("given", ["İSTANBUL’da ", "Iğdır.", "çağ​", "  Kâr  ", "A B"])
def test_normalization_is_idempotent(profile, given):
    once = normalize(given, profile)
    assert normalize(once, profile) == once


def test_parser_profiles_are_not_text_profiles():
    for p in ("numeric", "choice_label", "bogus"):
        with pytest.raises(ValueError):
            normalize("x", p)


def test_tr_upper():
    assert tr_upper("istanbul") == "İSTANBUL"
    assert tr_upper("ışık") == "IŞIK"
    assert tr_upper("I") == "I" and tr_upper("İ") == "İ"


# ------------------------------------------------------------------ exact_match with accepted_answers (GKN-900)
def test_each_accepted_answer_is_normalized_separately(by_id):
    q = by_id["GKN-900"]
    args = (q["answer"], q["accepted_answers"], q["scoring"]["normalization"])
    for ok in ["karbondioksit", "Karbondioksit.", "KARBONDİOKSİT", "karbon   dioksit", "Karbon Dioksit", "CO2", "co2", " co2. "]:
        assert score_exact_match(ok, *args)["passed"], ok
    for bad in ["CO₂", "karbon", "oksijen", "karbondiyoksit", "karbondıoksıt", "azot", ""]:
        assert not score_exact_match(bad, *args)["passed"], bad


def test_co2_equivalence_is_never_assumed(by_id):
    q = by_id["GKN-900"]
    without = score_exact_match("CO2", q["answer"], [], q["scoring"]["normalization"])
    assert not without["passed"], "'CO2' must only match because the author listed it explicitly"
    only_spaced = score_exact_match("CO2", q["answer"], ["karbon dioksit"], q["scoring"]["normalization"])
    assert not only_spaced["passed"]


def test_exact_match_for_fac_fixture_is_strict_about_suffixes(by_id):
    q = by_id["FAC-900"]
    args = (q["answer"], q["accepted_answers"], q["scoring"]["normalization"])
    assert score_exact_match("SELANİK.", *args)["passed"]
    assert score_exact_match("thessaloniki", *args)["passed"]
    for bad in ["Selanik'te", "Selanık", "Selanik şehri", "İstanbul"]:
        assert not score_exact_match(bad, *args)["passed"], bad


def test_empty_response_never_matches():
    assert not score_exact_match("", "x", [], "tr_text")["passed"]
    assert not score_exact_match("...", "x", ["."], "tr_text")["passed"]
