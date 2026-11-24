"""Generic scorers. Project-specific ones live in each project."""

from __future__ import annotations

import re
import string
from typing import Any

from evalkit.schema import Case


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = text.translate(str.maketrans("", "", string.punctuation))
    return re.sub(r"\s+", " ", text)


def exact_match(case: Case, output: Any) -> float:
    return float(_normalize(str(output)) == _normalize(str(case.expected)))


def contains(case: Case, output: Any) -> float:
    """1 if the expected string appears in the output (after normalizing)."""
    return float(_normalize(str(case.expected)) in _normalize(str(output)))


def token_f1(case: Case, output: Any) -> float:
    """SQuAD-style token-overlap F1."""
    pred = _normalize(str(output)).split()
    gold = _normalize(str(case.expected)).split()
    if not pred or not gold:
        return float(pred == gold)
    common: dict[str, int] = {}
    for t in pred:
        common[t] = common.get(t, 0) + 1
    overlap = 0
    for t in gold:
        if common.get(t, 0) > 0:
            overlap += 1
            common[t] -= 1
    if overlap == 0:
        return 0.0
    precision, recall = overlap / len(pred), overlap / len(gold)
    return 2 * precision * recall / (precision + recall)
