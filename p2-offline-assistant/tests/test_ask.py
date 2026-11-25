import io
import json
import sys
from pathlib import Path

import httpx
import pytest

from studyqa import __main__ as cli
from studyqa.ask import GENERATION_FAILED, OK, OLLAMA, USAGE, load_sections, run_ask
from studyqa.schema import QuestionSet

NOTES = Path(__file__).parents[1] / "notes_sample" / "03_transformers_and_attention.md"
TAGS = {"models": [{"name": "qwen2.5:3b", "model": "qwen2.5:3b"},
                   {"name": "phi3:latest", "model": "phi3:latest"}]}


def _first_sentence(text: str) -> str:
    body = " ".join(line for line in text.splitlines() if line.strip() and not line.startswith("#"))
    return body.split(". ")[0] + "."


def _questions(quote: str) -> str:
    q = {"question": "What does this section explain?", "answer": "It explains attention.",
         "difficulty": "easy", "source_quote": quote}
    return json.dumps({"questions": [q] * 5})


def mock(chat_replies=(), tags=TAGS, seen=None, chat_status=200):
    replies = iter(chat_replies)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/tags":
            return httpx.Response(200, json=tags)
        if seen is not None:
            seen.append(json.loads(req.content))
        if chat_status != 200:
            return httpx.Response(chat_status, json={"error": "boom"})
        content, reason = next(replies)
        return httpx.Response(200, json={"message": {"content": content}, "done_reason": reason,
                                         "eval_count": 20, "eval_duration": 10**9})
    return httpx.MockTransport(handler)


def ask(path=NOTES, *, list_only=False, section=None, model="qwen2.5:3b", as_json=False,
        transport=None):
    out, err = io.StringIO(), io.StringIO()
    code = run_ask(Path(path), list_only=list_only, section=section, model=model,
                   as_json=as_json, transport=transport, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


def _words(n):
    return " ".join(["word"] * n)


# --- sections -----------------------------------------------------------------------

def test_list_sections_matches_splitter():
    code, out, _ = ask(list_only=True)
    secs, _ = load_sections(NOTES)
    assert code == OK and len(secs) == 7
    lines = out.rstrip().splitlines()
    assert len(lines) == 7 and lines[0].startswith("  1. ") and lines[6].startswith("  7. ")
    assert secs[2].title.split(" > ")[-1] in lines[2]


def test_skipped_sections_are_listed_with_reason(tmp_path):
    p = tmp_path / "n.md"
    # > 1200 words in total, so the splitter splits at the ## headings
    p.write_text(f"# Notes\n\n## A\n\n{_words(600)}\n\n## Tiny\n\n{_words(20)}\n\n"
                 f"## B\n\n{_words(600)}\n", encoding="utf-8")
    code, out, _ = ask(p, list_only=True)
    assert code == OK and "  1. A (600 words)" in out and "  2. B (600 words)" in out
    assert "Skipped" in out and "Tiny (20 words): too short (<150 words)" in out


def test_short_file_is_one_section_even_with_headings(tmp_path):
    # Documented splitter behaviour: a node is only split when it exceeds 1200 words.
    p = tmp_path / "short.md"
    p.write_text(f"# Notes\n\n## A\n\n{_words(200)}\n\n## B\n\n{_words(200)}\n", encoding="utf-8")
    code, out, _ = ask(p, list_only=True)
    assert code == OK and out.rstrip().splitlines() == ["  1. Notes (404 words)"]  # 400 + 2 heading lines


@pytest.mark.parametrize("n", [0, 8])
def test_section_out_of_range(n):
    code, _, err = ask(section=n, transport=mock())
    assert code == USAGE and "numbered 1-7" in err


@pytest.mark.parametrize("name,content,msg", [
    ("missing.md", None, "file not found"),
    ("notes.pdf", b"%PDF-1.4", "PDF is not supported yet"),
    ("notes.txt", b"hello", "unsupported file type '.txt'"),
    ("empty.md", b"# T\n\n## A\n\nshort\n", "no usable sections"),
])
def test_bad_inputs_have_clear_messages(tmp_path, name, content, msg):
    p = tmp_path / name
    if content is not None:
        p.write_bytes(content)
    code, out, err = ask(p, section=1, transport=mock())
    assert code == USAGE and msg in err and out == "" and "Traceback" not in err


# --- Ollama preflight -----------------------------------------------------------------

def test_ollama_not_running():
    def down(req):
        raise httpx.ConnectError("refused", request=req)
    code, _, err = ask(section=1, transport=httpx.MockTransport(down))
    assert code == OLLAMA and "Ollama is not running" in err and "ollama serve" in err


def test_model_not_pulled_names_the_pull_command():
    code, _, err = ask(section=1, model="llama3.2:3b", transport=mock())
    assert code == OLLAMA and "ollama pull llama3.2:3b" in err and "qwen2.5:3b" in err


def test_untagged_model_name_matches_latest():
    sec = load_sections(NOTES)[0][0]
    code, _, _ = ask(section=1, model="phi3",
                     transport=mock([(_questions(_first_sentence(sec.text)), "stop")]))
    assert code == OK


def test_ollama_http_error_during_generation():
    code, _, err = ask(section=1, transport=mock(chat_status=500))
    assert code == OLLAMA and "Ollama request failed" in err


# --- generation -----------------------------------------------------------------------

def test_happy_path_text_uses_benchmarked_settings():
    sec = load_sections(NOTES)[0][0]
    seen = []
    code, out, err = ask(section=1, transport=mock(
        [(_questions(_first_sentence(sec.text)), "stop")], seen=seen))
    assert code == OK and "Generating 5 questions" in err
    assert out.startswith("Section 1/7: ") and "valid on attempt 1" in out
    assert "20 tokens at 20.0 tok/s" in out  # mock: eval_count 20 over 1 s
    for i in range(1, 6):
        assert f"\n{i}. [easy] What does this section explain?" in "\n" + out
    assert "quote not found" not in out  # verbatim quote
    body = seen[0]
    assert body["format"] == QuestionSet.model_json_schema()  # constrained decoding
    assert body["options"]["num_predict"] == 1536 and body["options"]["num_ctx"] == 4096


def test_fabricated_quote_is_flagged():
    code, out, _ = ask(section=1, transport=mock(
        [(_questions("Attention was invented by a committee of penguins in 1850."), "stop")]))
    assert code == OK and out.count("! quote not found verbatim in the section") == 5


def test_json_output_is_only_the_validated_json():
    sec = load_sections(NOTES)[0][0]
    code, out, err = ask(section=1, as_json=True, transport=mock(
        [(_questions(_first_sentence(sec.text)), "stop")]))
    assert code == OK and "Generating" in err and "tok/s" in err
    qs = QuestionSet.model_validate_json(out)  # stdout is pure JSON
    assert len(qs.questions) == 5 and out.isascii()


def test_retry_then_valid():
    sec = load_sections(NOTES)[0][0]
    code, out, _ = ask(section=1, transport=mock(
        [('{"questions": []}', "stop"), (_questions(_first_sentence(sec.text)), "stop")]))
    assert code == OK and "valid on attempt 2" in out


def test_all_attempts_invalid_explains_each_attempt():
    code, out, err = ask(section=1, transport=mock(
        [('{"questions": [', "length"), ("{}", "stop"), ("{}", "stop")]))
    assert code == GENERATION_FAILED and out == ""
    assert "no valid questions after 3 attempts" in err
    assert "attempt 1: hit the 1536-token output cap" in err
    assert "attempt 2:" in err and "attempt 3:" in err and "Traceback" not in err


# --- CLI ------------------------------------------------------------------------------

def test_cli_requires_list_or_section(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["ask", str(NOTES)])
    assert e.value.code == 2


def test_cli_survives_a_console_that_cannot_encode_the_notes(tmp_path, monkeypatch):
    p = tmp_path / "maths.md"
    p.write_text(f"# Maths\n\n## Scaling by √dₖ ≈ stable\n\n{_words(1300)}\n\n"
                 f"## Other\n\n{_words(200)}\n", encoding="utf-8")
    buf = io.BytesIO()
    strict_cp1252 = io.TextIOWrapper(buf, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", strict_cp1252)
    assert cli.main(["ask", str(p), "--list-sections"]) == OK
    strict_cp1252.flush()
    assert b"Scaling by" in buf.getvalue()
