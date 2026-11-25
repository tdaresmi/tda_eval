"""Statistics helpers. Wilson intervals are produced ONLY for genuine binary-proportion metrics."""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

Z_95 = 1.959963984540054


def wilson_interval(k: int, n: int, z: float = Z_95) -> Optional[Tuple[float, float]]:
    """Wilson score interval for k successes in n independent binary trials; None when n == 0."""
    if not (isinstance(k, int) and isinstance(n, int)) or isinstance(k, bool) or isinstance(n, bool):
        raise TypeError("k and n must be integers")
    if n < 0 or k < 0 or k > n:
        raise ValueError("need 0 <= k <= n")
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo, hi = max(0.0, centre - half), min(1.0, centre + half)
    # exact endpoints: with no successes the lower bound is 0, with only successes the upper bound is 1
    # (floating-point error would otherwise leave e.g. 5.5e-17, putting the interval beside the observed rate)
    if k == 0:
        lo = 0.0
    if k == n:
        hi = 1.0
    return lo, hi


def binary_metric(k: int, n: int) -> Dict:
    """Proportion with Wilson interval (appropriate: independent binary outcomes)."""
    ci = wilson_interval(k, n)
    if ci is None:
        return {"value": None, "n": 0, "ci_method": None, "ci": None, "ci_unavailable_reason": "n = 0"}
    return {"value": k / n, "n": n, "ci_method": "wilson_95", "ci": [ci[0], ci[1]], "ci_unavailable_reason": None}


def no_ci_metric(value: Optional[float], n: int, reason: str) -> Dict:
    """Metric for which an interval is NOT statistically appropriate: say so instead of inventing one."""
    return {"value": value, "n": n, "ci_method": None, "ci": None, "ci_unavailable_reason": reason}


def mean_metric(values: List[float], reason: str) -> Dict:
    return no_ci_metric(sum(values) / len(values) if values else None, len(values), reason)


def code_metrics(per_question: List[Dict]) -> Dict:
    """Two separate coding metrics from [{tests_total, tests_passed}, ...] (all scored questions only).

    code_test_pass_rate    : pooled passed tests / total tests; no interval (tests of one solution are dependent).
    code_problem_pass_rate : share of questions whose tests ALL pass; binary -> Wilson interval.
    """
    total = sum(q["tests_total"] for q in per_question)
    passed = sum(q["tests_passed"] for q in per_question)
    full = sum(1 for q in per_question if q["tests_total"] > 0 and q["tests_passed"] == q["tests_total"])
    return {
        "code_test_pass_rate": no_ci_metric(
            passed / total if total else None, total,
            "tests of one solution are not independent trials; Wilson interval would be misleading"),
        "code_problem_pass_rate": binary_metric(full, len(per_question)),
    }
