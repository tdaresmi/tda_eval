"""JSON Schema `format` keywords must actually be enforced (jsonschema ignores most formats by default)."""
import copy

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import FormatError

from tda_eval.validators import FORMAT_CHECKER, make_validator, schema_format_names

GOOD = {
    "date": ["2026-11-24", "2024-02-29", "1999-12-31"],
    "date-time": ["2026-11-24T08:00:00Z", "2026-11-24T08:00:00.5Z", "2026-11-24T11:00:00+03:00",
                  "2026-11-24T08:00:00.123456Z", "2026-11-24T23:59:59-12:00"],
    "uri": ["https://example.org", "http://example.org/a/b?c=1#d", "https://tr.wikipedia.org/wiki/Selanik",
            "https://example.org:8443/x"],
}
BAD = {
    "date": ["2026-13-45", "2026-02-30", "2025-02-29", "20261124", "2026-1-1", "", "2026-11-24T00:00:00", "dün",
             "٢٠٢٦-١١-٢٤", "２０２６-１１-２４", "2026/11/24", " 2026-11-24"],
    "date-time": ["yesterday", "2026-11-24", "2026-11-24 08:00:00Z", "2026-11-24T25:00:00Z", "2026-11-24T08:61:00Z",
                  "2026-02-30T08:00:00Z", "2026-11-24T08:00:00", "2026-11-24T08:00:00+25:00", "2026-11-24T08:00:60Z",
                  "٢٠٢٦-١١-٢٤T٠٨:٠٠:٠٠Z", "2026-11-24T08:00Z", ""],
    "uri": ["not a uri", "ftp://example.org/x", "https://user:pw@example.org/x", "https:///path", "//example.org",
            "https://exa mple.org", "javascript:alert(1)", "", "example.org", "https://"],
}


@pytest.mark.parametrize("fmt", sorted(GOOD))
def test_good_values_pass(fmt):
    for v in GOOD[fmt]:
        FORMAT_CHECKER.check(v, fmt)


@pytest.mark.parametrize("fmt", sorted(BAD))
def test_bad_values_fail(fmt):
    for v in BAD[fmt]:
        with pytest.raises(FormatError):
            FORMAT_CHECKER.check(v, fmt)


def test_every_format_used_in_our_schemas_has_an_active_checker(qschema, rschema):
    used = schema_format_names(qschema) | schema_format_names(rschema)
    assert used == {"date", "date-time", "uri"}  # if a schema starts using a new format this test forces a decision
    assert used <= set(FORMAT_CHECKER.checkers)


def test_make_validator_refuses_a_schema_with_an_unchecked_format():
    with pytest.raises(RuntimeError, match="no active checker"):
        make_validator({"type": "string", "format": "hostname"})


def test_formats_are_ignored_without_a_checker_and_enforced_with_ours():
    schema = {"type": "object", "properties": {"d": {"type": "string", "format": "date-time"},
                                               "u": {"type": "string", "format": "uri"},
                                               "t": {"type": "string", "format": "date"}}}
    bad = {"d": "yesterday", "u": "not a uri", "t": "2026-13-45"}
    assert Draft202012Validator(schema).is_valid(bad), "jsonschema ignores format when no checker is passed"
    assert not make_validator(schema).is_valid(bad)
    assert make_validator(schema).is_valid({"d": "2026-11-24T08:00:00Z", "u": "https://example.org", "t": "2026-11-24"})


def test_real_question_schema_rejects_bad_formats_only_because_of_the_checker(by_id, qschema, qvalidator):
    q = copy.deepcopy(by_id["TLU-900"])
    q["source"] = {"type": "third_party", "authoring": "human", "name": "x", "url": "not a uri", "license": "MIT",
                   "retrieved_date": "2026-02-30"}
    assert Draft202012Validator(qschema).is_valid(q), "without a format checker the broken item slips through"
    assert not qvalidator.is_valid(q)
    messages = " ".join(e.message for e in qvalidator.iter_errors(q))
    assert "not a 'uri'" in messages and "not a 'date'" in messages


def test_real_run_schema_rejects_bad_formats_only_because_of_the_checker(rschema, rvalidator):
    from test_08_run_report import build_run
    run = build_run()
    run["results"][3]["human"]["rated_at"] = "2026-13-45T08:00:00Z"   # pattern-valid, format-invalid
    assert Draft202012Validator(rschema).is_valid(run)
    assert not rvalidator.is_valid(run)


def test_our_checker_is_independent_of_optional_packages():
    # the default FormatChecker may or may not know date-time/uri depending on installed extras; ours always does
    assert {"date", "date-time", "uri"} <= set(FORMAT_CHECKER.checkers)
    assert set(FORMAT_CHECKER.checkers) == {"date", "date-time", "uri"}
    assert isinstance(FormatChecker().checkers, dict)
