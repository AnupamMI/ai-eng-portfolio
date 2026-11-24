"""Structured output contract. Validators are structural only: groundedness is
measured separately so a hallucinated quote is not mistaken for a schema error."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RevisionQuestion(BaseModel):
    question: str = Field(min_length=10)
    answer: str = Field(min_length=1)
    # Generated but NOT evaluated (no ground truth for difficulty); see README.
    difficulty: Literal["easy", "medium", "hard"]
    source_quote: str = Field(min_length=10, description="Verbatim sentence(s) from the section")


class QuestionSet(BaseModel):
    # Extra keys are ignored (pydantic default): the contract is that these
    # fields exist with these types, not that nothing else is emitted.
    questions: list[RevisionQuestion] = Field(min_length=5, max_length=5)
