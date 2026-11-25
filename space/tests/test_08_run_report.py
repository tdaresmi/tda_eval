"""Test groups 10, 11, 12 for run reports: schema + Python consistency validator; valid runs accepted, broken ones
rejected (each from a valid baseline so the rejection is attributable to the single mutation)."""
import copy

import pytest

from tda_eval.validators import validate_run_report

H64 = "a" * 64
STORY = "Yağmur yağıyordu. Kimse gelmeyecek miydi?"
CODE = "def cift_toplam(l):\n    return sum(l)\n"
CRITERIA = {"instruction_compliance": 4, "coherence": 3, "language_quality": 4, "creativity": 2, "style": 3}  # 16/5/4 = 0.8
HUMAN_CRITERIA = {k: 3 for k in CRITERIA}                                                                   # 0.75


def _ok(qid, cat, response, **kw):
    r = {"question_id": qid, "sample_index": 0, "category": cat, "status": "ok", "response": response, "error": None,
         "latency_ms": 420, "finish_reason": "stop", "response_chars": len(response),
         "response_words": len(response.split()), "automatic": None, "judge": None, "judge_error": None, "human": None}
    r.update(kw)
    return r


def _auto(method, passed, **extra):
    a = {"method": method, "status": "scored", "score": 1.0 if passed else 0.0, "passed": passed,
         "parse_status": "not_applicable", "parsed_answer": None, "normalization": None, "flags": [], "details": None}
    a.update(extra)
    return a


def build_run(judge=True, human=True):
    results = [
        _ok("MAT-001", "mathematics", "740", automatic=_auto("numeric_match", True, parse_status="parsed",
                                                              parsed_answer="740", normalization="numeric")),
        _ok("COD-001", "coding", CODE, automatic=_auto("unit_tests", False, tests_total=4, tests_passed=1)),
        _ok("IFL-001", "instruction_following", "- a\n- b\nc",
            automatic=_auto("constraint_check", False, constraints_total=3, constraints_passed=2)),
        _ok("CRW-001", "creative_writing", STORY,
            judge={"rubric_id": "creative_writing_v1", "rubric_version": "1.0.0", "score": 0.8,
                   "criteria_scores": dict(CRITERIA), "rationale": "akıcı"} if judge else None,
            human={"rubric_id": "creative_writing_v1", "rubric_version": "1.0.0", "score": 0.75,
                   "criteria_scores": dict(HUMAN_CRITERIA), "rater_id": "rater-01",
                   "rated_at": "2026-11-24T09:00:00Z"} if human else None),
        {"question_id": "GKN-001", "sample_index": 0, "category": "general_knowledge", "status": "error",
         "response": None, "error": {"type": "timeout", "message": "no reply within 60 s"}, "latency_ms": 60000,
         "finish_reason": None, "response_chars": None, "response_words": None, "automatic": None, "judge": None,
         "judge_error": None, "human": None},
    ]
    return {
        "schema_version": "1.0.0", "run_id": "run-20261124-0001", "created_at": "2026-11-24T08:00:00Z",
        "tda_eval_version": "0.1.0.dev0",
        "dataset": {"id": "TDA/TDA-Eval", "version": "0.1.0", "revision": None, "split": "pilot"},
        "model": {"provider": "hf_inference_providers", "model_id": "org/model-7b", "model_version": "unreported",
                  "model_revision": None, "endpoint_host": "router.huggingface.co"},
        "generation": {
            "n_samples": 1, "prompt_template_id": "tda-chat-v1", "system_prompt_sha256": None,
            "requested": {"temperature": 0.0, "top_p": None, "max_tokens": 512, "seed": 42},
            "reported": {"status": "unreported", "served_model_id": None, "model_version": None, "temperature": None,
                         "top_p": None, "max_tokens": None, "seed": None, "system_fingerprint": None}},
        "selection": {"categories": ["mathematics", "coding", "instruction_following", "creative_writing",
                                     "general_knowledge"], "question_count": 5},
        "judge": {"provider": "openai_compatible", "model_id": "judge-model", "model_version": "2026-01",
                  "temperature": 0.0, "rubric_ids": ["creative_writing_v1"],
                  "rubric_versions": {"creative_writing_v1": "1.0.0"}, "judge_prompt_sha256": H64} if judge else None,
        "human_evaluation": {"raters_per_item": 1, "rubric_ids": ["creative_writing_v1"],
                             "rubric_versions": {"creative_writing_v1": "1.0.0"},
                             "guidelines_version": "g1"} if human else None,
        "results": results,
    }


@pytest.fixture
def check(rvalidator, cats):
    return lambda run: validate_run_report(run, rvalidator, cats)


# ------------------------------------------------------------------------------- valid runs are accepted (group 11)
@pytest.mark.parametrize("judge,human", [(True, True), (True, False), (False, True), (False, False)])
def test_valid_runs_are_accepted_with_optional_judge_and_human(check, judge, human):
    assert check(build_run(judge, human)) == []


def test_failed_results_are_kept_and_valid(check):
    run = build_run()
    assert run["results"][-1]["status"] == "error" and check(run) == []


def test_provider_reported_parameters_are_separate_from_requested(check):
    run = build_run()
    run["generation"]["reported"] = {"status": "reported", "served_model_id": "org/model-7b-q4",
                                     "model_version": "2026-10-01", "temperature": 0.0, "top_p": 1.0,
                                     "max_tokens": 512, "seed": None, "system_fingerprint": "fp_123"}
    run["model"]["model_version"] = "2026-10-01"
    run["generation"]["requested"]["top_p"] = None  # we did not send top_p, provider still reports 1.0
    assert check(run) == []


def test_judge_failure_is_recorded_not_dropped(check):
    run = build_run(human=False)
    run["results"][3]["judge"] = None
    run["results"][3]["judge_error"] = "judge API timeout"
    assert check(run) == []


def test_optional_unknowns_may_be_null_and_model_version_unreported(check):
    run = build_run()
    run["model"]["endpoint_host"] = None
    run["dataset"]["revision"] = None
    run["generation"]["system_prompt_sha256"] = None
    assert run["model"]["model_version"] == "unreported" and check(run) == []


def test_other_timezone_offsets_are_not_accepted_for_created_at_but_z_with_fraction_is(check):
    run = build_run(); run["created_at"] = "2026-11-24T08:00:00.123Z"
    assert check(run) == []


# ------------------------------------------------------------------------------- broken runs are rejected (group 12)
def _r(run, i=0):
    return run["results"][i]


def _dup(run):
    run["results"].append(copy.deepcopy(run["results"][0])); run["selection"]["question_count"] = 6


MUT = {
    # --- regression: accepted by the previous schema revision ---
    "regression: created_at 'yesterday'": lambda r: r.update(created_at="yesterday"),
    "regression: result category 'foo'": lambda r: _r(r).update(category="foo"),
    "regression: error together with response": lambda r: _r(r, 4).update(response="x"),
    "regression: same question twice": _dup,
    # --- identity / counts / categories ---
    "duplicate (question_id, sample_index)": _dup,
    "count above question_count": lambda r: r["selection"].update(question_count=4),
    "count below question_count (failed result dropped)": lambda r: r["selection"].update(question_count=6),
    "failed result silently removed": lambda r: (r["results"].pop(), None),
    "result category not selected": lambda r: r["selection"].update(categories=["coding", "instruction_following", "creative_writing", "general_knowledge"]),
    "selection has unknown category": lambda r: r["selection"]["categories"].append("astrology"),
    "selection has duplicate category": lambda r: r["selection"]["categories"].append("coding"),
    "question id prefix does not match category": lambda r: _r(r).update(question_id="COD-002"),
    "sample_index 1": lambda r: _r(r).update(sample_index=1),
    "n_samples 2": lambda r: r["generation"].update(n_samples=2),
    "empty results": lambda r: r.update(results=[]),
    "extra property on result": lambda r: _r(r).update(extra=1),
    "extra property on run": lambda r: r.update(extra=1),
    # --- timestamps / formats ---
    "created_at without Z (offset)": lambda r: r.update(created_at="2026-11-24T11:00:00+03:00"),
    "created_at impossible date": lambda r: r.update(created_at="2026-13-45T08:00:00Z"),
    "created_at with space": lambda r: r.update(created_at="2026-11-24 08:00:00Z"),
    "created_at hour 25": lambda r: r.update(created_at="2026-11-24T25:00:00Z"),
    "created_at Arabic-Indic digits": lambda r: r.update(created_at="٢٠٢٦-١١-٢٤T٠٨:٠٠:٠٠Z"),
    "human rated_at invalid": lambda r: _r(r, 3)["human"].update(rated_at="yesterday"),
    "dataset.version not semver": lambda r: r["dataset"].update(version="v0.1"),
    "run_id too short": lambda r: r.update(run_id="r1"),
    # --- model / generation ---
    "model_version missing": lambda r: r["model"].pop("model_version"),
    "model_version empty": lambda r: r["model"].update(model_version=""),
    "endpoint_host is a URL": lambda r: r["model"].update(endpoint_host="https://router.huggingface.co/v1"),
    "endpoint_host with credentials": lambda r: r["model"].update(endpoint_host="user:token@host"),
    "temperature missing": lambda r: r["generation"]["requested"].pop("temperature"),
    "temperature 3": lambda r: r["generation"]["requested"].update(temperature=3),
    "generation lacks requested block": lambda r: r["generation"].pop("requested"),
    "generation lacks reported block": lambda r: r["generation"].pop("reported"),
    "reported unreported but carries values": lambda r: r["generation"]["reported"].update(temperature=0.0),
    "reported unreported but carries model": lambda r: r["generation"]["reported"].update(served_model_id="x"),
    "reported status invalid": lambda r: r["generation"]["reported"].update(status="guessed"),
    "system_prompt_sha256 malformed": lambda r: r["generation"].update(system_prompt_sha256="abc"),
    "old flat generation layout": lambda r: r["generation"].update(temperature=0.0),
    # --- errors / consistency of failed results ---
    "ok result with an error object": lambda r: _r(r).update(error={"type": "timeout", "message": "x"}),
    "ok result without response": lambda r: _r(r).update(response=None),
    "failed result without error object": lambda r: _r(r, 4).update(error=None),
    "failed result still has automatic score": lambda r: _r(r, 4).update(automatic=_auto("exact_match", True)),
    "failed result still has response_chars": lambda r: _r(r, 4).update(response_chars=3),
    "failed result has finish_reason": lambda r: _r(r, 4).update(finish_reason="stop"),
    "error type unknown": lambda r: _r(r, 4)["error"].update(type="exploded"),
    "error message huge": lambda r: _r(r, 4)["error"].update(message="x" * 600),
    "response_chars wrong": lambda r: _r(r).update(response_chars=99),
    "response_words wrong": lambda r: _r(r).update(response_words=99),
    # --- automatic scores ---
    "automatic missing for non-rubric result": lambda r: _r(r).update(automatic=None),
    "automatic present for rubric result": lambda r: _r(r, 3).update(automatic=_auto("rubric", True)),
    "score above 1": lambda r: _r(r)["automatic"].update(score=1.5),
    "score negative": lambda r: _r(r)["automatic"].update(score=-0.1),
    "score inconsistent with passed": lambda r: _r(r)["automatic"].update(score=0.5),
    "scored result with null score": lambda r: _r(r)["automatic"].update(score=None),
    "scoring_error with a score": lambda r: _r(r)["automatic"].update(status="scoring_error"),
    "unit_tests without counters": lambda r: (_r(r, 1)["automatic"].pop("tests_total"), None),
    "unit_tests passed although a test failed": lambda r: _r(r, 1)["automatic"].update(passed=True, score=1.0),
    "constraint strict pass although one failed": lambda r: _r(r, 2)["automatic"].update(passed=True, score=1.0),
    "constraint counters impossible": lambda r: _r(r, 2)["automatic"].update(constraints_passed=9),
    "parse_status invalid": lambda r: _r(r)["automatic"].update(parse_status="guessed"),
    # --- judge ---
    "judge score above 1": lambda r: _r(r, 3)["judge"].update(score=1.2),
    "judge score != criteria mean": lambda r: _r(r, 3)["judge"].update(score=0.5),
    "judge criterion missing": lambda r: _r(r, 3)["judge"]["criteria_scores"].pop("style"),
    "judge criterion unknown": lambda r: _r(r, 3)["judge"]["criteria_scores"].update(humor=2),
    "judge criterion above scale": lambda r: _r(r, 3)["judge"]["criteria_scores"].update(style=5),
    "judge criterion below scale": lambda r: _r(r, 3)["judge"]["criteria_scores"].update(style=-1),
    "judge criterion not an integer": lambda r: _r(r, 3)["judge"]["criteria_scores"].update(style=3.5),
    # scale violation isolated: the declared score still equals the criteria mean, so ONLY the scale rule can fire
    "judge criterion above scale, score consistent": lambda r: _r(r, 3)["judge"].update(
        criteria_scores={"instruction_compliance": 5, "coherence": 3, "language_quality": 4, "creativity": 2, "style": 2}, score=0.8),
    "judge criterion below scale, score consistent": lambda r: _r(r, 3)["judge"].update(
        criteria_scores={"instruction_compliance": 4, "coherence": 4, "language_quality": 4, "creativity": 4, "style": -1}, score=0.75),
    "human criterion above scale, score consistent": lambda r: _r(r, 3)["human"].update(
        criteria_scores={"instruction_compliance": 5, "coherence": 3, "language_quality": 3, "creativity": 2, "style": 2}, score=0.75),
    "human criterion below scale, score consistent": lambda r: _r(r, 3)["human"].update(
        criteria_scores={"instruction_compliance": 4, "coherence": 4, "language_quality": 4, "creativity": 3, "style": -1}, score=0.7),
    "judge rubric version differs from categories.json": lambda r: (_r(r, 3)["judge"].update(rubric_version="2.0.0"), None),
    "judge rubric unknown": lambda r: _r(r, 3)["judge"].update(rubric_id="nope_v1"),
    "judge rubric not declared at run level": lambda r: r["judge"].update(rubric_ids=["other_v1"]),
    "run judge rubric_versions disagree with categories": lambda r: r["judge"]["rubric_versions"].update(creative_writing_v1="9.9.9"),
    "judge prompt hash malformed": lambda r: r["judge"].update(judge_prompt_sha256="zzz"),
    "judge not used but result has judge": lambda r: (r.update(judge=None), None),
    "judge not used but judge_error set": lambda r: (r.update(judge=None), _r(r, 3).update(judge=None, judge_error="x"))[-1],
    "judge used, rubric result has neither judge nor error": lambda r: _r(r, 3).update(judge=None),
    "judge and judge_error both set": lambda r: _r(r, 3).update(judge_error="x"),
    "judge on a non-rubric result": lambda r: _r(r).update(judge=copy.deepcopy(_r(r, 3)["judge"])),
    "judge on a failed result": lambda r: _r(r, 4).update(judge=copy.deepcopy(_r(r, 3)["judge"])),
    # --- human ---
    "human present but no human_evaluation declared": lambda r: r.update(human_evaluation=None),
    "two raters per item (unsupported in v0.1.0)": lambda r: r["human_evaluation"].update(raters_per_item=2),
    "human rating is a list (multi-rater unsupported)": lambda r: _r(r, 3).update(human=[copy.deepcopy(_r(r, 3)["human"])]),
    "human score above 1": lambda r: _r(r, 3)["human"].update(score=1.01),
    "human score != criteria mean": lambda r: _r(r, 3)["human"].update(score=0.1),
    "human criterion above scale": lambda r: _r(r, 3)["human"]["criteria_scores"].update(style=7),
    "human criterion missing": lambda r: _r(r, 3)["human"]["criteria_scores"].pop("creativity"),
    "human rubric version mismatch": lambda r: _r(r, 3)["human"].update(rubric_version="0.9.0"),
    "human rubric not declared": lambda r: r["human_evaluation"].update(rubric_ids=["other_v1"]),
    "human rater id empty": lambda r: _r(r, 3)["human"].update(rater_id=""),
    "human on a non-rubric result": lambda r: _r(r).update(human=copy.deepcopy(_r(r, 3)["human"])),
    "human_evaluation lacks guidelines version": lambda r: r["human_evaluation"].pop("guidelines_version"),
}


@pytest.mark.parametrize("name", sorted(MUT))
def test_broken_runs_are_rejected(name, check):
    assert check(build_run()) == [], "baseline must be valid, so rejection is due to the mutation"
    run = build_run()
    MUT[name](run)
    assert check(run), f"broken run report was ACCEPTED: {name}"


def test_judge_not_used_requires_null_everywhere(check):
    run = build_run(judge=False)
    assert run["judge"] is None and all(r["judge"] is None and r["judge_error"] is None for r in run["results"])
    run["results"][3]["judge"] = {"rubric_id": "creative_writing_v1", "rubric_version": "1.0.0", "score": 0.8,
                                  "criteria_scores": dict(CRITERIA), "rationale": None}
    assert any("judge was not used" in e for e in check(run))


def test_human_not_used_requires_null_everywhere(check):
    run = build_run(human=False)
    assert run["human_evaluation"] is None and all(r["human"] is None for r in run["results"])
    run["results"][3]["human"] = copy.deepcopy(build_run()["results"][3]["human"])
    assert any("no human evaluation declared" in e for e in check(run))


def test_unreported_reported_block_is_not_a_copy_of_requested(check):
    run = build_run()
    assert run["generation"]["requested"]["temperature"] == 0.0
    assert run["generation"]["reported"]["temperature"] is None


def test_every_error_is_traceable_to_a_message(check):
    run = build_run()
    run["results"][0]["question_id"] = "COD-002"
    errs = check(run)
    assert errs and any("COD-002" in e for e in errs)
