"""Offline tests for the Ollama client, using httpx.MockTransport."""

import json

import httpx
import pytest
from pydantic import BaseModel

from evalkit.llm import ChatResponse, Ollama, StructuredOutputError


class Pair(BaseModel):
    a: int
    b: int


def fake_ollama(replies: list[str], seen: list[dict]):
    """Mock /api/chat: returns `replies` in order and records request bodies."""
    it = iter(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": next(it)},
            "eval_count": 50, "eval_duration": 2_000_000_000,
            "prompt_eval_count": 120, "prompt_eval_duration": 500_000_000,
            "load_duration": 100_000_000, "total_duration": 2_600_000_000,
        })

    return httpx.MockTransport(handler)


def test_chat_returns_usage_counts():
    seen: list[dict] = []
    llm = Ollama("m", transport=fake_ollama(["hi"], seen))
    r = llm.chat([{"role": "user", "content": "x"}])
    assert isinstance(r, ChatResponse)
    assert r.content == "hi"
    assert r.eval_count == 50 and r.prompt_eval_count == 120
    assert r.eval_duration_s == 2.0 and r.load_duration_s == 0.1
    assert r.tokens_per_s == 25.0


def test_tokens_per_s_handles_missing_counters():
    r = ChatResponse.from_ollama({"message": {"content": "x"}})
    assert r.tokens_per_s == 0.0


def test_structured_first_try():
    seen: list[dict] = []
    llm = Ollama("m", transport=fake_ollama(['{"a": 1, "b": 2}'], seen))
    r = llm.structured([{"role": "user", "content": "x"}], Pair)
    assert r.value == Pair(a=1, b=2)
    assert r.attempts == 1 and r.first_try and r.errors == []
    assert len(r.responses) == 1
    assert seen[0]["format"] == Pair.model_json_schema()


def test_structured_retry_feeds_error_back():
    seen: list[dict] = []
    llm = Ollama("m", transport=fake_ollama(['{"a": 1}', '{"a": 1, "b": 2}'], seen))
    r = llm.structured([{"role": "user", "content": "x"}], Pair, retries=2)
    assert r.attempts == 2 and not r.first_try
    assert len(r.errors) == 1 and "b" in r.errors[0]
    assert sum(x.eval_count for x in r.responses) == 100  # retry tokens are counted
    retry_msgs = seen[1]["messages"]
    assert retry_msgs[-2] == {"role": "assistant", "content": '{"a": 1}'}
    assert "invalid" in retry_msgs[-1]["content"]


def test_structured_gives_up_with_metadata():
    seen: list[dict] = []
    llm = Ollama("m", transport=fake_ollama(["not json", "{}"], seen))
    with pytest.raises(StructuredOutputError) as exc:
        llm.structured([{"role": "user", "content": "x"}], Pair, retries=1)
    assert exc.value.attempts == 2
    assert len(exc.value.errors) == 2 and len(exc.value.responses) == 2
