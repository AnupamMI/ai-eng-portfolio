"""Test-set schema: questions with one gold SQL per interpretation.

Stored as evalkit `Case` JSONL (`input` = the question, `expected` = the `Spec` below, `tags` =
[label, category]), so the shared loader and runner work unchanged; `load` validates `expected`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from evalkit import Case, load_cases
from pydantic import BaseModel, model_validator

Label = Literal["clear", "ambiguous"]
Category = Literal["clear", "metric", "time_window", "entity", "scope", "granularity"]
AMBIGUITY_CATEGORIES = ("metric", "time_window", "entity", "scope", "granularity")


class Interpretation(BaseModel):
    id: str
    description: str                     # what this reading means, in words
    clarifying_answer: str | None = None  # the simulated user's reply selecting this reading
    gold_sql: str
    ordered: bool = False                # row order is part of the answer
    expect_empty: bool = False           # an empty result is the correct answer


class Spec(BaseModel):
    label: Label
    category: Category
    note: str  # clear: why there is only one reading; ambiguous: what is left open
    interpretations: list[Interpretation]

    @model_validator(mode="after")
    def _consistent(self) -> "Spec":
        n = len(self.interpretations)
        if self.label == "clear":
            if n != 1 or self.category != "clear":
                raise ValueError("a clear question has category 'clear' and one interpretation")
        else:
            if not 2 <= n <= 3 or self.category == "clear":
                raise ValueError("an ambiguous question has an ambiguity category and 2-3 readings")
            if any(not i.clarifying_answer for i in self.interpretations):
                raise ValueError("every reading of an ambiguous question needs a clarifying_answer")
        ids = [i.id for i in self.interpretations]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate interpretation ids")
        return self


class Question(BaseModel):
    id: str
    question: str
    spec: Spec

    @property
    def label(self) -> Label:
        return self.spec.label


def load(path: str | Path) -> list[Question]:
    out = []
    for c in load_cases(path):
        spec = Spec.model_validate(c.expected)
        if c.tags != [spec.label, spec.category]:
            raise ValueError(f"{path}: {c.id}: tags must be [label, category]")
        out.append(Question(id=c.id, question=c.input, spec=spec))
    return out


def to_case(q: Question) -> Case:
    return Case(id=q.id, input=q.question, expected=q.spec.model_dump(exclude_defaults=True),
                tags=[q.spec.label, q.spec.category])


def pairs(questions: list[Question]) -> list[tuple[Question, Interpretation]]:
    """Every (question, intended reading): the scoring unit for conditions A/B/C."""
    return [(q, i) for q in questions for i in q.spec.interpretations]


TESTSET_DIR = Path(__file__).resolve().parents[2] / "testset"
