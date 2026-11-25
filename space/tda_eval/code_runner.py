"""Restricted execution of model-written Python for `unit_tests` scoring.

POLICY (categories.json -> code_execution_policy): model code is NEVER executed in the main application process.
Every test runs in its own subprocess with a clean environment, an empty temporary working directory, Python in
isolated mode, wall-clock/CPU/memory/file-size limits, a killed process group on timeout, and a statically checked
source (import allow-list, no open/exec/eval/compile/__import__/input, no dangerous dunder access).

IMPORTANT LIMITATION: this is best-effort resource restriction, NOT a security sandbox. Network access and file
reads are not blocked at OS level. Before running untrusted model output on a public Space, run this module inside a
container/gVisor/nsjail-class isolation.
"""
from __future__ import annotations

import ast
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:  # POSIX only
    import resource
except ImportError:  # pragma: no cover - non-POSIX platforms are unsupported
    resource = None  # type: ignore

ALLOWED_IMPORTS = frozenset({
    "math", "re", "itertools", "functools", "collections", "string", "statistics", "heapq", "bisect",
    "fractions", "decimal", "operator", "typing", "dataclasses", "copy", "numbers", "cmath", "enum",
})
BLOCKED_CALLS = frozenset({"open", "exec", "eval", "compile", "__import__", "input", "breakpoint",
                           "globals", "locals", "vars", "getattr", "setattr", "delattr", "memoryview"})
BLOCKED_ATTRIBUTES = frozenset({"__class__", "__subclasses__", "__globals__", "__builtins__", "__bases__",
                                "__mro__", "__code__", "__closure__", "__dict__", "__import__", "__loader__",
                                "__spec__", "gi_frame", "f_globals", "f_builtins"})


class SandboxUnavailable(RuntimeError):
    """Raised when restricted execution is impossible on this platform; callers must NOT fall back to in-process."""


@dataclass
class CodeRunResult:
    status: str                      # ok | rejected | syntax_error
    tests_total: int
    tests_passed: int
    per_test: List[Dict] = field(default_factory=list)
    reason: Optional[str] = None

    @property
    def problem_passed(self) -> bool:
        return self.tests_total > 0 and self.tests_passed == self.tests_total


def static_check(source: str) -> Optional[str]:
    """Return a rejection reason, or None when the source passes the static policy."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"syntax_error: {e.msg} (line {e.lineno})"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    return f"import not allowed: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                return f"import not allowed: {node.module}"
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            if name in BLOCKED_CALLS:
                return f"call not allowed: {name}"
        elif isinstance(node, ast.Attribute):
            if node.attr in BLOCKED_ATTRIBUTES:
                return f"attribute not allowed: {node.attr}"
        elif isinstance(node, ast.Name):
            if node.id in BLOCKED_ATTRIBUTES or node.id in ("__builtins__",):
                return f"name not allowed: {node.id}"
    return None


def _make_limiter(cpu_seconds: int, memory_mb: int):
    def limit():  # runs in the child between fork and exec
        mb = 1024 * 1024
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb * mb, memory_mb * mb))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1 * mb, 1 * mb))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return limit


def _footer(entry_point: str, token: str) -> str:
    return (
        "\n\nimport json as _j, sys as _s\n"
        "_tests = _j.load(open('tests.json', encoding='utf-8'))\n"
        "_t = _tests[int(_s.argv[1])]\n"
        f"_fn = globals().get({entry_point!r})\n"
        "try:\n"
        "    if not callable(_fn):\n"
        "        raise NameError('entry point not defined')\n"
        "    _out = _j.dumps(_fn(*_j.loads(_t['args_json'])), sort_keys=True, ensure_ascii=False)\n"
        f"    _s.stdout.write('\\n{token}OK ' + _out + '\\n')\n"
        "except BaseException as _e:\n"
        f"    _s.stdout.write('\\n{token}ERR ' + type(_e).__name__ + '\\n')\n"
    )


def _canonical(json_text: str) -> str:
    return json.dumps(json.loads(json_text), sort_keys=True, ensure_ascii=False)


def run_code_tests(source: str, code_spec: Dict, python: Optional[str] = None) -> CodeRunResult:
    """Run `source` against code_spec['tests'], one restricted subprocess per test."""
    if resource is None:
        raise SandboxUnavailable("POSIX resource limits are unavailable on this platform")
    tests = code_spec["tests"]
    total = len(tests)
    reason = static_check(source)
    if reason is not None:
        status = "syntax_error" if reason.startswith("syntax_error") else "rejected"
        return CodeRunResult(status, total, 0, [{"passed": False, "error": reason} for _ in tests], reason)

    timeout = float(code_spec.get("timeout_seconds", 2))
    memory_mb = int(code_spec.get("memory_limit_mb", 256))
    python = python or sys.executable
    per_test: List[Dict] = []
    with tempfile.TemporaryDirectory(prefix="tda_code_") as work:
        token = "TDA" + secrets.token_hex(8) + ":"
        with open(os.path.join(work, "solution.py"), "w", encoding="utf-8") as f:
            f.write(source + _footer(code_spec["entry_point"], token))
        with open(os.path.join(work, "tests.json"), "w", encoding="utf-8") as f:
            json.dump(tests, f, ensure_ascii=False)
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONHASHSEED": "0"}
        for idx, t in enumerate(tests):
            out_path = os.path.join(work, f"out_{idx}.txt")
            record = {"passed": False, "error": None}
            with open(out_path, "wb") as out:
                proc = subprocess.Popen(
                    [python, "-I", "-S", "-B", "solution.py", str(idx)],
                    cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    preexec_fn=_make_limiter(int(timeout) + 1, memory_mb),
                )
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    record["error"] = "timeout"
                finally:
                    try:  # make sure no stray descendants survive
                        os.killpg(proc.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
            if record["error"] is None:
                with open(out_path, "rb") as fh:
                    data = fh.read(1_000_000).decode("utf-8", errors="replace")
                marker = data.rfind(token)
                if marker < 0:
                    record["error"] = f"no result (exit code {proc.returncode})"
                else:
                    line = data[marker + len(token):].split("\n", 1)[0]
                    if line.startswith("OK "):
                        try:
                            record["passed"] = _canonical(line[3:]) == _canonical(t["expected_json"])
                            if not record["passed"]:
                                record["error"] = "wrong answer"
                        except ValueError:
                            record["error"] = "unparseable output"
                    else:
                        record["error"] = "exception: " + line[4:]
            per_test.append(record)
    return CodeRunResult("ok", total, sum(r["passed"] for r in per_test), per_test)
