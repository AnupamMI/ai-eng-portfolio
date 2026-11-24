"""Minimal Ollama client with Pydantic-validated structured output."""

from __future__ import annotations

import json
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

DEFAULT_URL = "http://localhost:11434"


class StructuredOutputError(Exception):
    """The model failed to produce valid output after all attempts."""


class Ollama:
    def __init__(self, model: str, *, url: str = DEFAULT_URL, temperature: float = 0.0,
                 timeout: float = 120.0, seed: int = 0):
        self.model = model
        self.options = {"temperature": temperature, "seed": seed}
        self._http = httpx.Client(base_url=url, timeout=timeout)
        # Counters so projects can report how often structured output fails.
        self.calls = 0
        self.validation_failures = 0

    def chat(self, messages: list[dict], *, format: dict | str | None = None) -> str:
        body = {"model": self.model, "messages": messages, "stream": False,
                "options": self.options}
        if format is not None:
            body["format"] = format
        self.calls += 1
        resp = self._http.post("/api/chat", json=body)
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def structured(self, messages: list[dict], schema: type[T], *, retries: int = 1) -> T:
        """Ask for JSON matching `schema`; on invalid output, show the error and retry."""
        msgs = list(messages)
        last_err: Exception | None = None
        for _ in range(retries + 1):
            raw = self.chat(msgs, format=schema.model_json_schema())
            try:
                return schema.model_validate_json(raw)
            except (ValidationError, json.JSONDecodeError) as e:
                self.validation_failures += 1
                last_err = e
                msgs = msgs + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"That output was invalid: {e}. "
                                                "Reply again with only valid JSON."},
                ]
        raise StructuredOutputError(str(last_err)) from last_err
