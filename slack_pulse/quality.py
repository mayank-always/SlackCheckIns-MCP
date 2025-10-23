"""Utility functions to score the quality of Slack check-ins."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

KEYWORDS = {"completed", "blocked", "planning", "done", "help", "stuck"}
STRUCTURE_PATTERNS = [
    re.compile(r"^[-*]\s", re.MULTILINE),
    re.compile(r"^\d+\.\s", re.MULTILINE),
    re.compile(r"completed:\s", re.IGNORECASE),
    re.compile(r"blocked:\s", re.IGNORECASE),
    re.compile(r"planning:\s", re.IGNORECASE),
]


@dataclass(slots=True)
class QualityResult:
    """Structured representation of a quality assessment."""

    label: str
    reasons: List[str]


def assess_quality(message: str) -> QualityResult:
    """Return the quality label for a Slack check-in message."""

    normalized = message.strip().lower()
    reasons: List[str] = []

    has_length = len(normalized) > 50
    if has_length:
        reasons.append("length")

    has_keyword = any(keyword in normalized for keyword in KEYWORDS)
    if has_keyword:
        reasons.append("keyword")

    has_structure = any(pattern.search(message) for pattern in STRUCTURE_PATTERNS)
    if has_structure:
        reasons.append("structure")

    score = sum((has_length, has_keyword, has_structure))
    label = "good" if score >= 2 else "bad"
    if not reasons:
        reasons.append("insufficient_detail")
    return QualityResult(label=label, reasons=reasons)


__all__ = ["QualityResult", "assess_quality"]
