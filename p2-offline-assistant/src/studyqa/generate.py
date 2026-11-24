"""One generation = one section through one model in one decoding mode."""

from __future__ import annotations

from pydantic import BaseModel

from evalkit import ChatResponse, Ollama, StructuredOutputError
from studyqa.prompt import build_messages
from studyqa.schema import QuestionSet

CTX_LIMIT = 0.95  # above this share of num_ctx, assume the prompt may be truncated


class Generation(BaseModel):
    questions: QuestionSet | None  # None when every attempt failed validation
    valid: bool
    attempts: int
    errors: list[str]
    responses: list[ChatResponse]

    @property
    def first_try_valid(self) -> bool:
        return self.valid and self.attempts == 1

    @property
    def ctx_overflow(self) -> bool:
        return any((r.ctx_fraction or 0) > CTX_LIMIT for r in self.responses)


def generate(llm: Ollama, section: dict, *, constrained: bool, retries: int = 2) -> Generation:
    """Never raises on invalid output: failures are data, not exceptions."""
    try:
        r = llm.structured(build_messages(section), QuestionSet, retries=retries,
                           constrained=constrained)
        return Generation(questions=r.value, valid=True, attempts=r.attempts,
                          errors=r.errors, responses=r.responses)
    except StructuredOutputError as e:
        return Generation(questions=None, valid=False, attempts=e.attempts,
                          errors=e.errors, responses=e.responses)
