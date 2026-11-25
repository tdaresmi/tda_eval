"""Test group 9: instruction-following constraints (IFL-900 and the semantics documented in categories.json)."""
import pytest

from tda_eval.checks import check_constraint, check_constraints, split_lines


@pytest.fixture
def ifl(by_id):
    return by_id["IFL-900"]["constraints"]


def test_ifl_fixture_accepts_a_correct_answer(ifl):
    r = check_constraints("- Ayasofya\n- Galata Kulesi\n- Kapalıçarşı", ifl)
    assert r.strict and r.fraction == 1.0


def test_line_prefix_checks_every_line_not_only_the_first(ifl):
    r = check_constraints("- Ayasofya\nGalata Kulesi\n- Kapalıçarşı", ifl)
    prefix = next(d for d in r.details if d["type"] == "line_prefix")
    assert not prefix["passed"] and "[2]" in prefix["info"]
    assert not r.strict and r.fraction == pytest.approx(2 / 3)
    # first line fine, only the LAST line wrong
    ok, info = check_constraint("- a\n- b\nc", "line_prefix", "- ")
    assert not ok and "[3]" in info
    # all lines wrong except the first, still failing
    assert not check_constraint("- a\nb\nc", "line_prefix", "- ")[0]


def test_ifl_fixture_other_failure_modes(ifl):
    four = check_constraints("- a\n- b\n- c\n- d", ifl)
    assert not four.strict and not next(d for d in four.details if d["type"] == "line_count")["passed"]
    question = check_constraints("- a?\n- b\n- c", ifl)
    assert not question.strict and not next(d for d in question.details if d["type"] == "forbidden_char")["passed"]
    assert not check_constraints("", ifl).strict


@pytest.mark.parametrize("text,lines", [
    ("a\nb\nc", ["a", "b", "c"]), ("\n\na\nb\n\n", ["a", "b"]), ("a\r\nb\r\n", ["a", "b"]), ("a\rb", ["a", "b"]),
    ("a\n\nb", ["a", "", "b"]), ("  \na\n  ", ["a"]), ("", []), ("\n \n", []), ("  a  ", ["  a  "]),
])
def test_line_definition(text, lines):
    assert split_lines(text) == lines


def test_inner_blank_lines_count_as_lines_and_fail_prefix():
    assert check_constraint("- a\n\n- b", "line_count", "3")[0]
    assert not check_constraint("- a\n\n- b", "line_prefix", "- ")[0]


def test_no_lines_means_line_prefix_fails():
    assert not check_constraint("", "line_prefix", "- ")[0]


# ---- substring vs whole-word semantics are never mixed ---------------------------------------------------------
@pytest.mark.parametrize("text,substring_pass,word_pass", [
    # (forbidden value is 'veri'; *_pass = the constraint is SATISFIED, i.e. no violation)
    ("verileri inceledik", False, True),    # suffix: substring violates, whole-word does not
    ("veritabanı kuruldu", False, True),
    ("Bu bir veri.", False, False),          # whole lowercase word: both violate
    ("Veri, önemlidir", True, False),        # substring is case-sensitive ('Veri' != 'veri'); word is not
    ("VERİ geldi", True, False),             # Turkish-aware word match: VERİ -> veri
    ("VERI geldi", True, True),              # VERI -> 'verı' (dotless): a different letter, no violation
    ("Bilgi geldi", True, True),
    ("ver i", True, True),
])
def test_forbidden_substring_vs_forbidden_word(text, substring_pass, word_pass):
    assert check_constraint(text, "forbidden_substring", "veri")[0] is substring_pass, text
    assert check_constraint(text, "forbidden_word", "veri")[0] is word_pass, text


def test_required_substring_is_case_sensitive_required_word_is_turkish_case_insensitive():
    assert not check_constraint("istanbul güzel", "required_substring", "İstanbul")[0]
    assert check_constraint("istanbul güzel", "required_word", "İstanbul")[0]
    assert check_constraint("İSTANBUL güzel", "required_word", "İstanbul")[0]
    assert check_constraint("ISPARTA gülü", "required_word", "Isparta")[0]       # I -> ı on both sides
    assert not check_constraint("İSPARTA gülü", "required_word", "Isparta")[0]   # ı vs i stay different
    assert check_constraint("İstanbul'da yaşıyorum", "required_word", "İstanbul")[0]  # apostrophe is a boundary
    assert not check_constraint("İstanbullu", "required_word", "İstanbul")[0]
    assert check_constraint("İstanbullu", "required_substring", "İstanbul")[0]
    assert check_constraint("ev-ödevi", "required_word", "ödevi")[0]


def test_required_word_with_regex_metacharacters_is_literal():
    assert check_constraint("a.b", "required_word", "a.b")[0]
    assert not check_constraint("axb", "required_word", "a.b")[0]


@pytest.mark.parametrize("text,lower,upper", [
    ("ışık", True, False), ("Işık", False, False), ("ISIK", False, True), ("IŞIK", False, True), ("işık", True, False),
    ("İSTANBUL", False, True), ("istanbul", True, False), ("Istanbul", False, False), ("123 !?", True, True),
    ("ÇAĞRI", False, True), ("çağrı", True, False),
])
def test_all_lowercase_and_all_uppercase_use_turkish_rules(text, lower, upper):
    assert check_constraint(text, "all_lowercase", "true")[0] is lower
    assert check_constraint(text, "all_uppercase", "true")[0] is upper


def test_case_constraints_only_ask_whether_any_cased_letter_is_wrong():
    """all_lowercase/all_uppercase mean "no uppercase / no lowercase letter". For THESE predicates Turkish and
    naive case mapping always agree (checked exhaustively below), so no Turkish-specific risk exists here; the
    Turkish rules matter for tr_lower/tr_upper themselves, which the normalization tests cover."""
    from tda_eval.normalize import tr_lower, tr_upper
    letters = "abcçdefgğhıijklmnoöprsştuüvyzABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ0123 .?"
    for c in letters:
        assert check_constraint(c, "all_lowercase", "true")[0] == (c == c.lower()) == (c == tr_lower(c))
        assert check_constraint(c, "all_uppercase", "true")[0] == (c == c.upper()) == (c == tr_upper(c))
    # the mappings themselves do differ from Python's defaults
    assert tr_lower("I") == "ı" and "I".lower() == "i"
    assert tr_upper("i") == "İ" and "i".upper() == "I"
    assert not check_constraint("istanbul", "all_uppercase", "true")[0]
    assert check_constraint("İSTANBUL", "all_uppercase", "true")[0]


@pytest.mark.parametrize("ctype,value,text,expected", [
    ("word_count_min", "3", "bir iki üç", True), ("word_count_min", "3", "bir iki", False),
    ("word_count_max", "3", "bir iki üç", True), ("word_count_max", "3", "bir iki üç dört", False),
    ("word_count_max", "2", "ev-ödevi  yaptım", True),
    ("starts_with", "Merhaba", "  Merhaba dünya", True), ("starts_with", "Merhaba", "merhaba", False),
    ("ends_with", "dünya.", "Merhaba dünya.\n\n", True), ("ends_with", "dünya.", "dünya. Merhaba", False),
    ("forbidden_char", "?", "Nasılsın?", False), ("forbidden_char", "?", "Nasılsın", True),
    ("forbidden_char", "ğ", "dağ", False), ("forbidden_char", "ğ", "dag", True),
    ("required_substring", "ışı", "ışık", True), ("required_substring", "isi", "ışık", False),
    ("line_count", "2", "a\nb", True), ("line_count", "2", "a\nb\nc", False),
])
def test_remaining_constraint_types(ctype, value, text, expected):
    assert check_constraint(text, ctype, value)[0] is expected


def test_unknown_constraint_type_raises():
    with pytest.raises(ValueError):
        check_constraint("x", "be_nice", "1")


def test_strict_and_loose_scores_are_both_available():
    cs = [{"type": "line_count", "value": "2"}, {"type": "forbidden_char", "value": "?"},
          {"type": "word_count_max", "value": "3"}]
    r = check_constraints("bir iki üç dört?\nb", cs)
    assert r.strict is False and r.fraction == pytest.approx(1 / 3)


def test_semantics_in_categories_json_cover_every_type(cats, qschema):
    types = set(qschema["properties"]["constraints"]["items"]["properties"]["type"]["enum"])
    assert set(cats["constraint_semantics"]["types"]) == types
    for t in types:  # every documented type is actually implemented
        value = "true" if t.startswith("all_") else ("1" if "count" in t else "x")
        check_constraint("x", t, value)
