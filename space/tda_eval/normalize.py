"""Turkish-aware text normalization and strict answer parsers.

The behaviour implemented here is specified in categories.json -> normalization_profiles; the unit tests execute the
examples stored there against this code, so the two cannot silently drift apart.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import List, Optional

ZERO_WIDTH = "​‌‍⁠﻿"
_ZERO_WIDTH_TABLE = {ord(c): None for c in ZERO_WIDTH}
_APOSTROPHE_TABLE = {ord("’"): "'", ord("‘"): "'", ord("ʼ"): "'"}
TRIM_CHARS = " \"'“”„«».,;:!?…"

TEXT_PROFILES = ("tr_text", "tr_text_case_sensitive", "none")


def tr_lower(text: str) -> str:
    """Turkish lower-casing: İ -> i and I -> ı (Python's own lower() would give 'i̇' and 'i')."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def tr_upper(text: str) -> str:
    """Turkish upper-casing: i -> İ and ı -> I."""
    return text.replace("i", "İ").replace("ı", "I").upper()


def _basic(text: str) -> str:
    """Steps 1-3: NFC, drop zero-width characters, collapse all Unicode whitespace to single spaces."""
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_ZERO_WIDTH_TABLE)
    return " ".join(text.split())


def normalize(text: str, profile: str) -> str:
    """Normalize `text` for COMPARISON only. The raw text must always be kept by the caller."""
    if profile == "none":
        return text  # identity: byte-for-byte the same string
    if profile not in ("tr_text", "tr_text_case_sensitive"):
        raise ValueError(f"'{profile}' is a parser profile, not a text profile; use parse_choice/parse_number")
    text = _basic(text).translate(_APOSTROPHE_TABLE)
    if profile == "tr_text":
        text = tr_lower(text).replace("i̇", "i")
    return text.strip(TRIM_CHARS)


# --------------------------------------------------------------------------- choice parsing
CHOICE_PREFIXES = ("cevap", "yanıt", "doğru cevap", "doğru yanıt", "doğru seçenek")
_BARE_LABEL = re.compile(r"^(?:([A-Ea-e])[.)]?|\(([A-Ea-e])\)\.?)$")
_STANDALONE_UPPER = re.compile(r"(?<!\w)([A-E])(?!\w)")


@dataclass
class ChoiceParse:
    status: str  # parsed | ambiguous | invalid_format | invalid_label
    label: Optional[str] = None
    flags: List[str] = field(default_factory=list)


def parse_choice(response: str, valid_labels: str) -> ChoiceParse:
    """Strictly parse a multiple-choice answer. Never guesses: see categories.json -> choice_label."""
    text = _basic(response)
    candidate = None
    m = _BARE_LABEL.match(text)
    if m:
        candidate = m.group(1) or m.group(2)
    elif ":" in text:
        head, _, tail = text.partition(":")
        if tr_lower(head.strip()) in CHOICE_PREFIXES:
            m2 = _BARE_LABEL.match(tail.strip())
            if m2:
                candidate = m2.group(1) or m2.group(2)
    if candidate is not None:
        label = candidate.upper()
        if label in valid_labels:
            return ChoiceParse("parsed", label)
        return ChoiceParse("invalid_label", None, ["invalid_label"])
    distinct = sorted(set(_STANDALONE_UPPER.findall(text)))
    if len(distinct) >= 2:
        return ChoiceParse("ambiguous", None, ["ambiguous_answer"])
    return ChoiceParse("invalid_format", None, ["invalid_format"])


# --------------------------------------------------------------------------- numeric parsing
_NUMBER_TOKEN = re.compile(r"[0-9][0-9.,]*")
_WHOLE = re.compile(
    r"^(?:(?:cevap|yanıt)\s*:\s*)?(?P<sign>[-−])?(?P<num>[0-9][0-9.,]*?)(?:\s*(?P<unit>[^\W\d_]{1,12}))?\.?$",
    re.IGNORECASE,
)


@dataclass
class NumberParse:
    status: str  # parsed | ambiguous | multiple_numbers | invalid_format
    value: Optional[Decimal] = None
    candidates: List[Decimal] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)


def _classify(num: str) -> NumberParse:
    """Classify one unsigned numeric token that starts with a digit."""
    if num.endswith((".", ",")) or ".." in num or ",," in num or ".," in num or ",." in num:
        return NumberParse("invalid_format", flags=["invalid_format"])
    if re.fullmatch(r"[0-9]+", num):
        return NumberParse("parsed", Decimal(num))
    has_dot, has_comma = "." in num, "," in num
    if has_dot and has_comma:
        dec = "." if num.rfind(".") > num.rfind(",") else ","
        grp = "," if dec == "." else "."
        if num.count(dec) != 1:
            return NumberParse("invalid_format", flags=["invalid_format"])
        integer, _, frac = num.partition(dec)
        if not re.fullmatch(rf"[0-9]{{1,3}}(?:{re.escape(grp)}[0-9]{{3}})+", integer) or not re.fullmatch(r"[0-9]+", frac):
            return NumberParse("invalid_format", flags=["invalid_format"])
        return NumberParse("parsed", Decimal(integer.replace(grp, "") + "." + frac), flags=["grouping_separator_used"])
    sep = "." if has_dot else ","
    parts = num.split(sep)
    if len(parts) > 2:  # repeated separator -> must be thousands grouping
        if re.fullmatch(rf"[0-9]{{1,3}}(?:{re.escape(sep)}[0-9]{{3}})+", num):
            return NumberParse("parsed", Decimal(num.replace(sep, "")), flags=["grouping_separator_used"])
        return NumberParse("invalid_format", flags=["invalid_format"])
    left, right = parts
    if len(right) == 3 and re.fullmatch(r"[1-9][0-9]{0,2}", left):
        return NumberParse(
            "ambiguous",
            None,
            [Decimal(left + right), Decimal(left + "." + right)],
            ["ambiguous_number"],
        )
    return NumberParse("parsed", Decimal(left + "." + right))


def parse_number(response: str) -> NumberParse:
    """Strictly parse a numeric answer. Never guesses ambiguous formats such as '1.234'."""
    text = _basic(response)
    tokens = _NUMBER_TOKEN.findall(text)
    if len(tokens) >= 2:
        return NumberParse("multiple_numbers", flags=["multiple_numbers"])
    m = _WHOLE.match(text)
    if not m:
        return NumberParse("invalid_format", flags=["invalid_format"])
    result = _classify(m.group("num"))
    if result.status == "parsed" and m.group("sign"):
        result.value = -result.value
    if result.status == "ambiguous" and m.group("sign"):
        result.candidates = [-c for c in result.candidates]
    return result


def score_numeric(response: str, answer: str, tolerance: float) -> dict:
    """Score a numeric item. Ambiguous / multi-number / malformed answers score 0 and are flagged."""
    parsed = parse_number(response)
    out = {"parse_status": parsed.status, "parsed_answer": None, "flags": list(parsed.flags), "details": None}
    if parsed.status == "parsed":
        expected = Decimal(answer)
        tol = Decimal(str(tolerance))
        out["parsed_answer"] = format(parsed.value, "f")
        passed = abs(parsed.value - expected) <= tol
    else:
        passed = False
        if parsed.status == "ambiguous":
            out["details"] = "ambiguous interpretations: " + " | ".join(format(c, "f") for c in parsed.candidates)
    out["passed"] = passed
    out["score"] = 1.0 if passed else 0.0
    return out


def score_choice(response: str, answer: str, valid_labels: str) -> dict:
    parsed = parse_choice(response, valid_labels)
    passed = parsed.status == "parsed" and parsed.label == answer
    return {"parse_status": parsed.status, "parsed_answer": parsed.label, "flags": list(parsed.flags),
            "details": None, "passed": passed, "score": 1.0 if passed else 0.0}


def score_exact_match(response: str, answer: str, accepted_answers: Optional[List[str]], profile: str) -> dict:
    """exact_match: the response and EVERY key entry (answer + each accepted answer) are normalized separately.
    No equivalence beyond what the author listed explicitly is ever assumed."""
    keys = [answer] + list(accepted_answers or [])
    norm_response = normalize(response, profile)
    matched = next((k for k in keys if normalize(k, profile) == norm_response and norm_response != ""), None)
    passed = matched is not None
    return {"parse_status": "not_applicable", "parsed_answer": norm_response, "flags": [],
            "details": None if not passed else f"matched key: {matched}", "passed": passed,
            "score": 1.0 if passed else 0.0}
