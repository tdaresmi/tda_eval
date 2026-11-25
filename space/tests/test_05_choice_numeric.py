"""Test groups 6 and 7: strict multiple-choice parsing and ambiguous numeric answers."""
from decimal import Decimal

import pytest

from tda_eval.normalize import parse_choice, parse_number, score_choice, score_numeric


# ------------------------------------------------------------------------------- choice (group 6)
def test_choice_examples_from_categories_json(cats):
    for e in cats["normalization_profiles"]["choice_label"]["examples"]:
        r = parse_choice(e["input"], e["valid_labels"])
        assert (r.status, r.label) == (e["status"], e["label"]), e["input"]


@pytest.mark.parametrize("text,label", [
    ("B", "B"), ("b", "B"), ("B.", "B"), ("B)", "B"), ("(B)", "B"), ("(b).", "B"), ("  B  ", "B"), ("B\n", "B"),
    ("Cevap: B", "B"), ("cevap:B", "B"), ("CEVAP : (c)", "C"), ("Yanıt: D.", "D"), ("YANIT: d", "D"),
    ("Doğru cevap: A", "A"), ("Doğru yanıt: b)", "B"), ("Doğru seçenek: C", "C"), ("​B", "B"),
])
def test_accepted_answer_formats(text, label):
    r = parse_choice(text, "ABCD")
    assert (r.status, r.label) == ("parsed", label)


@pytest.mark.parametrize("text", ["A veya B", "A ya da C", "B, C", "A) ve B)", "Cevap: A veya B", "A/B", "B C", "A, B, C"])
def test_several_candidate_labels_are_ambiguous_never_guessed(text):
    r = parse_choice(text, "ABCD")
    assert r.status == "ambiguous" and r.label is None and "ambiguous_answer" in r.flags


@pytest.mark.parametrize("text", [
    "", "   ", "Bence cevap B olabilir", "Cevap B", "Cevabım: B", "B şıkkı", "Seçenek B", "B) Değerini ve itibarını kaybetmek",
    "Değerini ve itibarını kaybetmek", "bilmiyorum", "BB", "AB", "Cevap:", "?",
])
def test_everything_else_is_invalid_format(text):
    r = parse_choice(text, "ABCD")
    assert r.status == "invalid_format" and r.label is None and r.flags == ["invalid_format"]


@pytest.mark.parametrize("text,valid", [("E", "ABCD"), ("D", "ABC"), ("Cevap: e", "ABCD"), ("(C)", "AB")])
def test_label_outside_the_choices_is_invalid_label(text, valid):
    r = parse_choice(text, valid)
    assert r.status == "invalid_label" and r.label is None


def test_choice_scoring_end_to_end(by_id):
    q = by_id["TLU-900"]  # answer B
    valid = "".join(c["label"] for c in q["choices"])
    ok = score_choice("Cevap: b", q["answer"], valid)
    assert ok["passed"] and ok["score"] == 1.0 and ok["parsed_answer"] == "B"
    wrong = score_choice("C", q["answer"], valid)
    assert not wrong["passed"] and wrong["parse_status"] == "parsed" and wrong["parsed_answer"] == "C"
    # contains the right letter but is ambiguous -> NOT credited, flagged
    amb = score_choice("A veya B", q["answer"], valid)
    assert not amb["passed"] and amb["score"] == 0.0 and "ambiguous_answer" in amb["flags"]
    # right letter inside a sentence -> not credited
    sent = score_choice("Bence B doğru", q["answer"], valid)
    assert not sent["passed"] and sent["parse_status"] == "invalid_format"


# ------------------------------------------------------------------------------- numeric (group 7)
def test_numeric_examples_from_categories_json(cats):
    for e in cats["normalization_profiles"]["numeric"]["examples"]:
        r = parse_number(e["input"])
        assert r.status == e["status"], e["input"]
        if e["value"] is None:
            assert r.value is None
        else:
            assert r.value == Decimal(e["value"]), e["input"]


@pytest.mark.parametrize("text", ["1.234", "1,234", "12.345", "999,999", "5.000", "1,000"])
def test_one_separator_plus_three_digits_is_ambiguous(text):
    r = parse_number(text)
    assert r.status == "ambiguous" and r.value is None and "ambiguous_number" in r.flags
    left, right = text.replace(",", ".").split(".")
    assert set(r.candidates) == {Decimal(left + right), Decimal(left + "." + right)}


@pytest.mark.parametrize("text,value", [
    ("740", "740"), ("0", "0"), ("-5", "-5"), ("−5", "-5"), ("3,5", "3.5"), ("3.5", "3.5"), ("2,25", "2.25"),
    ("0.123", "0.123"), ("0,123", "0.123"), ("1234.567", "1234.567"), ("1234,567", "1234.567"), ("1.5", "1.5"),
    ("1.234,5", "1234.5"), ("1,234.5", "1234.5"), ("1.234.567,89", "1234567.89"), ("1,234,567.89", "1234567.89"),
    ("1.234.567", "1234567"), ("1,234,567", "1234567"), ("740 TL", "740"), ("740TL", "740"), ("Cevap: 740.", "740"),
    ("cevap : 12,5 kg", "12.5"), ("740.", "740"), ("  740  ", "740"), ("0,5", "0.5"), ("007", "7"),
])
def test_unambiguous_formats(text, value):
    r = parse_number(text)
    assert r.status == "parsed" and r.value == Decimal(value), (text, r)


@pytest.mark.parametrize("text", ["12 ve 15", "1 234", "3 - 4", "17:30", "2 elma 3 armut", "1e5", "1.234 veya 5"])
def test_several_numbers_are_reported_as_multiple_numbers(text):
    r = parse_number(text)
    assert r.status == "multiple_numbers" and r.value is None


@pytest.mark.parametrize("text", [
    "", "yedi yüz kırk", "yaklaşık yedi yüz", "%25", "$5", "٧٤٠", "７４０", ".5", ",5", "1.2.3", "1,23.4", "1..2", "1,,2",
    "1.234,56,7", "12.34.567", "5,", "740 TL'dir", "bilmiyorum", "∞", "NaN", "0x1F", "740 lira ve kuruş",
])
def test_malformed_answers_are_invalid_format(text):
    r = parse_number(text)
    assert r.status in ("invalid_format", "multiple_numbers") and r.value is None, (text, r)


@pytest.mark.parametrize("text", ["٧٤٠", "７４０"])
def test_only_ascii_digits_are_accepted(text):
    assert parse_number(text).status == "invalid_format"


def test_ambiguous_number_scores_zero_and_is_flagged_even_if_one_reading_matches(by_id):
    # key 1234: "1.234" could be 1234 (thousands) or 1.234 (decimal) -> we do not guess either way
    for key in ("1234", "1.234"):
        r = score_numeric("1.234", key, 0)
        assert not r["passed"] and r["score"] == 0.0
        assert r["parse_status"] == "ambiguous" and "ambiguous_number" in r["flags"]
        assert "1234" in r["details"] and "1.234" in r["details"]


def test_numeric_scoring_with_the_math_fixture(by_id):
    q = by_id["MAT-900"]
    assert q["answer"] == "740"
    tol = q["scoring"]["tolerance"]
    for good in ["740", "740.0", "740,00", "Cevap: 740", "740 TL", "740."]:
        assert score_numeric(good, q["answer"], tol)["passed"], good
    for bad in ["739", "741", "7400", "74", "yedi yüz kırk", "700 ve 40", "740 ya da 741"]:
        assert not score_numeric(bad, q["answer"], tol)["passed"], bad


def test_tolerance_is_absolute_and_inclusive():
    assert score_numeric("3,14", "3.14159", 0.002)["passed"]
    assert score_numeric("3.15", "3.14159", 0.01)["passed"]
    assert not score_numeric("3.2", "3.14159", 0.01)["passed"]
    assert score_numeric("10.5", "10", 0.5)["passed"]
    assert not score_numeric("10.5", "10", 0.4)["passed"]
