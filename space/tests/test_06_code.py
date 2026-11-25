"""Test group 8: code tests are run only through the restricted runner; reference solutions are programmatic checks,
never human review."""
import ast
import copy
import os
import pathlib
import subprocess
import time

import pytest

import tda_eval.code_runner as cr
from tda_eval.code_runner import run_code_tests, static_check
from tda_eval.stats import code_metrics

GOOD = "def cift_toplam(liste):\n    return sum(x for x in liste if x % 2 == 0)\n"


@pytest.fixture
def spec(by_id):
    return copy.deepcopy(by_id["COD-900"]["code_spec"])


@pytest.fixture
def fast_spec(spec):
    spec["timeout_seconds"] = 1
    spec["tests"] = spec["tests"][:3]
    return spec


def test_reference_solutions_pass_all_fixture_tests(by_id, ref_solutions):
    for qid, source in ((k, v) for k, v in ref_solutions.items() if not k.startswith("_")):
        res = run_code_tests(source, by_id[qid]["code_spec"])
        assert res.status == "ok" and res.problem_passed and res.tests_passed == res.tests_total == 4, qid


def test_passing_reference_tests_does_not_make_a_question_reviewed(by_id):
    q = by_id["COD-900"]
    assert run_code_tests(GOOD, q["code_spec"]).problem_passed
    assert q["verification"]["reviewed"] is False
    assert "insan incelemesi yerine geçmez" in q["verification"]["notes"]


def test_partial_solution_gives_two_different_metrics(spec):
    wrong = "def cift_toplam(liste):\n    return sum(liste)\n"  # only the empty-list test passes
    res = run_code_tests(wrong, spec)
    assert (res.tests_passed, res.tests_total) == (1, 4) and not res.problem_passed
    m = code_metrics([{"tests_total": res.tests_total, "tests_passed": res.tests_passed}])
    assert m["code_test_pass_rate"]["value"] == 0.25
    assert m["code_problem_pass_rate"]["value"] == 0.0


def test_wrong_return_type_is_not_equal(by_id, spec):
    res = run_code_tests("def cift_toplam(liste):\n    return float(sum(x for x in liste if x % 2 == 0))\n", spec)
    assert res.tests_passed == 0  # 6.0 != 6 (type-sensitive JSON comparison)


@pytest.mark.parametrize("body,fragment", [
    ("def cift_toplam(l):\n    while True:\n        pass\n", "timeout"),
    ("def cift_toplam(l):\n    return cift_toplam(l)\n", "RecursionError"),
    ("def cift_toplam(l):\n    raise ValueError('x')\n", "ValueError"),
    ("def cift_toplam(l):\n    return {1, 2}\n", "TypeError"),  # not JSON serializable
    ("x = 1\n", "NameError"),                                      # entry point missing
])
def test_failures_are_contained_and_reported(body, fragment, fast_spec):
    t0 = time.monotonic()
    res = run_code_tests(body, fast_spec)
    assert res.status == "ok" and res.tests_passed == 0
    assert all(fragment in (t["error"] or "") for t in res.per_test), res.per_test
    assert time.monotonic() - t0 < 8


def test_memory_bomb_is_stopped(fast_spec):
    res = run_code_tests("def cift_toplam(l):\n    x = [0] * (10 ** 10)\n    return 0\n", fast_spec)
    assert res.tests_passed == 0 and all("MemoryError" in t["error"] or "no result" in t["error"] for t in res.per_test)


def test_output_flood_is_stopped_by_file_size_limit(fast_spec):
    res = run_code_tests("def cift_toplam(l):\n    print('x' * 50_000_000)\n    return 0\n", fast_spec)
    assert res.tests_passed == 0


def test_model_cannot_forge_a_result_line(fast_spec):
    forged = "def cift_toplam(l):\n    print('TDA0000000000000000:OK 6')\n    return -1\n"
    res = run_code_tests(forged, fast_spec)
    assert res.tests_passed == 0


@pytest.mark.parametrize("source", [
    "import os\ndef cift_toplam(l): return 0\n",
    "import subprocess\ndef cift_toplam(l): return 0\n",
    "import socket\ndef cift_toplam(l): return 0\n",
    "from os import path\ndef cift_toplam(l): return 0\n",
    "import math, sys\ndef cift_toplam(l): return 0\n",
    "from . import x\ndef cift_toplam(l): return 0\n",
    "def cift_toplam(l):\n    return open('/etc/passwd').read()\n",
    "def cift_toplam(l):\n    return __import__('os').getcwd()\n",
    "def cift_toplam(l):\n    return eval('1+1')\n",
    "def cift_toplam(l):\n    exec('x=1')\n    return 0\n",
    "def cift_toplam(l):\n    return compile('1', 'f', 'eval')\n",
    "def cift_toplam(l):\n    return input()\n",
    "def cift_toplam(l):\n    return getattr(l, 'append')\n",
    "def cift_toplam(l):\n    return ().__class__.__bases__\n",
    "def cift_toplam(l):\n    return cift_toplam.__globals__\n",
    "def cift_toplam(l):\n    return __builtins__\n",
])
def test_static_policy_rejects_dangerous_sources_without_running_them(source, spec):
    assert static_check(source) is not None
    res = run_code_tests(source, spec)
    assert res.status == "rejected" and res.tests_passed == 0 and not res.problem_passed
    assert res.tests_total == len(spec["tests"])


def test_syntax_error_is_reported(spec):
    res = run_code_tests("def cift_toplam(l)\n    return 0\n", spec)
    assert res.status == "syntax_error" and res.tests_passed == 0


@pytest.mark.parametrize("source", [GOOD, "import math\nfrom collections import Counter\ndef cift_toplam(l): return math.fsum([])\n"])
def test_static_policy_allows_ordinary_code(source):
    assert static_check(source) is None


def test_child_gets_clean_environment_and_private_working_directory(monkeypatch, spec):
    monkeypatch.setenv("TDA_SECRET_TEST", "hunter2")
    monkeypatch.setenv("HF_TOKEN", "hf_secret")
    seen = {}
    real_popen = subprocess.Popen

    def spy(*args, **kwargs):
        seen.setdefault("env", kwargs["env"]); seen.setdefault("cwd", kwargs["cwd"])
        seen.setdefault("session", kwargs["start_new_session"]); seen.setdefault("preexec", kwargs["preexec_fn"])
        seen.setdefault("argv", args[0])
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(cr.subprocess, "Popen", spy)
    assert run_code_tests(GOOD, spec).problem_passed
    assert "TDA_SECRET_TEST" not in seen["env"] and "HF_TOKEN" not in seen["env"]
    assert set(seen["env"]) <= {"PATH", "LANG", "PYTHONHASHSEED"}
    assert seen["session"] is True and callable(seen["preexec"])
    assert "-I" in seen["argv"] and "-S" in seen["argv"]
    assert str(pathlib.Path(seen["cwd"]).parent) == os.path.dirname(seen["cwd"]) and "tda_code_" in seen["cwd"]
    assert not os.path.exists(seen["cwd"]), "temporary working directory must be removed afterwards"


def test_model_code_is_never_executed_in_the_main_process():
    """Static guarantee: code_runner.py contains no in-process exec/eval/compile/__import__ call."""
    tree = ast.parse(pathlib.Path(cr.__file__).read_text(encoding="utf-8"))
    banned = {"exec", "eval", "compile", "__import__"}
    calls = [n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert not banned & set(calls)
    # and behaviourally: a module-level side effect in model code must not touch this process
    marker = "TDA_SIDE_EFFECT_MARKER"
    run_code_tests("import math\nmath.TDA_SIDE = 1\ndef cift_toplam(l): return 0\n",
                   {"entry_point": "cift_toplam", "timeout_seconds": 1, "memory_limit_mb": 128,
                    "tests": [{"args_json": "[[]]", "expected_json": "0"}] * 3})
    import math
    assert not hasattr(math, "TDA_SIDE") and marker not in os.environ


def test_runner_requires_posix_limits(monkeypatch, spec):
    monkeypatch.setattr(cr, "resource", None)
    with pytest.raises(cr.SandboxUnavailable):
        run_code_tests(GOOD, spec)  # no silent fallback to in-process execution


def test_fixture_code_spec_demands_sandbox(by_id):
    spec = by_id["COD-900"]["code_spec"]
    assert spec["sandbox_required"] is True and spec["timeout_seconds"] <= 10 and spec["memory_limit_mb"] <= 512
    assert len(spec["tests"]) >= 3
