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


class ChatResponse(BaseModel):
    """Model reply plus Ollama's server-side counters (durations in seconds)."""

    content: str
    eval_count: int = 0  # generated tokens
    eval_duration_s: float = 0.0
    prompt_eval_count: int = 0  # prompt tokens actually processed
    prompt_eval_duration_s: float = 0.0
    load_duration_s: float = 0.0
    total_duration_s: float = 0.0

    @property
    def tokens_per_s(self) -> float:
        """Decode speed, excluding model load and prompt processing."""
        return self.eval_count / self.eval_duration_s if self.eval_duration_s else 0.0

    @classmethod
    def from_ollama(cls, data: dict) -> ChatResponse:
        ns = 1e9
        return cls(
            content=data["message"]["content"],
            eval_count=data.get("eval_count", 0),
            eval_duration_s=data.get("eval_duration", 0) / ns,
            prompt_eval_count=data.get("prompt_eval_count", 0),
            prompt_eval_duration_s=data.get("prompt_eval_duration", 0) / ns,
            load_duration_s=data.get("load_duration", 0) / ns,
            total_duration_s=data.get("total_duration", 0) / ns,
        )


class Ollama:
    def __init__(self, model: str, *, url: str = DEFAULT_URL, temperature: float = 0.0,
                 timeout: float = 120.0, seed: int = 0,
                 transport: httpx.BaseTransport | None = None):
        self.model = model
        self.options = {"temperature": temperature, "seed": seed}
        # `transport` lets tests inject httpx.MockTransport instead of a live server.
        self._http = httpx.Client(base_url=url, timeout=timeout, transport=transport)

    def chat(self, messages: list[dict], *, format: dict | str | None = None) -> ChatResponse:
        body = {"model": self.model, "messages": messages, "stream": False,
                "options": self.options}
        if format is not None:
            body["format"] = format
        resp = self._http.post("/api/chat", json=body)
        resp.raise_for_status()
        return ChatResponse.from_ollama(resp.json())

    def structured(self, messages: list[dict], schema: type[T], *, retries: int = 1) -> T:
        """Ask for JSON matching `schema`; on invalid output, show the error and retry."""
        msgs = list(messages)
        last_err: Exception | None = None
        for _ in range(retries + 1):
            raw = self.chat(msgs, format=schema.model_json_schema()).content
            try:
                return schema.model_validate_json(raw)
            except (ValidationError, json.JSONDecodeError) as e:
                last_err = e
                msgs = msgs + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"That output was invalid: {e}. "
                                                "Reply again with only valid JSON."},
                ]
        raise StructuredOutputError(str(last_err)) from last_err
