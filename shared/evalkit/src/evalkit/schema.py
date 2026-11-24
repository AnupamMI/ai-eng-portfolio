"""Core data models shared by every project's eval."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Case(BaseModel):
    """One eval example. `input` and `expected` are free-form per project."""

    id: str
    input: Any
    expected: Any = None
    tags: list[str] = Field(default_factory=list)


class Result(BaseModel):
    """Outcome of running one case through a system under test."""

    case_id: str
    output: Any = None
    error: str | None = None
    latency_s: float
    scores: dict[str, float] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)


def load_cases(path: str | Path) -> list[Case]:
    """Load cases from a JSONL file (one JSON object per line)."""
    cases = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if line.strip():
                try:
                    cases.append(Case.model_validate_json(line))
                except ValueError as e:
                    raise ValueError(f"{path}:{lineno}: {e}") from e
    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: duplicate case ids")
    return cases


def save_results(results: list[Result], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(r.model_dump_json() + "\n")


def load_results(path: str | Path) -> list[Result]:
    with open(path, encoding="utf-8") as f:
        return [Result.model_validate(json.loads(line)) for line in f if line.strip()]
