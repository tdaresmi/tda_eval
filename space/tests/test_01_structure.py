"""Test group 1: structural checks of all five files (JSON / JSONL / Markdown) and cross-file consistency."""
import json
import re

import pytest

from conftest import DATASET_DIR, FIXTURES, RUN_SCHEMA

GUIDE = DATASET_DIR / "QUESTION_GUIDE.md"
KNOWN_FILES = {
    "question.schema.json", "categories.json", "run_report.schema.json", "sample_questions.jsonl",
    "questions.jsonl", "reference_solutions.json", "validators.py", "normalize.py", "checks.py",
    "code_runner.py", "stats.py", "README.md", "QUESTION_GUIDE.md",
}


@pytest.mark.parametrize("path", [DATASET_DIR / "question.schema.json", DATASET_DIR / "categories.json",
                                  RUN_SCHEMA, FIXTURES / "reference_solutions.json"])
def test_json_files_parse(path):
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)


def test_jsonl_every_line_is_an_object_and_ids_unique(samples):
    assert len(samples) == 10
    assert len({q["id"] for q in samples}) == 10
    raw = (FIXTURES / "sample_questions.jsonl").read_text(encoding="utf-8")
    assert raw.endswith("\n") and "\n\n" not in raw


def test_markdown_structure():
    text = GUIDE.read_text(encoding="utf-8")
    lines = text.split("\n")
    assert text.count("```") % 2 == 0, "unbalanced code fences"
    in_fence, levels = False, []
    for ln in lines:
        if ln.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            m = re.match(r"^(#{1,6}) \S", ln)
            if m:
                levels.append(len(m.group(1)))
    assert levels.count(1) == 1 and levels[0] == 1, "exactly one H1, and it comes first"
    for a, b in zip(levels, levels[1:]):
        assert b <= a + 1, "heading level skipped"
    # tables: every row of a table has the same number of columns
    block = []
    for ln in lines + [""]:
        if ln.startswith("|"):
            block.append(ln)
        else:
            if block:
                widths = {len(re.findall(r"(?<!\\)\|", r)) for r in block}
                assert len(widths) == 1, f"inconsistent table columns: {block[0][:60]}"
                assert re.match(r"^\|[\s:|-]+\|$", block[1]), "table lacks a header separator"
            block = []
    assert re.search(r"^## .*(Lisans|lisans)", text, re.M), "guide must document the license fields"


def test_markdown_mentions_only_known_files():
    text = GUIDE.read_text(encoding="utf-8")
    mentioned = set(re.findall(r"`([A-Za-z0-9_./-]+\.(?:json|jsonl|py|md))`", text))
    names = {m.split("/")[-1] for m in mentioned}
    assert names <= KNOWN_FILES, f"guide mentions unknown files: {names - KNOWN_FILES}"


def test_guide_covers_every_schema_term(qschema, cats):
    text = GUIDE.read_text(encoding="utf-8")
    terms = set(qschema["properties"]["question_type"]["enum"])
    terms |= set(qschema["properties"]["scoring"]["properties"]["method"]["enum"])
    terms |= set(qschema["properties"]["scoring"]["properties"]["normalization"]["enum"])
    terms |= set(qschema["properties"]["constraints"]["items"]["properties"]["type"]["enum"])
    terms |= {c["prefix"] for c in cats["categories"]}
    terms |= {"reviewed", "independent", "references", "accessed_date", "source.license", "license",
              "fixture", "900", "tolerance", "rubric_id", "sandbox", "accepted_answers"}
    missing = sorted(t for t in terms if t not in text)
    assert not missing, f"QUESTION_GUIDE.md does not document: {missing}"


def test_guide_type_table_matches_categories(cats):
    """The question_type | scoring.method table in the guide must equal categories.json -> question_type_rules."""
    text = GUIDE.read_text(encoding="utf-8")
    rows = {}
    for ln in text.split("\n"):
        m = re.match(r"^\| `(\w+)` \| `(\w+)` \|", ln)
        if m and m.group(1) in cats["question_type_rules"]:
            rows[m.group(1)] = m.group(2)
    expected = {k: v["scoring_method"] for k, v in cats["question_type_rules"].items()}
    assert rows == expected


def test_fixture_files_are_all_marked_as_fixtures(samples):
    assert all(q["split"] == "fixture" and q["id"].endswith("-900") for q in samples)
    assert all(q["verification"]["reviewed"] is False for q in samples)
