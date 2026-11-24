"""Lexical groundedness. Raw scores are stored per question; thresholds are applied
at report time so they can be calibrated and swept without re-running models.

- quote_fidelity: does source_quote actually appear in the section? 1.0 if its
  tokens occur contiguously; else best difflib ratio over same-length windows.
- answer_support: share of the answer's content words found in source_quote.
- section_support: same, against the whole section (diagnostic: separates
  "right answer, wrong quote" from "made-up answer").
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from pydantic import BaseModel

from studyqa.schema import QuestionSet

STOPWORDS = frozenset("""
a about above after again all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further
had has have having he her here hers him his how i if in into is it its itself just me more
most my no nor not now of off on once only or other our out over own same she should so some
such than that the their them then there these they this those through to too under until up
very was we were what when where which while who whom why will with would you your yours
""".split())

TOKEN = re.compile(r"[a-z0-9]+")
MD_LINK = re.compile(r"\[([^\]]*)\]\([^)\s]*(?:\s+\"[^\"]*\")?\)")  # [text](url "title")
URL = re.compile(r"<?https?://[^\s>)]+>?")


def strip_links(text: str) -> str:
    """Keep link text, drop link targets and bare URLs. Without this a verbatim
    quote of '[`WeakRef`](/en-US/docs/...)' text scores < 1 against a source whose
    URL tokens the model did not copy (or vice versa)."""
    return URL.sub(" ", MD_LINK.sub(r"\1", text))


def tokens(text: str) -> list[str]:
    return TOKEN.findall(strip_links(text).lower())


def _stem(t: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def content_words(text: str) -> set[str]:
    return {_stem(t) for t in tokens(text) if t not in STOPWORDS}


def quote_fidelity(quote: str, section: str) -> float:
    q, s = tokens(quote), tokens(section)
    if not q or not s:
        return 0.0
    if f" {' '.join(q)} " in f" {' '.join(s)} ":
        return 1.0
    n = len(q)
    best = 0.0
    for i in range(max(1, len(s) - n + 1)):
        best = max(best, SequenceMatcher(None, q, s[i:i + n], autojunk=False).ratio())
        if best == 1.0:
            break
    return best


def support(answer: str, reference: str) -> float:
    a = content_words(answer)
    if not a:
        return 0.0
    return len(a & content_words(reference)) / len(a)


class QuestionGrounding(BaseModel):
    quote_fidelity: float
    answer_support: float
    section_support: float

    def grounded(self, tau_quote: float, tau_answer: float) -> bool:
        return self.quote_fidelity >= tau_quote and self.answer_support >= tau_answer


def ground(qs: QuestionSet, section_text: str) -> list[QuestionGrounding]:
    return [
        QuestionGrounding(
            quote_fidelity=quote_fidelity(q.source_quote, section_text),
            answer_support=support(q.answer, q.source_quote),
            section_support=support(q.answer, section_text),
        )
        for q in qs.questions
    ]
