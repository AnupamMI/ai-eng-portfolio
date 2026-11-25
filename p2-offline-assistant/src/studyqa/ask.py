"""`python -m studyqa ask`: revision questions for one section of a markdown notes file.

Uses exactly the benchmarked path: the same splitter, prompt, schema, schema-constrained
decoding, retry loop and output cap (generate.NUM_*). Default model qwen2.5:3b is a
reliability/speed/memory choice from the benchmark (1.00 first-try validity in both
modes, highest tok/s, lowest RAM), not a claim that it writes the best questions.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import TextIO

import httpx

from evalkit import Ollama
from studyqa.generate import NUM_CTX, NUM_PREDICT, RETRIES, Generation, generate
from studyqa.grounding import quote_fidelity
from studyqa.sections import Drop, Section, split_markdown

DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_URL = "http://localhost:11434"
QUOTE_TAU = 0.85  # frozen tau_quote (docs/LOG.md)
TIMEOUT_S = 600  # one capped attempt is ~3 min on this CPU; 3 attempts must fit

# Exit codes
OK, GENERATION_FAILED, USAGE, OLLAMA = 0, 1, 2, 3

SKIP_REASON = {"too_short": "too short (<150 words)",
               "too_long_no_subheadings": "too long (>1200 words, no subheadings to split at)"}


class AskError(Exception):
    def __init__(self, message: str, code: int):
        super().__init__(message)
        self.code = code


def load_sections(path: Path) -> tuple[list[Section], list[Drop]]:
    if path.suffix.lower() == ".pdf":
        raise AskError("PDF is not supported yet: no PDF parser is installed (the project adds "
                       "no new dependencies). Convert the PDF to a .md file first.", USAGE)
    if not path.exists():
        raise AskError(f"file not found: {path}", USAGE)
    if path.is_dir():
        raise AskError(f"{path} is a directory; give one .md notes file", USAGE)
    if path.suffix.lower() not in {".md", ".markdown"}:
        raise AskError(f"unsupported file type '{path.suffix or '(none)'}': give a markdown "
                       "(.md) notes file", USAGE)
    drops: list[Drop] = []
    # utf-8-sig: a BOM (Notepad, PowerShell) would otherwise hide YAML front matter
    secs = split_markdown(path.read_text(encoding="utf-8-sig"), path.name, drops=drops)
    return secs, [d for d in drops if d.reason in SKIP_REASON]


def _short_title(s: Section) -> str:
    parts = s.title.split(" > ")
    return " > ".join(parts[1:]) if len(parts) > 1 else parts[0]


def list_sections(secs: list[Section], skipped: list[Drop], out: TextIO) -> None:
    for i, s in enumerate(secs, 1):
        out.write(f"{i:>3}. {_short_title(s)} ({s.words} words)\n")
    if skipped:
        out.write(f"\nSkipped (not available with --section): {len(skipped)}\n")
        for d in skipped:
            out.write(f"     - {d.title.split(' > ')[-1]} ({d.words} words): "
                      f"{SKIP_REASON[d.reason]}\n")


def _norm(model: str) -> str:
    return model if ":" in model else model + ":latest"


def preflight(url: str, model: str, transport: httpx.BaseTransport | None = None) -> None:
    """Fail fast, with an actionable message, if Ollama is down or the model is missing."""
    try:
        with httpx.Client(base_url=url, timeout=10, transport=transport) as c:
            resp = c.get("/api/tags")
            resp.raise_for_status()
    except httpx.ConnectError:
        raise AskError(f"Ollama is not running at {url}. Start it (open the Ollama app, or run "
                       "`ollama serve`) and try again.", OLLAMA) from None
    except httpx.HTTPError as e:
        raise AskError(f"Ollama at {url} did not answer /api/tags: {e}", OLLAMA) from None
    pulled = {_norm(m.get("name") or m.get("model", "")) for m in resp.json().get("models", [])}
    if _norm(model) not in pulled:
        have = ", ".join(sorted(pulled)) or "none"
        raise AskError(f"model '{model}' is not pulled. Run: ollama pull {model}\n"
                       f"       pulled models: {have}", OLLAMA)


def _attempt_lines(g: Generation) -> list[str]:
    lines = []
    for i, (resp, err) in enumerate(zip(g.responses, g.errors), 1):
        if resp.hit_length:
            lines.append(f"  attempt {i}: hit the {NUM_PREDICT}-token output cap "
                         "(the model kept generating without finishing the JSON)")
        else:
            first = err.strip().splitlines()[0] if err.strip() else "invalid output"
            lines.append(f"  attempt {i}: {first[:200]}")
    return lines


def format_questions(g: Generation, sec: Section, n: int, total: int, model: str,
                     seconds: float) -> str:
    lines = [f"Section {n}/{total}: {_short_title(sec)} ({sec.words} words)",
             f"Model {model}, constrained decoding, valid on attempt {g.attempts}, "
             f"{seconds:.0f} s", ""]
    for i, q in enumerate(g.questions.questions, 1):
        lines += [f"{i}. [{q.difficulty}] {q.question}",
                  f"   Answer: {q.answer}",
                  f'   Source: "{q.source_quote}"']
        fid = quote_fidelity(q.source_quote, sec.text)
        if fid < QUOTE_TAU:
            lines.append(f"   ! quote not found verbatim in the section (best match {fid:.2f})")
        lines.append("")
    return "\n".join(lines)


def run_ask(path: Path, *, list_only: bool, section: int | None, model: str, as_json: bool,
            url: str = DEFAULT_URL, transport: httpx.BaseTransport | None = None,
            out: TextIO | None = None, err: TextIO | None = None) -> int:
    out = out or sys.stdout  # resolved per call, not at import, so redirection works
    err = err or sys.stderr
    try:
        secs, skipped = load_sections(path)
        if not secs:
            raise AskError(f"no usable sections in {path}: sections must be 150-1200 words "
                           "(split at ## headings if longer)" +
                           (f"; {len(skipped)} skipped, see --list-sections" if skipped else ""),
                           USAGE)
        if list_only:
            list_sections(secs, skipped, out)
            return OK
        if section is None:
            raise AskError("give --section N (see --list-sections) or --list-sections", USAGE)
        if not 1 <= section <= len(secs):
            raise AskError(f"section {section} is out of range: {path.name} has "
                           f"{len(secs)} usable section(s), numbered 1-{len(secs)} "
                           "(see --list-sections)", USAGE)
        sec = secs[section - 1]
        preflight(url, model, transport)
        err.write(f"Generating 5 questions for section {section} with {model} "
                  "(about a minute on CPU)...\n")
        err.flush()
        llm = Ollama(model, url=url, num_ctx=NUM_CTX, num_predict=NUM_PREDICT,
                     timeout=TIMEOUT_S, transport=transport)
        t0 = time.perf_counter()
        try:
            g = generate(llm, sec.model_dump(), constrained=True, retries=RETRIES)
        except httpx.TimeoutException:
            raise AskError(f"Ollama did not answer within {TIMEOUT_S} s", OLLAMA) from None
        except httpx.HTTPError as e:
            raise AskError(f"Ollama request failed: {e}", OLLAMA) from None
        seconds = time.perf_counter() - t0
        if not g.valid:
            err.write(f"error: {model} produced no valid questions after {g.attempts} "
                      "attempts:\n" + "\n".join(_attempt_lines(g)) + "\n"
                      "Try again, or another model with --model.\n")
            return GENERATION_FAILED
        if as_json:
            out.write(json.dumps(g.questions.model_dump(mode="json"), indent=2,
                                 ensure_ascii=True) + "\n")
        else:
            out.write(format_questions(g, sec, section, len(secs), model, seconds))
        return OK
    except AskError as e:
        err.write(f"error: {e}\n")
        return e.code
