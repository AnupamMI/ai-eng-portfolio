"""Minimal Ollama client with Pydantic-validated structured output."""

from __future__ import annotations

import json
from typing import Generic, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

DEFAULT_URL = "http://localhost:11434"


class ChatResponse(BaseModel):
    """Model reply plus Ollama's server-side counters (durations in seconds)."""

    content: str
    eval_count: int = 0  # generated tokens
    eval_duration_s: float = 0.0
    prompt_eval_count: int = 0  # prompt tokens actually processed
    prompt_eval_duration_s: float = 0.0
    load_duration_s: float = 0.0
    total_duration_s: float = 0.0
    num_ctx: int | None = None  # context window the request ran with

    @property
    def tokens_per_s(self) -> float:
        """Decode speed, excluding model load and prompt processing."""
        return self.eval_count / self.eval_duration_s if self.eval_duration_s else 0.0

    @property
    def ctx_fraction(self) -> float | None:
        """Share of the context window used. Near 1.0 means Ollama may have
        silently truncated the prompt; callers should treat that as a failure."""
        if not self.num_ctx:
            return None
        return (self.prompt_eval_count + self.eval_count) / self.num_ctx

    @classmethod
    def from_ollama(cls, data: dict, *, num_ctx: int | None = None) -> ChatResponse:
        ns = 1e9
        return cls(
            num_ctx=num_ctx,
            content=data["message"]["content"],
            eval_count=data.get("eval_count", 0),
            eval_duration_s=data.get("eval_duration", 0) / ns,
            prompt_eval_count=data.get("prompt_eval_count", 0),
            prompt_eval_duration_s=data.get("prompt_eval_duration", 0) / ns,
            load_duration_s=data.get("load_duration", 0) / ns,
            total_duration_s=data.get("total_duration", 0) / ns,
        )


class StructuredResult(BaseModel, Generic[T]):
    """A validated value plus how hard it was to get."""

    value: T
    attempts: int  # 1 = valid on the first try
    errors: list[str] = []  # validation errors from failed attempts, in order
    responses: list[ChatResponse] = []  # one per attempt, including failed ones

    @property
    def first_try(self) -> bool:
        return self.attempts == 1


class StructuredOutputError(Exception):
    """The model failed to produce valid output after all attempts."""

    def __init__(self, message: str, *, attempts: int, errors: list[str],
                 responses: list[ChatResponse]):
        super().__init__(message)
        self.attempts = attempts
        self.errors = errors
        self.responses = responses


class Ollama:
    def __init__(self, model: str, *, url: str = DEFAULT_URL, temperature: float = 0.0,
                 timeout: float = 120.0, seed: int = 0, num_ctx: int = 4096,
                 keep_alive: str | int = "5m",
                 transport: httpx.BaseTransport | None = None):
        """`num_ctx` is always sent explicitly: Ollama's default differs across
        versions and over-long prompts are truncated without an error.
        `keep_alive` controls how long the model stays loaded (0 = unload now)."""
        self.model = model
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.options = {"temperature": temperature, "seed": seed, "num_ctx": num_ctx}
        # `transport` lets tests inject httpx.MockTransport instead of a live server.
        self._http = httpx.Client(base_url=url, timeout=timeout, transport=transport)

    def chat(self, messages: list[dict], *, format: dict | str | None = None) -> ChatResponse:
        body = {"model": self.model, "messages": messages, "stream": False,
                "options": self.options, "keep_alive": self.keep_alive}
        if format is not None:
            body["format"] = format
        resp = self._http.post("/api/chat", json=body)
        resp.raise_for_status()
        return ChatResponse.from_ollama(resp.json(), num_ctx=self.num_ctx)

    def unload(self) -> None:
        """Evict the model from memory (used between benchmark runs)."""
        self._http.post("/api/generate", json={"model": self.model, "keep_alive": 0}
                        ).raise_for_status()

    def structured(self, messages: list[dict], schema: type[T], *,
                   retries: int = 1) -> StructuredResult[T]:
        """Ask for JSON matching `schema`; on invalid output, show the error and retry.

        Returns the parsed value with per-attempt metadata. Raises
        StructuredOutputError (carrying the same metadata) if every attempt fails.
        """
        msgs = list(messages)
        responses: list[ChatResponse] = []
        errors: list[str] = []
        for _ in range(retries + 1):
            resp = self.chat(msgs, format=schema.model_json_schema())
            responses.append(resp)
            try:
                value = schema.model_validate_json(resp.content)
                return StructuredResult[schema](value=value, attempts=len(responses),
                                                errors=errors, responses=responses)
            except (ValidationError, json.JSONDecodeError) as e:
                errors.append(str(e))
                msgs = msgs + [
                    {"role": "assistant", "content": resp.content},
                    {"role": "user", "content": f"That output was invalid: {e}. "
                                                "Reply again with only valid JSON."},
                ]
        raise StructuredOutputError(errors[-1], attempts=len(responses), errors=errors,
                                    responses=responses)
