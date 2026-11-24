"""Prompt for generating revision questions. The JSON schema is included in the
prompt in BOTH decoding modes, so constrained vs json differ only in decoding."""

from __future__ import annotations

import json

from studyqa.schema import QuestionSet

PROMPT_VERSION = "v1"

SYSTEM = """You write revision questions that help a student study their own notes.
Rules:
- Write exactly 5 questions that test understanding of the section, not trivia.
- Every answer must be supported by the section alone. Do not use outside knowledge.
- For each question, source_quote must be one or two consecutive sentences copied
  word for word from the section that support the answer.
- difficulty is one of: easy, medium, hard.
Reply with only a JSON object matching this JSON schema:
{schema}"""


def build_messages(section: dict) -> list[dict]:
    schema = json.dumps(QuestionSet.model_json_schema())
    return [
        {"role": "system", "content": SYSTEM.format(schema=schema)},
        {"role": "user", "content": f"Section: {section['title']}\n\n{section['text']}"},
    ]
