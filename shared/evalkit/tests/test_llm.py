"""Offline tests for the Ollama client, using httpx.MockTransport."""

import json

import httpx

from evalkit.llm import ChatResponse, Ollama


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
