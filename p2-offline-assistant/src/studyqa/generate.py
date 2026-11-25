"""One generation = one section through one model in one decoding mode."""

from __future__ import annotations

from pydantic import BaseModel

from evalkit import ChatResponse, Ollama, StructuredOutputError
from studyqa.prompt import build_messages
from studyqa.schema import QuestionSet

CTX_LIMIT = 0.95  # above this share of num_ctx, assume the prompt may be truncated

# Generation settings shared by the benchmark and the `ask` tool, so the tool runs
# exactly what was measured. NUM_PREDICT: largest valid output in the smoke run was
# 1043 tokens (phi3); largest prompt 2024 tokens, and 2024 + 1536 < 4096, so a capped
# call cannot trigger a context shift (docs/LOG.md).
NUM_CTX = 4096
NUM_PREDICT = 1536
RETRIES = 2


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


def generate(llm: Ollama, section: dict, *, constrained: bool,
             retries: int = RETRIES) -> Generation:
    """Never raises on invalid output: failures are data, not exceptions."""
    try:
        r = llm.structured(build_messages(section), QuestionSet, retries=retries,
                           constrained=constrained)
        return Generation(questions=r.value, valid=True, attempts=r.attempts,
                          errors=r.errors, responses=r.responses)
    except StructuredOutputError as e:
        return Generation(questions=None, valid=False, attempts=e.attempts,
                          errors=e.errors, responses=e.responses)
