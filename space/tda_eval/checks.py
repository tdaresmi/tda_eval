"""Programmatic instruction-following (constraint) checks. Semantics are specified in
categories.json -> constraint_semantics and QUESTION_GUIDE.md."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Tuple

from .normalize import tr_lower, tr_upper


def split_lines(text: str) -> List[str]:
    """\\r\\n/\\r -> \\n, drop leading/trailing whitespace-only lines, split on \\n (inner blank lines count)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()
    return lines


def _has_word(text: str, word: str) -> bool:
    """Whole-word match: Turkish lower-casing, case-insensitive; word chars = Unicode letters/digits/underscore.
    The apostrophe is a boundary, so "İstanbul'da" contains the word 'İstanbul' but 'verileri' does not contain 'veri'."""
    text = tr_lower(unicodedata.normalize("NFC", text))
    word = tr_lower(unicodedata.normalize("NFC", word))
    return re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text) is not None


def check_constraint(text: str, ctype: str, value: str) -> Tuple[bool, str]:
    if ctype == "line_count":
        n = len(split_lines(text))
        return n == int(value), f"lines={n}"
    if ctype == "line_prefix":
        lines = split_lines(text)
        bad = [i + 1 for i, ln in enumerate(lines) if not ln.startswith(value)]
        return bool(lines) and not bad, "all lines checked" if not bad else f"lines without prefix: {bad}"
    if ctype == "word_count_min":
        n = len(text.split())
        return n >= int(value), f"words={n}"
    if ctype == "word_count_max":
        n = len(text.split())
        return n <= int(value), f"words={n}"
    if ctype == "required_substring":
        return value in text, "substring"
    if ctype == "forbidden_substring":
        return value not in text, "substring"
    if ctype == "required_word":
        return _has_word(text, value), "whole word"
    if ctype == "forbidden_word":
        return not _has_word(text, value), "whole word"
    if ctype == "forbidden_char":
        return value not in text, "char"
    if ctype == "starts_with":
        return text.lstrip().startswith(value), "prefix"
    if ctype == "ends_with":
        return text.rstrip().endswith(value), "suffix"
    if ctype == "all_lowercase":
        return text == tr_lower(text), "tr lower"
    if ctype == "all_uppercase":
        return text == tr_upper(text), "tr upper"
    raise ValueError(f"unknown constraint type: {ctype}")


@dataclass
class ConstraintResult:
    strict: bool      # all constraints satisfied
    fraction: float   # satisfied / total
    details: List[dict]


def check_constraints(text: str, constraints: List[dict]) -> ConstraintResult:
    details = []
    for c in constraints:
        ok, info = check_constraint(text, c["type"], c["value"])
        details.append({"type": c["type"], "value": c["value"], "passed": ok, "info": info})
    n_ok = sum(d["passed"] for d in details)
    return ConstraintResult(n_ok == len(details), n_ok / len(details), details)
