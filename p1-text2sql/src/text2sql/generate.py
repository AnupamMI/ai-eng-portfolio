"""Plain SQL generation: question -> one SQLite query, as Pydantic-validated JSON.

Design: schema-constrained JSON `{"sql": ...}` through `evalkit.Ollama.structured` (as approved in
the plan), not free text with code-fence stripping. Free text needs a fragile parser, and that parser
would become part of what is measured. The cost: SQL has to be JSON-escaped, which a small model
can get wrong. That shows up as an invalid output and a retry, so it is counted rather than hidden.
There is no execution-feedback repair loop: stage 2 measures plain SQL competence.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator

from evalkit import Ollama, StructuredOutputError
from text2sql.prompt import sql_messages

NUM_CTX = 4096      # system prompt is ~700 tokens; prompt + NUM_PREDICT stays far below this
NUM_PREDICT = 256   # longest gold SQL is ~110 tokens; JSON wrapping adds a few
RETRIES = 1         # one retry on invalid JSON (same as p2)


class SQLAnswer(BaseModel):
    sql: str

    @field_validator("sql")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("sql is empty")
        return v


def generate_sql(llm: Ollama, question: str, *, retries: int = RETRIES) -> dict:
    """Returns a JSON-safe dict. `sql` is None when no valid answer was produced."""
    try:
        r = llm.structured(sql_messages(question), SQLAnswer, retries=retries)
        sql, attempts, errors, responses = r.value.sql, r.attempts, r.errors, r.responses
    except StructuredOutputError as e:
        sql, attempts, errors, responses = None, e.attempts, e.errors, e.responses
    return {
        "sql": sql,
        "attempts": attempts,
        "first_try_valid": sql is not None and attempts == 1,
        "errors": errors,
        "responses": [x.model_dump(mode="json") for x in responses],
    }
