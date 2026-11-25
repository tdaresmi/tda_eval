"""Test groups 3 and 4 for categories.json: validator accepts the real file and rejects broken variants."""
import copy

import pytest

from tda_eval.validators import extract_type_rules, validate_categories


def test_real_categories_file_is_valid(cats, qschema):
    assert validate_categories(cats, qschema) == []


def test_pilot_targets_sum_to_100_and_weights_to_1(cats):
    assert sum(c["pilot_target_count"] for c in cats["categories"]) == 100
    assert abs(sum(c["weight"] for c in cats["categories"]) - 1.0) < 1e-9


def test_category_ids_and_prefixes_are_unique_and_match_question_ids(cats, samples):
    ids = [c["id"] for c in cats["categories"]]
    assert len(ids) == len(set(ids)) == 10
    prefix = {c["id"]: c["prefix"] for c in cats["categories"]}
    assert len(set(prefix.values())) == 10
    for q in samples:
        assert q["id"].startswith(prefix[q["category"]] + "-")


def test_types_and_methods_agree_with_schema(cats, qschema):
    derived = extract_type_rules(qschema)
    assert derived == {k: {kk: vv for kk, vv in v.items()} for k, v in derived.items()}
    for qt, rule in cats["question_type_rules"].items():
        for key in ("scoring_method", "normalization", "required_fields", "forbidden_fields",
                    "scoring_required", "scoring_forbidden"):
            a, b = rule[key], derived[qt][key]
            assert (sorted(a) == sorted(b)) if isinstance(a, list) else a == b, (qt, key)


def _mut(fn):
    return fn


BROKEN = {
    "duplicate category id": lambda c: c["categories"][1].update(id=c["categories"][0]["id"]),
    "duplicate prefix": lambda c: c["categories"][1].update(prefix=c["categories"][0]["prefix"]),
    "unknown category id": lambda c: c["categories"][0].update(id="astrology"),
    "prefix differs from schema rule": lambda c: c["categories"][0].update(prefix="XXX"),
    "weights sum 1.1": lambda c: c["categories"][0].update(weight=0.2),
    "non-positive weight": lambda c: (c["categories"][0].update(weight=0.0), c["categories"][1].update(weight=0.2)),
    "pilot targets sum 99": lambda c: c["categories"][0].update(pilot_target_count=9),
    "pilot targets sum 101": lambda c: c["categories"][0].update(pilot_target_count=11),
    "rubric category without rubric": lambda c: next(x for x in c["categories"] if x["scoring_mode"] == "rubric").update(rubric_id="nope_v1"),
    "rubric lacks applies_to": lambda c: c["rubrics"]["creative_writing_v1"].update(applies_to_categories=[]),
    "automatic category referencing rubric": lambda c: c["categories"][0].update(rubric_id="creative_writing_v1"),
    "rubric_mean on automatic category": lambda c: c["categories"][0].update(score_basis="rubric_mean"),
    "rubric category not rubric_mean": lambda c: next(x for x in c["categories"] if x["scoring_mode"] == "rubric").update(score_basis="accuracy"),
    "rubric criteria duplicate": lambda c: c["rubrics"]["creative_writing_v1"]["criteria"].append(c["rubrics"]["creative_writing_v1"]["criteria"][0]),
    "rubric scale inverted": lambda c: c["rubrics"]["creative_writing_v1"]["scale"].update(min=5),
    "category question type unknown": lambda c: c["categories"][0]["question_types"].append("essay"),
    "automatic category with open_ended": lambda c: c["categories"][0]["question_types"].append("open_ended"),
    "rubric category with numeric": lambda c: next(x for x in c["categories"] if x["scoring_mode"] == "rubric")["question_types"].append("numeric"),
    "type rule: wrong scoring method": lambda c: c["question_type_rules"]["numeric"].update(scoring_method="exact_match"),
    "type rule: wrong normalization": lambda c: c["question_type_rules"]["multiple_choice"].update(normalization=["tr_text"]),
    "type rule: tolerance not required": lambda c: c["question_type_rules"]["numeric"].update(scoring_required=[]),
    "type rule: missing forbidden field": lambda c: c["question_type_rules"]["short_answer"]["forbidden_fields"].remove("choices"),
    "type rule: type removed": lambda c: c["question_type_rules"].pop("code"),
    "normalization profile missing": lambda c: c["normalization_profiles"].pop("numeric"),
    "constraint semantic missing": lambda c: c["constraint_semantics"]["types"].pop("line_prefix"),
    "references flag mismatch": lambda c: next(x for x in c["categories"] if x["id"] == "factual_accuracy").update(references_required=False),
    "wilson declared for ordinal metric": lambda c: c["metrics"]["response_quality"]["confidence_interval"].update(method="wilson_95"),
    "wilson declared for weighted overall": lambda c: c["metrics"]["overall_score_automatic"]["confidence_interval"].update(method="wilson_95"),
    "wilson declared for pooled test rate": lambda c: c["metrics"]["code_test_pass_rate"]["confidence_interval"].update(method="wilson_95"),
    "missing reason for unavailable CI": lambda c: c["metrics"]["response_quality"]["confidence_interval"].pop("reason_tr"),
    "wilson applied to rubric_mean": lambda c: c["metrics"]["category_scores"]["confidence_interval"]["applies_to_score_basis"].append("rubric_mean"),
    "overlapping id ranges": lambda c: c["id_ranges"]["real_dataset"].update(max=950),
}


@pytest.mark.parametrize("name", sorted(BROKEN))
def test_broken_categories_are_rejected(name, cats, qschema):
    assert validate_categories(cats, qschema) == []
    broken = copy.deepcopy(cats)
    BROKEN[name](broken)
    assert validate_categories(broken, qschema), f"broken categories.json was ACCEPTED: {name}"


def test_judge_and_human_are_optional_and_separate_in_metrics(cats):
    m = cats["metrics"]
    assert "KATILMAZ" in m["overall_score_automatic"]["definition_tr"]
    assert m["overall_score_automatic"]["score_source"] == "automatic"
    rules = cats["reporting_rules"]
    assert "isteğe bağlı" in rules["judge_disclosure_tr"] and "isteğe bağlı" in rules["human_disclosure_tr"]
    assert "hiçbir zaman otomatik genel puana karıştırılmaz" in rules["separate_score_sources_tr"]


def test_two_coding_metrics_are_defined_with_correct_interval_policy(cats):
    m = cats["metrics"]
    assert m["code_test_pass_rate"]["confidence_interval"]["method"] is None
    assert m["code_problem_pass_rate"]["confidence_interval"]["method"] == "wilson_95"
    assert next(c for c in cats["categories"] if c["id"] == "coding")["score_basis"] == "code_problem_pass_rate"
