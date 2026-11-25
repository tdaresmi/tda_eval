"""Schema + cross-field validators for questions, categories.json and run reports.

Why this module exists: `jsonschema` silently ignores `format` unless a FormatChecker is passed, and its built-in
checker has NO 'date-time' or 'uri' check unless optional packages are installed (and its 'date' check is looser than
YYYY-MM-DD on newer Pythons). FORMAT_CHECKER below implements exactly the formats our schemas use, and
`make_validator` is the only way validators should be built so that format checking can never be skipped by accident.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Set
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

from .normalize import normalize

# ------------------------------------------------------------------------------------------ format checking
FORMAT_CHECKER = FormatChecker(formats=())  # start empty: only the checks defined here are active

_DATE_RE = re.compile(r"^([0-9]{4})-([0-9]{2})-([0-9]{2})$")
_DATETIME_RE = re.compile(
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]{1,9})?(Z|[+-][0-9]{2}:[0-9]{2})$")


@FORMAT_CHECKER.checks("date", raises=ValueError)
def _check_date(value) -> bool:
    if not isinstance(value, str):
        return True  # type errors are the schema's business
    m = _DATE_RE.match(value)
    if not m:
        raise ValueError("date must be YYYY-MM-DD")
    date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return True


@FORMAT_CHECKER.checks("date-time", raises=ValueError)
def _check_datetime(value) -> bool:
    if not isinstance(value, str):
        return True
    m = _DATETIME_RE.match(value)
    if not m:
        raise ValueError("date-time must be RFC 3339")
    y, mo, d, h, mi, s = (int(m.group(i)) for i in range(1, 7))
    datetime(y, mo, d, h, mi, s)  # validates ranges (leap seconds are not accepted)
    tz = m.group(8)
    if tz != "Z":
        if int(tz[1:3]) > 23 or int(tz[4:6]) > 59:
            raise ValueError("bad UTC offset")
    return True


@FORMAT_CHECKER.checks("uri", raises=ValueError)
def _check_uri(value) -> bool:
    if not isinstance(value, str):
        return True
    if re.search(r"\s", value):
        raise ValueError("whitespace in URI")
    parts = urlparse(value)
    if parts.scheme not in ("http", "https") or not parts.netloc or "@" in parts.netloc:
        raise ValueError("only http(s) URIs with a host and no credentials are accepted")
    return True


def schema_format_names(schema) -> Set[str]:
    """All `format` keywords used anywhere in a schema (used to prove none is left unchecked)."""
    found: Set[str] = set()

    def walk(node):
        if isinstance(node, dict):
            fmt = node.get("format")
            if isinstance(fmt, str):
                found.add(fmt)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return found


def make_validator(schema: dict) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    unchecked = schema_format_names(schema) - set(FORMAT_CHECKER.checkers)
    if unchecked:
        raise RuntimeError(f"schema uses format(s) with no active checker: {sorted(unchecked)}")
    return Draft202012Validator(schema, format_checker=FORMAT_CHECKER)


def _schema_errors(validator: Draft202012Validator, instance) -> List[str]:
    out = []
    for e in sorted(validator.iter_errors(instance), key=lambda e: list(map(str, e.path))):
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        out.append(f"{path}: {e.message[:200]}")
    return out


def load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: str) -> List[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise ValueError(f"{path}:{n}: invalid JSON: {e}") from e
    return rows


# ------------------------------------------------------------------------------------------ question validation
def _is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except (ValueError, TypeError):
        return False


def validate_question(q: dict, validator: Draft202012Validator, mode: str = "dataset",
                      cats: Optional[dict] = None) -> List[str]:
    """mode='dataset': a real questions.jsonl row (split=pilot, id 001-899, never a fixture).
    mode='fixture': a test example (split=fixture, id 900-999, reviewed must stay false)."""
    if mode not in ("dataset", "fixture"):
        raise ValueError("mode must be 'dataset' or 'fixture'")
    errors = _schema_errors(validator, q)
    if errors:
        return errors  # cross-field checks assume a schema-valid object
    num = int(q["id"].split("-")[1])
    if mode == "dataset":
        if q["split"] != "pilot" or num >= 900:
            errors.append("fixture/test examples (split=fixture, ids 900-999) must never enter the real dataset")
    else:
        if q["split"] != "fixture" or num < 900:
            errors.append("fixture examples must use ids 900-999 and split=fixture")
        if q["verification"]["reviewed"] is not False:
            errors.append("fixture examples must keep verification.reviewed=false")

    choices = q.get("choices")
    if choices is not None:
        labels = [c["label"] for c in choices]
        if len(set(labels)) != len(labels):
            errors.append("choices: duplicate labels")
        if q.get("answer") not in labels:
            errors.append("answer is not one of the existing choice labels")
        texts = [c["text"].strip() for c in choices]
        if len(set(texts)) != len(texts):
            errors.append("choices: duplicate option texts")

    if q["question_type"] == "short_answer":
        profile = q["scoring"]["normalization"]
        keys = [q["answer"]] + list(q.get("accepted_answers", []))
        normed = [normalize(k, profile) for k in keys]
        if any(n == "" for n in normed):
            errors.append("an answer is empty after normalization")
        if len(set(normed)) != len(normed):
            errors.append("answer/accepted_answers contain duplicates after normalization")

    if q["question_type"] == "code":
        spec = q["code_spec"]
        for i, t in enumerate(spec["tests"]):
            if not _is_json(t["args_json"]):
                errors.append(f"code_spec.tests[{i}].args_json is not valid JSON")
            else:
                if not isinstance(json.loads(t["args_json"]), list):
                    errors.append(f"code_spec.tests[{i}].args_json must be a JSON array")
            if not _is_json(t["expected_json"]):
                errors.append(f"code_spec.tests[{i}].expected_json is not valid JSON")

    if cats is not None:
        allowed = set(cats["license_policy"]["third_party_allowed_licenses"])
        if q["source"]["type"] != "original":
            if q["source"]["license"] not in allowed:
                errors.append(f"source.license {q['source']['license']!r} is not in the third-party allow-list")
            if q["license"] not in allowed:
                errors.append(f"license {q['license']!r} is not in the allowed license list")
        cat = next((c for c in cats["categories"] if c["id"] == q["category"]), None)
        if cat is None:
            errors.append("unknown category")
        else:
            if q["question_type"] not in cat["question_types"]:
                errors.append(f"question_type {q['question_type']} not allowed for category {q['category']}")
            if cat.get("rubric_id") and q["question_type"] == "open_ended" \
                    and q["scoring"].get("rubric_id") != cat["rubric_id"]:
                errors.append("scoring.rubric_id does not match the category's rubric")
            if q["question_type"] == "open_ended" and q["scoring"]["rubric_id"] not in cats["rubrics"]:
                errors.append("scoring.rubric_id references an unknown rubric")
    return errors


def validate_questions(rows: Iterable[dict], validator: Draft202012Validator, mode: str = "dataset",
                       cats: Optional[dict] = None) -> Dict[str, List[str]]:
    """Validate a whole file; returns {row label: [errors]} for rows with problems (empty dict = all good)."""
    problems: Dict[str, List[str]] = {}
    seen: Set[str] = set()
    for i, q in enumerate(rows, 1):
        label = q.get("id", f"row {i}") if isinstance(q, dict) else f"row {i}"
        errs = validate_question(q, validator, mode, cats) if isinstance(q, dict) else ["row is not an object"]
        if isinstance(q, dict) and q.get("id") in seen:
            errs.append("duplicate id")
        if isinstance(q, dict) and "id" in q:
            seen.add(q["id"])
        if errs:
            problems[label] = errs
    return problems


# ------------------------------------------------------------------------------------------ categories.json
def extract_type_rules(qschema: dict) -> Dict[str, dict]:
    """Re-derive the per-question_type rules from question.schema.json's allOf (so categories.json can be compared)."""
    rules = {}
    for entry in qschema["allOf"]:
        qt = entry.get("if", {}).get("properties", {}).get("question_type", {}).get("const")
        if qt is None:
            continue
        then = entry["then"]
        scoring = then["properties"]["scoring"]
        rules[qt] = {
            "scoring_method": scoring["properties"]["method"]["const"],
            "normalization": scoring["properties"]["normalization"]["enum"],
            "required_fields": then.get("required", []),
            "forbidden_fields": [r["required"][0] for r in then.get("not", {}).get("anyOf", [])],
            "scoring_required": scoring.get("required", []),
            "scoring_forbidden": [r["required"][0] for r in scoring.get("not", {}).get("anyOf", [])],
        }
    return rules


def _reference_required_categories(qschema: dict) -> Set[str]:
    for entry in qschema["allOf"]:
        if "references" in entry.get("then", {}).get("required", []):
            return set(entry["if"]["properties"]["category"]["enum"])
    return set()


def validate_categories(cats: dict, qschema: dict, tolerance: float = 1e-9) -> List[str]:
    errors: List[str] = []
    categories = cats["categories"]
    ids = [c["id"] for c in categories]
    prefixes = [c["prefix"] for c in categories]
    if len(set(ids)) != len(ids):
        errors.append("category ids are not unique")
    if len(set(prefixes)) != len(prefixes):
        errors.append("category prefixes are not unique")
    schema_ids = set(qschema["properties"]["category"]["enum"])
    if set(ids) != schema_ids:
        errors.append(f"category ids differ from question.schema.json enum: {sorted(set(ids) ^ schema_ids)}")
    m = re.match(r"^\^\((.*)\)-", qschema["properties"]["id"]["pattern"])
    schema_prefixes = set(m.group(1).split("|")) if m else set()
    if set(prefixes) != schema_prefixes:
        errors.append("category prefixes differ from the question id pattern in question.schema.json")
    schema_pairs = {}
    for entry in qschema["allOf"]:
        cat = entry.get("if", {}).get("properties", {}).get("category", {}).get("const")
        if cat:
            schema_pairs[cat] = entry["then"]["properties"]["id"]["pattern"]
    for c in categories:
        if schema_pairs.get(c["id"]) != f"^{c['prefix']}-":
            errors.append(f"category {c['id']}: prefix {c['prefix']} does not match the id/category rule in the schema")

    if abs(sum(c["weight"] for c in categories) - 1.0) > tolerance:
        errors.append(f"category weights sum to {sum(c['weight'] for c in categories)}, expected 1")
    if any(c["weight"] <= 0 for c in categories):
        errors.append("weights must be positive")
    if sum(c["pilot_target_count"] for c in categories) != 100:
        errors.append(f"pilot_target_count sums to {sum(c['pilot_target_count'] for c in categories)}, expected 100")

    rubrics = cats["rubrics"]
    for c in categories:
        if c["scoring_mode"] == "rubric":
            if c.get("rubric_id") not in rubrics:
                errors.append(f"category {c['id']} references unknown rubric {c.get('rubric_id')!r}")
            elif c["id"] not in rubrics[c["rubric_id"]].get("applies_to_categories", []):
                errors.append(f"rubric {c['rubric_id']} does not list category {c['id']} in applies_to_categories")
            if c["score_basis"] != "rubric_mean":
                errors.append(f"category {c['id']}: rubric categories must use score_basis=rubric_mean")
        else:
            if c.get("rubric_id") is not None:
                errors.append(f"category {c['id']}: automatic categories must not reference a rubric")
            if c["score_basis"] == "rubric_mean":
                errors.append(f"category {c['id']}: score_basis rubric_mean requires scoring_mode=rubric")
    for rid, r in rubrics.items():
        crit_ids = [k["id"] for k in r["criteria"]]
        if len(set(crit_ids)) != len(crit_ids):
            errors.append(f"rubric {rid}: duplicate criterion ids")
        if not r["scale"]["min"] < r["scale"]["max"]:
            errors.append(f"rubric {rid}: invalid scale")
        for ac in r["applies_to_categories"]:
            if ac not in ids:
                errors.append(f"rubric {rid}: unknown category {ac}")

    derived = extract_type_rules(qschema)
    declared = cats["question_type_rules"]
    if set(derived) != set(declared):
        errors.append("question_type_rules differ from question.schema.json question types")
    for qt, rule in derived.items():
        d = declared.get(qt, {})
        for key, value in rule.items():
            got = d.get(key)
            if sorted(got or []) != sorted(value) if isinstance(value, list) else got != value:
                errors.append(f"question_type_rules[{qt}].{key} = {got!r} but question.schema.json says {value!r}")
    schema_types = set(qschema["properties"]["question_type"]["enum"])
    schema_methods = set(qschema["properties"]["scoring"]["properties"]["method"]["enum"])
    for c in categories:
        for qt in c["question_types"]:
            if qt not in schema_types:
                errors.append(f"category {c['id']}: question type {qt} unknown to the schema")
        if c["scoring_mode"] == "rubric" and c["question_types"] != ["open_ended"]:
            errors.append(f"category {c['id']}: rubric categories must contain only open_ended questions")
        if c["scoring_mode"] == "automatic" and "open_ended" in c["question_types"]:
            errors.append(f"category {c['id']}: automatic categories cannot contain open_ended questions")
    if {r["scoring_method"] for r in declared.values()} != schema_methods:
        errors.append("scoring methods in question_type_rules differ from the schema enum")
    schema_norms = set(qschema["properties"]["scoring"]["properties"]["normalization"]["enum"])
    if set(cats["normalization_profiles"]) != schema_norms:
        errors.append("normalization_profiles keys differ from the schema normalization enum")
    schema_constraints = set(qschema["properties"]["constraints"]["items"]["properties"]["type"]["enum"])
    if set(cats["constraint_semantics"]["types"]) != schema_constraints:
        errors.append("constraint_semantics types differ from the schema constraint type enum")

    ref_cats = _reference_required_categories(qschema)
    if {c["id"] for c in categories if c["references_required"]} != ref_cats:
        errors.append("references_required flags differ from the schema's references rule")

    allowed_ci = set(cats["confidence_interval_policy"]["allowed_statistic_types"])
    for name, metric in cats["metrics"].items():
        ci = metric["confidence_interval"]
        if ci["method"] is not None and metric["statistic_type"] not in allowed_ci and name != "category_scores":
            errors.append(f"metric {name}: a confidence interval is declared for statistic_type "
                          f"{metric['statistic_type']!r}, which is not a binary proportion")
        if ci["method"] is None and not ci.get("reason_tr") and name != "category_scores":
            errors.append(f"metric {name}: missing reason for the unavailable confidence interval")
    cs = cats["metrics"]["category_scores"]["confidence_interval"]
    if "rubric_mean" in cs["applies_to_score_basis"]:
        errors.append("category_scores: Wilson must not apply to rubric_mean")
    bases = {c["score_basis"] for c in categories}
    if not bases <= set(cs["applies_to_score_basis"]) | set(cs["unavailable_for_score_basis"]):
        errors.append("a category score_basis has no declared confidence-interval rule")
    if cats["id_ranges"]["real_dataset"]["max"] >= cats["id_ranges"]["fixture"]["min"]:
        errors.append("real-dataset and fixture id ranges overlap")
    return errors


# ------------------------------------------------------------------------------------------ run reports
def _rubric_score(criteria: Dict[str, int], rubric: dict) -> Optional[float]:
    lo, hi = rubric["scale"]["min"], rubric["scale"]["max"]
    if not criteria:
        return None
    return (sum(criteria.values()) / len(criteria) - lo) / (hi - lo)


def _check_rating(kind: str, rating: dict, rubric_versions: Dict[str, str], cats: dict, cat: dict,
                  label: str) -> List[str]:
    errs: List[str] = []
    rid, ver = rating["rubric_id"], rating["rubric_version"]
    rubric = cats["rubrics"].get(rid)
    if rubric is None:
        return [f"{label}: {kind} references unknown rubric {rid!r}"]
    if cat.get("rubric_id") != rid:
        errs.append(f"{label}: {kind} rubric {rid!r} is not the rubric of category {cat['id']}")
    if ver != rubric["version"]:
        errs.append(f"{label}: {kind} rubric_version {ver!r} != categories.json version {rubric['version']!r}")
    if rubric_versions.get(rid) != ver:
        errs.append(f"{label}: {kind} rubric_version differs from the run-level {kind} rubric_versions")
    crit = rating["criteria_scores"]
    expected_ids = {k["id"] for k in rubric["criteria"]}
    if set(crit) != expected_ids:
        errs.append(f"{label}: {kind} criteria {sorted(crit)} != rubric criteria {sorted(expected_ids)}")
    for k, v in crit.items():
        if not rubric["scale"]["min"] <= v <= rubric["scale"]["max"]:
            errs.append(f"{label}: {kind} criterion {k}={v} outside the scale "
                        f"{rubric['scale']['min']}..{rubric['scale']['max']}")
    expected = _rubric_score(crit, rubric)
    if expected is not None and set(crit) == expected_ids and abs(expected - rating["score"]) > 1e-6:
        errs.append(f"{label}: {kind} score {rating['score']} != normalized criteria mean {expected:.6f}")
    if not 0.0 <= rating["score"] <= 1.0:
        errs.append(f"{label}: {kind} score outside 0..1")
    return errs


def validate_run_report(run: dict, validator: Draft202012Validator, cats: dict) -> List[str]:
    errors = _schema_errors(validator, run)
    if errors:
        return errors
    cat_by_id = {c["id"]: c for c in cats["categories"]}
    prefix_to_cat = {c["prefix"]: c["id"] for c in cats["categories"]}
    selected = run["selection"]["categories"]
    for c in selected:
        if c not in cat_by_id:
            errors.append(f"selection: unknown category {c}")
    results = run["results"]
    if len(results) != run["selection"]["question_count"]:
        errors.append(f"results has {len(results)} items but selection.question_count is "
                      f"{run['selection']['question_count']} (failed results must be kept, not dropped)")
    seen = set()
    judge, human = run["judge"], run["human_evaluation"]
    for r in results:
        label = r["question_id"]
        key = (r["question_id"], r["sample_index"])
        if key in seen:
            errors.append(f"{label}: duplicate (question_id, sample_index)")
        seen.add(key)
        cat = cat_by_id.get(r["category"])
        if cat is None:
            errors.append(f"{label}: unknown category {r['category']}")
            continue
        if prefix_to_cat.get(r["question_id"].split("-")[0]) != r["category"]:
            errors.append(f"{label}: question id prefix does not belong to category {r['category']}")
        if r["category"] not in selected:
            errors.append(f"{label}: category {r['category']} was not selected for this run")
        rubric_cat = cat["scoring_mode"] == "rubric"

        if r["status"] == "ok":
            if r["error"] is not None or not isinstance(r["response"], str):
                errors.append(f"{label}: status ok requires response text and error=null")
            else:
                if r["response_chars"] != len(r["response"]):
                    errors.append(f"{label}: response_chars {r['response_chars']} != {len(r['response'])}")
                if r["response_words"] != len(r["response"].split()):
                    errors.append(f"{label}: response_words {r['response_words']} != {len(r['response'].split())}")
            if rubric_cat and r["automatic"] is not None:
                errors.append(f"{label}: rubric items must have automatic=null")
            if not rubric_cat and r["automatic"] is None:
                errors.append(f"{label}: automatic category result is missing its automatic score")
            if r["automatic"] is not None:
                a = r["automatic"]
                if a["status"] == "scored":
                    if a["score"] is None or a["passed"] is None:
                        errors.append(f"{label}: scored result needs score and passed")
                    elif a["score"] != (1.0 if a["passed"] else 0.0):
                        errors.append(f"{label}: score {a['score']} inconsistent with passed={a['passed']}")
                    if a["method"] == "unit_tests":
                        tt, tp = a.get("tests_total"), a.get("tests_passed")
                        if tt is None or tp is None or tp > tt or a["passed"] != (tt > 0 and tp == tt):
                            errors.append(f"{label}: unit_tests result needs consistent tests_total/tests_passed "
                                          f"(passed only when every test passed)")
                    if a["method"] == "constraint_check":
                        ct, cp = a.get("constraints_total"), a.get("constraints_passed")
                        if ct is None or cp is None or cp > ct or a["passed"] != (cp == ct):
                            errors.append(f"{label}: constraint_check result needs consistent "
                                          f"constraints_total/constraints_passed (strict pass = all satisfied)")
                if a["status"] == "scoring_error" and (a["score"] is not None or a["passed"] is not None):
                    errors.append(f"{label}: scoring_error must not carry a score")
        else:
            if r["error"] is None or r["response"] is not None or r["automatic"] is not None \
                    or r["judge"] is not None or r["human"] is not None:
                errors.append(f"{label}: failed result must keep the error and have no response/scores")

        # judge (optional)
        if judge is None:
            if r["judge"] is not None or r["judge_error"] is not None:
                errors.append(f"{label}: judge was not used but judge/judge_error is set")
        else:
            if r["status"] == "ok" and rubric_cat:
                if (r["judge"] is None) == (r["judge_error"] is None):
                    errors.append(f"{label}: exactly one of judge / judge_error must be set when a judge is used")
            elif r["judge"] is not None or r["judge_error"] is not None:
                errors.append(f"{label}: judge fields must be null for non-rubric or failed results")
            if r["judge"] is not None:
                if r["judge"]["rubric_id"] not in judge["rubric_ids"]:
                    errors.append(f"{label}: judge rubric not declared at run level")
                errors += _check_rating("judge", r["judge"], judge["rubric_versions"], cats, cat, label)
        # human (optional, single rating)
        if human is None:
            if r["human"] is not None:
                errors.append(f"{label}: no human evaluation declared but human rating present")
        elif r["human"] is not None:
            if not (r["status"] == "ok" and rubric_cat):
                errors.append(f"{label}: human rating only applies to successful rubric results")
            if r["human"]["rubric_id"] not in human["rubric_ids"]:
                errors.append(f"{label}: human rubric not declared at run level")
            errors += _check_rating("human", r["human"], human["rubric_versions"], cats, cat, label)

    if judge is not None:
        for rid, ver in judge["rubric_versions"].items():
            if rid not in judge["rubric_ids"]:
                errors.append(f"judge.rubric_versions has {rid} which is not in rubric_ids")
            if rid in cats["rubrics"] and cats["rubrics"][rid]["version"] != ver:
                errors.append(f"judge rubric {rid} version {ver} != categories.json")
    if human is not None:
        for rid, ver in human["rubric_versions"].items():
            if rid in cats["rubrics"] and cats["rubrics"][rid]["version"] != ver:
                errors.append(f"human rubric {rid} version {ver} != categories.json")
    return errors
