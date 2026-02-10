"""Deterministic text adapters for entropy, rotation, and grounding checks."""
from __future__ import annotations

import ast
import re
from typing import Any

SURREAL_TOKENS = {
    "dream", "dreams", "purple", "cloud", "clouds", "fly", "wings", "magic",
    "ether", "telepathy", "hallucination", "becomes", "eat", "cosmic", "unicorn",
}

PHYSICS_RED_FLAGS = [
    "wings are made of dreams",
    "data becomes purple",
    "eat the clouds",
    "gravity is optional",
]

CONCRETE_TERMS = {
    "device", "sensor", "mode", "input", "output", "log", "test", "system", "file",
    "protocol", "controller", "signal", "compute", "process", "result",
}


def _words(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def entropy_score(text: str) -> dict[str, Any]:
    """Return bounded entropy score with transparent details."""
    words = _words(text)
    token_count = len(words) or 1
    unique_ratio = len(set(words)) / token_count
    surreal_hits = sum(1 for word in words if word in SURREAL_TOKENS)
    surreal_ratio = surreal_hits / token_count

    score = min(1.0, 0.55 * unique_ratio + 0.45 * surreal_ratio)
    label = "HIGH" if score >= 0.45 else "LOW"

    return {
        "score": round(score, 6),
        "label": label,
        "details": {
            "token_count": token_count,
            "unique_ratio": round(unique_ratio, 6),
            "surreal_hits": surreal_hits,
            "surreal_ratio": round(surreal_ratio, 6),
            "threshold_high": 0.45,
        },
    }


def rotate_text(text: str) -> str:
    """Compress and normalize text in a deterministic/auditable way."""
    words = re.findall(r"\S+", text)
    if not words:
        return ""

    filtered = [w for w in words if re.sub(r"\W+", "", w).lower() not in SURREAL_TOKENS]
    source = filtered if filtered else words
    compact = " ".join(source[:20]).strip()
    compact = re.sub(r"\s+", " ", compact)
    return compact


def grounding_check(text: str) -> dict[str, Any]:
    """Assess whether text appears grounded with explicit evidence flags."""
    lowered = text.lower()
    words = set(_words(text))

    impossible_math = bool(re.search(r"\b(\d+)\s*\+\s*(\d+)\s*=\s*(\d+)\b", lowered))
    math_valid = True
    if impossible_math:
        match = re.search(r"\b(\d+)\s*\+\s*(\d+)\s*=\s*(\d+)\b", lowered)
        if match:
            left = int(match.group(1)) + int(match.group(2))
            right = int(match.group(3))
            math_valid = left == right

    physics_consistent = not any(flag in lowered for flag in PHYSICS_RED_FLAGS)

    executable_code = False
    if any(marker in text for marker in ("def ", "class ", "import ", "{")):
        try:
            ast.parse(text)
            executable_code = True
        except SyntaxError:
            executable_code = False

    has_concrete_context = len(words.intersection(CONCRETE_TERMS)) > 0
    grounded = bool(math_valid and physics_consistent and (executable_code or has_concrete_context))

    if not math_valid:
        reason = "math_invalid"
    elif not physics_consistent:
        reason = "physics_inconsistent"
    elif not (executable_code or has_concrete_context):
        reason = "missing_concrete_context"
    else:
        reason = "grounded"

    return {
        "grounded": grounded,
        "reason": reason,
        "evidence": {
            "math_valid": math_valid,
            "physics_consistent": physics_consistent,
            "executable_code": executable_code,
        },
    }
