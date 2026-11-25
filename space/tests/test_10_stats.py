"""Statistics: Wilson intervals only for genuine binary proportions; no misleading intervals elsewhere."""
import pytest

from tda_eval.stats import binary_metric, code_metrics, mean_metric, no_ci_metric, wilson_interval


@pytest.mark.parametrize("k,n,lo,hi", [
    (8, 10, 0.4902, 0.9433), (0, 10, 0.0, 0.2775), (10, 10, 0.7225, 1.0), (50, 100, 0.4038, 0.5962),
    (5, 10, 0.2366, 0.7634), (1, 10, 0.0179, 0.4041),
])
def test_wilson_known_values(k, n, lo, hi):
    got = wilson_interval(k, n)
    assert got[0] == pytest.approx(lo, abs=5e-4) and got[1] == pytest.approx(hi, abs=5e-4)


def test_wilson_properties():
    for n in (1, 2, 7, 10, 33, 100):
        for k in range(n + 1):
            lo, hi = wilson_interval(k, n)
            assert 0.0 <= lo <= k / n <= hi <= 1.0
            mlo, mhi = wilson_interval(n - k, n)
            assert (1 - hi, 1 - lo) == pytest.approx((mlo, mhi))  # symmetry
    assert wilson_interval(3, 10)[1] - wilson_interval(3, 10)[0] > wilson_interval(30, 100)[1] - wilson_interval(30, 100)[0]


def test_pilot_sized_samples_give_very_wide_intervals():
    lo, hi = wilson_interval(7, 10)
    assert hi - lo > 0.4  # n=10 per category: differences of a few questions are not distinguishable


def test_wilson_input_validation():
    assert wilson_interval(0, 0) is None
    for bad in [(-1, 5), (6, 5), (1, -1)]:
        with pytest.raises(ValueError):
            wilson_interval(*bad)
    for bad in [(1.0, 5), (True, 5), (1, 5.0), ("1", 5)]:
        with pytest.raises(TypeError):
            wilson_interval(*bad)


def test_binary_metric_has_interval_and_empty_metric_explains_itself():
    m = binary_metric(8, 10)
    assert m["ci_method"] == "wilson_95" and m["n"] == 10 and m["ci_unavailable_reason"] is None
    assert m["ci"][0] < 0.8 < m["ci"][1]
    empty = binary_metric(0, 0)
    assert empty["value"] is None and empty["ci"] is None and empty["ci_unavailable_reason"] == "n = 0"


def test_non_binary_metrics_never_get_an_interval_and_say_why():
    m = mean_metric([0.8, 0.75, 0.5], "ordinal rubric scores are not binary outcomes")
    assert m["ci"] is None and m["ci_method"] is None and "not binary" in m["ci_unavailable_reason"]
    assert m["value"] == pytest.approx((0.8 + 0.75 + 0.5) / 3) and m["n"] == 3
    assert mean_metric([], "no rubric scores")["value"] is None
    assert no_ci_metric(0.5, 4, "weighted mean")["ci"] is None


def test_two_coding_metrics():
    per_q = [{"tests_total": 4, "tests_passed": 4}, {"tests_total": 4, "tests_passed": 1}, {"tests_total": 3, "tests_passed": 0}]
    m = code_metrics(per_q)
    tests = m["code_test_pass_rate"]; problems = m["code_problem_pass_rate"]
    assert tests["value"] == pytest.approx(5 / 11) and tests["n"] == 11
    assert tests["ci"] is None and tests["ci_method"] is None and "not independent" in tests["ci_unavailable_reason"]
    assert problems["value"] == pytest.approx(1 / 3) and problems["n"] == 3
    assert problems["ci_method"] == "wilson_95" and problems["ci"][0] < 1 / 3 < problems["ci"][1]


def test_partial_credit_does_not_inflate_the_problem_pass_rate():
    per_q = [{"tests_total": 5, "tests_passed": 4}] * 10   # nearly right every time
    m = code_metrics(per_q)
    assert m["code_test_pass_rate"]["value"] == pytest.approx(0.8)
    assert m["code_problem_pass_rate"]["value"] == 0.0


def test_question_without_tests_is_never_a_full_pass():
    assert code_metrics([{"tests_total": 0, "tests_passed": 0}])["code_problem_pass_rate"]["value"] == 0.0
    assert code_metrics([])["code_test_pass_rate"]["value"] is None


def test_interval_policy_in_categories_matches_the_helpers(cats):
    policy = cats["confidence_interval_policy"]
    assert policy["z"] == pytest.approx(1.959963984540054)
    for name, metric in cats["metrics"].items():
        method = metric["confidence_interval"]["method"]
        if metric["statistic_type"] == "binary_proportion":
            assert method == "wilson_95", name
        elif name != "category_scores":
            assert method is None, name
