"""Test groups 2, 3, 4, 11, 12 for questions: schema validation, category/id compatibility, question-type/scoring
compatibility, acceptance of valid examples and rejection of deliberately broken ones."""
import copy

import pytest

from tda_eval.validators import validate_question, validate_questions

BASE_FOR_TYPE = {"multiple_choice": "TLU-900", "short_answer": "GKN-900", "numeric": "MAT-900", "code": "COD-900",
                 "constraint_check": "IFL-900", "open_ended": "CRW-900"}
FIELD_VALUES = {
    "choices": [{"label": "A", "text": "bir"}, {"label": "B", "text": "iki"}],
    "answer": "A", "accepted_answers": ["x"], "constraints": [{"type": "line_count", "value": "3"}],
}


def errs(q, v, mode="fixture", cats=None):
    return validate_question(q, v, mode, cats)


def real_question(by_id):
    """A legitimate REAL-dataset question (derived from the GKN fixture) with full human review + references."""
    q = copy.deepcopy(by_id["GKN-900"])
    q["id"], q["split"] = "GKN-001", "pilot"
    q["references"] = [{"name": "Örnek Ansiklopedi", "url": "https://example.org/fotosentez",
                        "edition": "2. baskı", "accessed_date": "2026-11-20"}]
    q["verification"] = {"reviewed": True, "reviewer_type": "human", "reviewer": "reviewer-01", "independent": True,
                         "checked": {"answer_key": True, "question_content": True}, "method": "source_checked",
                         "reviewed_date": "2026-11-21", "notes": "kaynakla doğrulandı"}
    return q


# ----------------------------------------------------------------------------- test group 2/11 (valid accepted)
def test_all_fixtures_valid_in_fixture_mode(samples, qvalidator, cats):
    assert validate_questions(samples, qvalidator, "fixture", cats) == {}


def test_one_fixture_per_category_and_ids_match_categories(samples, cats):
    assert sorted(q["category"] for q in samples) == sorted(c["id"] for c in cats["categories"])
    prefix = {c["id"]: c["prefix"] for c in cats["categories"]}
    for q in samples:
        assert q["id"] == f"{prefix[q['category']]}-900"


def test_valid_real_question_is_accepted(by_id, qvalidator, cats):
    assert errs(real_question(by_id), qvalidator, "dataset", cats) == []


def test_valid_third_party_question_is_accepted(by_id, qvalidator, cats):
    q = real_question(by_id)
    q["source"] = {"type": "third_party", "authoring": "human", "name": "Açık Veri Seti", "url": "https://example.org/d",
                   "license": "CC-BY-4.0", "retrieved_date": "2026-11-20"}
    q["license"] = "CC-BY-4.0"
    assert errs(q, qvalidator, "dataset", cats) == []


# ----------------------------------------------------------------------------- fixture/real separation
def test_fixtures_never_enter_the_real_dataset(samples, qvalidator, cats):
    problems = validate_questions(samples, qvalidator, "dataset", cats)
    assert set(problems) == {q["id"] for q in samples}
    assert all("must never enter the real dataset" in e[0] for e in problems.values())


def test_id_range_and_split_are_tied_together(by_id, qvalidator):
    q = copy.deepcopy(by_id["TLU-900"]); q["split"] = "pilot"
    assert errs(q, qvalidator)  # 9xx id with split=pilot
    q = copy.deepcopy(by_id["TLU-900"]); q["id"] = "TLU-001"
    assert errs(q, qvalidator)  # real id with split=fixture
    q["split"] = "pilot"
    assert errs(q, qvalidator, "dataset") == []


def test_fixture_mode_refuses_reviewed_true(by_id, qvalidator):
    q = real_question(by_id); q["id"], q["split"] = "GKN-900", "fixture"
    assert any("reviewed=false" in e for e in errs(q, qvalidator, "fixture"))


def test_factual_fixture_cannot_be_promoted_without_references(by_id, qvalidator, cats):
    q = copy.deepcopy(by_id["FAC-900"]); q["id"], q["split"] = "FAC-001", "pilot"
    assert any("references" in e for e in errs(q, qvalidator, "dataset", cats))
    q["references"] = [{"name": "Resmî Gazete", "url": "https://example.org/rg", "accessed_date": "2026-11-20"}]
    assert errs(q, qvalidator, "dataset", cats) == []


@pytest.mark.parametrize("cat,fixture_id", [("general_knowledge", "GKN-900"), ("turkish_grammar", "GRM-900"),
                                           ("factual_accuracy", "FAC-900")])
def test_references_required_categories(by_id, qvalidator, cat, fixture_id):
    q = copy.deepcopy(by_id[fixture_id]); q["id"], q["split"] = fixture_id.replace("900", "002"), "pilot"
    assert any("references" in e for e in errs(q, qvalidator, "dataset"))


# ----------------------------------------------------------------------------- test group 12 (rejected)
def _m(fn):
    return fn


MUTATIONS = {
    # --- regression: all of these were ACCEPTED by the previous schema revision ---
    "regression: duplicate choice labels": ("TLU-900", lambda q: q["choices"].__setitem__(1, {"label": "A", "text": "x"})),
    "regression: answer E with 4 choices": ("TLU-900", lambda q: q.update(answer="E")),
    "regression: MC + tolerance": ("TLU-900", lambda q: q["scoring"].update(tolerance=1)),
    "regression: MC + rubric_id": ("TLU-900", lambda q: q["scoring"].update(rubric_id="x")),
    "regression: MC + constraints": ("TLU-900", lambda q: q.update(constraints=[{"type": "line_count", "value": "3"}])),
    "regression: numeric without tolerance": ("MAT-900", lambda q: q["scoring"].pop("tolerance")),
    "regression: numeric + accepted_answers": ("MAT-900", lambda q: q.update(accepted_answers=["740"])),
    "regression: open_ended + answer": ("CRW-900", lambda q: q.update(answer="x")),
    "regression: line_count 'üç'": ("IFL-900", lambda q: q["constraints"].__setitem__(0, {"type": "line_count", "value": "üç"})),
    "regression: forbidden_char 2 chars": ("IFL-900", lambda q: q["constraints"].__setitem__(2, {"type": "forbidden_char", "value": "ab"})),
    "regression: third_party bad url": ("TLU-900", lambda q: q.update(source={"type": "third_party", "authoring": "human", "name": "x", "url": "not a uri", "license": "MIT", "retrieved_date": "2026-11-20"}, license="MIT")),
    "regression: original + license MIT": ("TLU-900", lambda q: q.update(license="MIT")),
    "regression: code question with answer": ("COD-900", lambda q: q.update(answer="6")),
    # --- reviewed / verification (base REAL = a valid, fully human-reviewed real-dataset question) ---
    "reviewed true without reviewer": ("REAL", lambda q: q["verification"].pop("reviewer")),
    "reviewed true without reviewed_date": ("REAL", lambda q: q["verification"].pop("reviewed_date")),
    "reviewed true without method": ("REAL", lambda q: q["verification"].pop("method")),
    "reviewed true without checked scope": ("REAL", lambda q: q["verification"].pop("checked")),
    "reviewed true, not independent": ("REAL", lambda q: q["verification"].update(independent=False)),
    "reviewed true, reviewer is AI": ("REAL", lambda q: q["verification"].update(reviewer_type="ai")),
    "reviewed true, only answer key checked": ("REAL", lambda q: q["verification"]["checked"].pop("question_content")),
    "reviewed true, question content unchecked": ("REAL", lambda q: q["verification"]["checked"].update(question_content=False)),
    "reviewed true, programmatic method": ("REAL", lambda q: q["verification"].update(method="unit_tested")),
    "reviewed false carrying reviewer data": ("REAL", lambda q: q["verification"].update(reviewed=False)),
    "reviewed_date 2026-13-45 (format)": ("REAL", lambda q: q["verification"].update(reviewed_date="2026-13-45")),
    "reviewed_date 20261121 (format)": ("REAL", lambda q: q["verification"].update(reviewed_date="20261121")),
    "reviewed_date 'dün' (format)": ("REAL", lambda q: q["verification"].update(reviewed_date="dün")),
    # --- third party / license ---
    "third_party without url": ("TLU-900", lambda q: q.update(source={"type": "third_party", "authoring": "human", "name": "x", "license": "MIT", "retrieved_date": "2026-11-20"})),
    "third_party without license": ("TLU-900", lambda q: q.update(source={"type": "third_party", "authoring": "human", "name": "x", "url": "https://example.org", "retrieved_date": "2026-11-20"})),
    "third_party without name": ("TLU-900", lambda q: q.update(source={"type": "third_party", "authoring": "human", "url": "https://example.org", "license": "MIT", "retrieved_date": "2026-11-20"})),
    "third_party url with credentials": ("TLU-900", lambda q: q.update(source={"type": "third_party", "authoring": "human", "name": "x", "url": "https://user:pw@example.org/x", "license": "MIT", "retrieved_date": "2026-11-20"})),
    "third_party url ftp": ("TLU-900", lambda q: q.update(source={"type": "third_party", "authoring": "human", "name": "x", "url": "ftp://example.org/x", "license": "MIT", "retrieved_date": "2026-11-20"})),
    "original carrying source.license": ("TLU-900", lambda q: q["source"].update(license="MIT")),
    "retrieved_date 2026-02-30": ("TLU-900", lambda q: q.update(source={"type": "third_party", "authoring": "human", "name": "x", "url": "https://example.org", "license": "MIT", "retrieved_date": "2026-02-30"})),
    # --- ids / choices / types ---
    "id prefix != category": ("TLU-900", lambda q: q.update(id="MAT-900")),
    "id 000": ("TLU-900", lambda q: q.update(id="TLU-000")),
    "unknown category": ("TLU-900", lambda q: q.update(category="astrology")),
    "choice labels out of order": ("TLU-900", lambda q: q["choices"].reverse()),
    "6 choices": ("TLU-900", lambda q: q["choices"].extend([{"label": "E", "text": "e"}, {"label": "F", "text": "f"}])),
    "1 choice": ("TLU-900", lambda q: q.update(choices=q["choices"][:1])),
    "MC wrong normalization": ("TLU-900", lambda q: q["scoring"].update(normalization="tr_text")),
    "short_answer + choices": ("GKN-900", lambda q: q.update(choices=FIELD_VALUES["choices"])),
    "short_answer numeric normalization": ("GKN-900", lambda q: q["scoring"].update(normalization="numeric")),
    "short_answer missing normalization": ("GKN-900", lambda q: q["scoring"].pop("normalization")),
    "numeric Turkish decimal key": ("MAT-900", lambda q: q.update(answer="1.234,5")),
    "numeric negative tolerance": ("MAT-900", lambda q: q["scoring"].update(tolerance=-1)),
    "numeric + rubric_id": ("MAT-900", lambda q: q["scoring"].update(rubric_id="creative_writing_v1")),
    "code fewer than 3 tests": ("COD-900", lambda q: q["code_spec"].update(tests=q["code_spec"]["tests"][:2])),
    "code without sandbox_required": ("COD-900", lambda q: q["code_spec"].pop("sandbox_required")),
    "code sandbox_required false": ("COD-900", lambda q: q["code_spec"].update(sandbox_required=False)),
    "code without memory limit": ("COD-900", lambda q: q["code_spec"].pop("memory_limit_mb")),
    "code timeout 60s": ("COD-900", lambda q: q["code_spec"].update(timeout_seconds=60)),
    "code entry_point not identifier": ("COD-900", lambda q: q["code_spec"].update(entry_point="a-b")),
    "code invalid args_json": ("COD-900", lambda q: q["code_spec"]["tests"][0].update(args_json="[1,2")),
    "code args_json not an array": ("COD-900", lambda q: q["code_spec"]["tests"][0].update(args_json="5")),
    "code invalid expected_json": ("COD-900", lambda q: q["code_spec"]["tests"][0].update(expected_json="{bad")),
    "constraint_check without constraints": ("IFL-900", lambda q: q.pop("constraints")),
    "constraint unknown type": ("IFL-900", lambda q: q["constraints"].append({"type": "be_nice", "value": "x"})),
    "constraint line_count 0": ("IFL-900", lambda q: q["constraints"].__setitem__(0, {"type": "line_count", "value": "0"})),
    "constraint all_lowercase value yes": ("IFL-900", lambda q: q["constraints"].append({"type": "all_lowercase", "value": "yes"})),
    "open_ended without rubric_id": ("CRW-900", lambda q: q["scoring"].pop("rubric_id")),
    "open_ended wrong method": ("CRW-900", lambda q: q["scoring"].update(method="exact_match")),
    "open_ended + tolerance": ("CRW-900", lambda q: q["scoring"].update(tolerance=0)),
    "unknown extra field": ("TLU-900", lambda q: q.update(foo=1)),
    "prompt too short": ("TLU-900", lambda q: q.update(prompt="kısa")),
    "added_in not semver": ("TLU-900", lambda q: q.update(added_in="v1")),
    "split unknown": ("TLU-900", lambda q: q.update(split="test")),
    "duplicate accepted_answers": ("GKN-900", lambda q: q.update(accepted_answers=["a", "a"])),
    "references empty list (real)": ("GKN-900", lambda q: q.update(id="GKN-003", split="pilot", references=[])),
    "references missing accessed_date": ("GKN-900", lambda q: q.update(id="GKN-003", split="pilot", references=[{"name": "x"}])),
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_broken_questions_are_rejected(name, by_id, qvalidator, cats):
    base_id, mutate = MUTATIONS[name]
    if base_id == "REAL":
        base, base_mode = real_question(by_id), "dataset"
    else:
        base, base_mode = by_id[base_id], "fixture"
    assert errs(base, qvalidator, base_mode, cats) == [], "baseline must be valid, so rejection is due to the mutation"
    q = copy.deepcopy(base)
    mutate(q)
    mode = "dataset" if q.get("split") == "pilot" else "fixture"
    assert errs(q, qvalidator, mode, cats), f"broken question was ACCEPTED: {name}"


# ----------------------------------------------------------------------------- test group 4: type <-> scoring rules
def test_every_wrong_scoring_method_is_rejected(by_id, qvalidator, cats):
    methods = {r["scoring_method"] for r in cats["question_type_rules"].values()}
    for qtype, bid in BASE_FOR_TYPE.items():
        right = cats["question_type_rules"][qtype]["scoring_method"]
        for m in methods - {right}:
            q = copy.deepcopy(by_id[bid]); q["scoring"]["method"] = m
            assert errs(q, qvalidator), f"{qtype} accepted scoring.method={m}"


def test_every_required_field_is_enforced(by_id, qvalidator, cats):
    for qtype, bid in BASE_FOR_TYPE.items():
        rule = cats["question_type_rules"][qtype]
        for f in rule["required_fields"]:
            q = copy.deepcopy(by_id[bid]); q.pop(f)
            assert errs(q, qvalidator), f"{qtype}: missing {f} accepted"
        for f in rule["scoring_required"]:
            q = copy.deepcopy(by_id[bid]); q["scoring"].pop(f)
            assert errs(q, qvalidator), f"{qtype}: missing scoring.{f} accepted"


def test_every_forbidden_field_is_rejected(by_id, qvalidator, cats):
    for qtype, bid in BASE_FOR_TYPE.items():
        rule = cats["question_type_rules"][qtype]
        for f in rule["forbidden_fields"]:
            q = copy.deepcopy(by_id[bid])
            q[f] = copy.deepcopy(by_id["COD-900"]["code_spec"]) if f == "code_spec" else FIELD_VALUES[f]
            assert errs(q, qvalidator), f"{qtype}: forbidden field {f} accepted"
        for f in rule["scoring_forbidden"]:
            q = copy.deepcopy(by_id[bid]); q["scoring"][f] = 1 if f == "tolerance" else "x"
            assert errs(q, qvalidator), f"{qtype}: forbidden scoring.{f} accepted"


def test_every_wrong_normalization_is_rejected(by_id, qvalidator, cats):
    all_norms = set(cats["normalization_profiles"])
    for qtype, bid in BASE_FOR_TYPE.items():
        for n in all_norms - set(cats["question_type_rules"][qtype]["normalization"]):
            q = copy.deepcopy(by_id[bid]); q["scoring"]["normalization"] = n
            assert errs(q, qvalidator), f"{qtype} accepted normalization={n}"


@pytest.mark.parametrize("n_choices,bad_answer", [(2, "C"), (3, "D"), (4, "E")])
def test_answer_must_be_an_existing_choice_label(by_id, qvalidator, n_choices, bad_answer):
    q = copy.deepcopy(by_id["TLU-900"])
    q["choices"] = [{"label": "ABCDE"[i], "text": f"seçenek {i}"} for i in range(n_choices)]
    q["answer"] = "A"
    assert errs(q, qvalidator) == []
    q["answer"] = bad_answer
    assert errs(q, qvalidator)


def test_question_type_must_belong_to_category(by_id, qvalidator, cats):
    q = copy.deepcopy(by_id["MAT-900"])  # numeric in mathematics is fine
    assert errs(q, qvalidator, "fixture", cats) == []
    q = copy.deepcopy(by_id["TLU-900"])  # multiple_choice item filed under coding (id/category rules both break)
    q["category"], q["id"] = "coding", "COD-900"
    assert errs(q, qvalidator, "fixture", cats)


def test_rubric_must_match_category_rubric(by_id, qvalidator, cats):
    q = copy.deepcopy(by_id["CRW-900"]); q["scoring"]["rubric_id"] = "nonexistent_v9"
    assert any("rubric" in e for e in errs(q, qvalidator, "fixture", cats))


def test_licence_allow_list(by_id, qvalidator, cats):
    q = real_question(by_id)
    q["source"] = {"type": "third_party", "authoring": "human", "name": "x", "url": "https://example.org/x",
                   "license": "Proprietary-EULA", "retrieved_date": "2026-11-20"}
    q["license"] = "Proprietary-EULA"
    assert any("allow-list" in e or "allowed" in e for e in errs(q, qvalidator, "dataset", cats))


def test_normalized_duplicate_answers_are_caught(by_id, qvalidator):
    q = copy.deepcopy(by_id["GKN-900"]); q["accepted_answers"] = ["KARBONDİOKSİT."]
    assert any("duplicates after normalization" in e for e in errs(q, qvalidator))


def test_duplicate_ids_across_rows(samples, qvalidator):
    rows = samples + [copy.deepcopy(samples[0])]
    assert "duplicate id" in validate_questions(rows, qvalidator, "fixture")["TLU-900"]


# ----------------------------------------------------------------------------- the JSON Schema itself must enforce its rules
# validate_question() adds Python rules on top of the schema; these tests make sure the SCHEMA alone is not
# silently relying on that second layer (a mutation test showed the id/split rule was masked that way).
PYTHON_ONLY = {"code invalid args_json", "code args_json not an array", "code invalid expected_json"}


@pytest.mark.parametrize("name", sorted(set(MUTATIONS) - PYTHON_ONLY))
def test_json_schema_alone_rejects_broken_questions(name, by_id, qvalidator):
    base_id, mutate = MUTATIONS[name]
    base = real_question(by_id) if base_id == "REAL" else by_id[base_id]
    assert qvalidator.is_valid(base)
    q = copy.deepcopy(base)
    mutate(q)
    assert not qvalidator.is_valid(q), f"JSON Schema alone accepted: {name}"


def test_schema_alone_ties_id_range_to_split(by_id, qvalidator):
    fx = copy.deepcopy(by_id["TLU-900"])
    assert qvalidator.is_valid(fx)
    fx["split"] = "pilot"
    assert not qvalidator.is_valid(fx), "id 900-999 with split=pilot must be rejected by the schema"
    real = copy.deepcopy(by_id["TLU-900"]); real["id"] = "TLU-001"
    assert not qvalidator.is_valid(real), "id 001-899 with split=fixture must be rejected by the schema"
    real["split"] = "pilot"
    assert qvalidator.is_valid(real)
