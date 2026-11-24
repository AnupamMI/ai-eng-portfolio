import json

import httpx

from evalkit import Ollama
from studyqa.generate import generate
from studyqa.prompt import build_messages
from studyqa.schema import QuestionSet

SECTION = {"title": "Closures", "text": "A closure is a function bundled with its scope."}
Q = {"question": "What is a closure?", "answer": "A function plus its scope.",
     "difficulty": "easy", "source_quote": "A closure is a function bundled with its scope."}


def fake(replies, seen, prompt_tokens=100):
    it = iter(replies)

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": next(it)},
                                         "eval_count": 10, "eval_duration": 10**9,
                                         "prompt_eval_count": prompt_tokens})
    return httpx.MockTransport(handler)


def test_prompt_contains_schema_and_section():
    msgs = build_messages(SECTION)
    assert '"source_quote"' in msgs[0]["content"]
    assert "Closures" in msgs[1]["content"] and "bundled" in msgs[1]["content"]


def test_valid_first_try():
    seen = []
    llm = Ollama("m", transport=fake([json.dumps({"questions": [Q] * 5})], seen))
    g = generate(llm, SECTION, constrained=True)
    assert g.valid and g.first_try_valid and g.attempts == 1
    assert isinstance(seen[0]["format"], dict)


def test_wrong_count_retries_then_fails_without_raising():
    seen = []
    four = json.dumps({"questions": [Q] * 4})
    llm = Ollama("m", transport=fake([four] * 3, seen))
    g = generate(llm, SECTION, constrained=False, retries=2)
    assert not g.valid and g.questions is None and g.attempts == 3
    assert seen[0]["format"] == "json"
    assert len(g.responses) == 3 and "at least 5" in g.errors[0]


def test_ctx_overflow_flagged():
    llm = Ollama("m", num_ctx=1000,
                 transport=fake([json.dumps({"questions": [Q] * 5})], [], prompt_tokens=990))
    assert generate(llm, SECTION, constrained=True).ctx_overflow


def test_extra_keys_are_ignored():
    q = QuestionSet.model_validate({"questions": [{**Q, "topic": "x"}] * 5, "notes": "y"})
    assert len(q.questions) == 5
