"""Split markdown notes into author-defined sections (no fixed-size chunking).

A section is the text under one heading. We split at the shallowest heading
level present; a section longer than `max_words` is split again at its own
subheadings, and sections shorter than `min_words` are dropped.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from evalkit import Case

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
MDN_MACRO = re.compile(r"\{\{\s*(\w+)(?:\((.*?)\))?\s*\}\}")  # args may contain "()"


class Section(BaseModel):
    id: str
    source: str  # path relative to the notes root
    title: str  # heading path, e.g. "Closures > Lexical scoping"
    text: str
    words: int
    sha: str  # content hash, so a changed note can't silently reuse old results


@dataclass
class _Node:
    level: int
    title: str
    body: list[str] = field(default_factory=list)  # lines before the first child
    children: list[_Node] = field(default_factory=list)

    def all_lines(self) -> list[str]:
        out = list(self.body)
        for c in self.children:
            out.append("#" * c.level + " " + c.title)
            out.extend(c.all_lines())
        return out


def word_count(text: str) -> int:
    return len(text.split())


def strip_mdn_macros(text: str) -> str:
    """{{HTTPHeader("Cache-Control")}} -> `Cache-Control`; {{Glossary("x", "y")}} -> y."""

    def repl(m: re.Match) -> str:
        args = re.findall(r'"([^"]*)"', m.group(2) or "")
        if not args:
            return ""  # {{Compat}}, {{Specifications}}, ...
        shown = args[1] if len(args) > 1 and args[1] else args[0]
        return shown if m.group(1).lower() == "glossary" else f"`{shown}`"

    return MDN_MACRO.sub(repl, text)


def _parse(text: str, doc_title: str) -> _Node:
    """Build a heading tree, ignoring '#' lines inside code fences."""
    root = _Node(level=0, title=doc_title)
    stack = [root]
    in_fence = False
    for line in text.splitlines():
        if FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence else HEADING.match(line)
        if m:
            node = _Node(level=len(m.group(1)), title=m.group(2).strip())
            while stack[-1].level >= node.level:
                stack.pop()
            stack[-1].children.append(node)
            stack.append(node)
        else:
            stack[-1].body.append(line)
    return root


def _emit(node: _Node, path: list[str], min_w: int, max_w: int) -> list[tuple[str, str]]:
    """Return (title_path, text) pairs for node, splitting if too long."""
    title = " > ".join(path)
    text = "\n".join(node.all_lines()).strip()
    if word_count(text) <= max_w or not node.children:
        return [(title, text)] if min_w <= word_count(text) <= max_w else []
    out = []
    intro = "\n".join(node.body).strip()
    if min_w <= word_count(intro) <= max_w:
        out.append((title, intro))
    for c in node.children:
        out.extend(_emit(c, path + [c.title], min_w, max_w))
    return out


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def split_markdown(text: str, source: str, *, min_words: int = 150, max_words: int = 1200,
                   mdn: bool = False) -> list[Section]:
    m = FRONT_MATTER.match(text)
    front, text = (m.group(0), text[m.end():]) if m else ("", text)
    t = re.search(r"^title:\s*(.+)$", front, re.M)
    doc_title = t.group(1).strip().strip("\"'") if t else Path(source).stem
    if mdn:
        text = strip_mdn_macros(text)

    pieces = _emit(_parse(text, doc_title), [doc_title], min_words, max_words)

    sections, seen = [], set()
    for title, body in pieces:
        sid = f"{_slug(Path(source).stem)}--{_slug(title.split(' > ')[-1])}"
        while sid in seen:  # repeated heading names within one file
            sid += "-x"
        seen.add(sid)
        sections.append(Section(id=sid, source=source, title=title, text=body,
                                words=word_count(body),
                                sha=hashlib.sha256(body.encode()).hexdigest()[:12]))
    return sections


def load_notes(root: str | Path, *, mdn: bool = False, **kw) -> list[Section]:
    root = Path(root)
    out: list[Section] = []
    for p in sorted(root.rglob("*.md")):
        if p.name.upper() in {"README.MD", "ATTRIBUTION.MD"}:
            continue
        out.extend(split_markdown(p.read_text(encoding="utf-8"), p.relative_to(root).as_posix(),
                                  mdn=mdn, **kw))
    return out


def select(sections: list[Section], n: int, *, seed: int = 0) -> list[Section]:
    """Pick n sections round-robin across source files, so no single long note dominates."""
    rng = random.Random(seed)
    by_source: dict[str, list[Section]] = {}
    for s in sections:
        by_source.setdefault(s.source, []).append(s)
    queues = [rng.sample(v, len(v)) for _, v in sorted(by_source.items())]
    rng.shuffle(queues)
    picked: list[Section] = []
    while len(picked) < n and any(queues):
        for q in queues:
            if q and len(picked) < n:
                picked.append(q.pop())
    if len(picked) < n:
        raise ValueError(f"only {len(picked)} eligible sections, wanted {n}")
    return picked


def to_cases(sections: list[Section]) -> list[Case]:
    return [Case(id=s.id, input=s.model_dump(), tags=[s.source]) for s in sections]
