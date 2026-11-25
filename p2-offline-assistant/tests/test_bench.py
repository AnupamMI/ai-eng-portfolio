import json

import httpx

from evalkit import Case, Ollama, run
from studyqa.bench import SCORERS, make_system

TEXT = "A closure is the combination of a function bundled together with its surrounding state."
SECTION = {"id": "s1", "title": "Closures", "text": TEXT}
GOOD = {"question": "What is a closure?", "answer": "A function bundled with surrounding state.",
        "difficulty": "easy", "source_quote": TEXT}
BAD = {**GOOD, "answer": "Garbage collection in Python.", "source_quote": "Python frees memory."}


def llm_replying(*replies):
    it = iter(replies)
    return Ollama("m", transport=httpx.MockTransport(lambda req: httpx.Response(200, json={
        "message": {"content": next(it)}, "eval_count": 20, "eval_duration": 10**9})))


def test_scores_for_valid_output():
    llm = llm_replying(json.dumps({"questions": [GOOD] * 4 + [BAD]}))
    (r,) = run(make_system(llm, True, 2), [Case(id="s1", input=SECTION)], SCORERS)
    assert r.scores == {"valid_first_try": 1.0, "valid": 1.0, "grounded": 0.8}
    assert len(r.output["grounding"]) == 5 and r.output["attempts"] == 1


def test_scores_for_output_valid_after_retry():
    llm = llm_replying('{"questions": []}', json.dumps({"questions": [GOOD] * 5}))
    (r,) = run(make_system(llm, False, 2), [Case(id="s1", input=SECTION)], SCORERS)
    assert r.scores == {"valid_first_try": 0.0, "valid": 1.0, "grounded": 1.0}


def test_scores_for_invalid_output():
    llm = llm_replying("{}", "{}", "{}")
    (r,) = run(make_system(llm, False, 2), [Case(id="s1", input=SECTION)], SCORERS)
    assert r.error is None  # a schema failure is a measured outcome, not a crash
    assert r.scores == {"valid_first_try": 0.0, "valid": 0.0, "grounded": 0.0}
    assert r.output["attempts"] == 3 and r.output["grounding"] == []


def test_stall_dump_arms_and_always_cancels(monkeypatch):
    import pytest
    from studyqa import bench
    calls = []
    monkeypatch.setattr(bench.faulthandler, "dump_traceback_later",
                        lambda s, repeat: calls.append(("arm", s, repeat)))
    monkeypatch.setattr(bench.faulthandler, "cancel_dump_traceback_later",
                        lambda: calls.append(("cancel",)))
    with pytest.raises(RuntimeError):
        with bench.stall_dump(900):
            raise RuntimeError("generation failed")
    assert calls == [("arm", 900, True), ("cancel",)]
    calls.clear()
    with bench.stall_dump(0):
        pass
    assert calls == []
