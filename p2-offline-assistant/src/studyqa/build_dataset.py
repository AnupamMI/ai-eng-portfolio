"""Freeze a section selection to JSONL so every model sees identical input.

    uv run python -m studyqa.build_dataset --notes sample_data/mdn --mdn --n 8 \
        --out data/smoke_public.jsonl
"""

from __future__ import annotations

import argparse
from pathlib import Path

from collections import Counter

from studyqa.sections import Drop, Section, load_notes, select, to_cases


def split_report(secs: list[Section], drops: list[Drop]) -> str:
    """Kept vs filtered counts, with reasons. Empty container headings (a title
    whose text lives entirely in its subsections) hold no text, so they are
    listed but not counted as filtered content."""
    real = [d for d in drops if d.reason != "empty_container"]
    lines = [f"kept {len(secs)} sections from {len({s.source for s in secs})} files; "
             f"filtered {len(real)} "
             f"({', '.join(f'{r}={n}' for r, n in Counter(d.reason for d in real).items()) or 'none'}); "
             f"{len(drops) - len(real)} empty container headings"]
    for d in drops:
        lines.append(f"  drop [{d.reason}] {d.source}: {d.title} ({d.words}w)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--notes", required=True, type=Path)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--mdn", action="store_true", help="strip MDN {{macros}}")
    ap.add_argument("--min-words", type=int, default=150)
    ap.add_argument("--max-words", type=int, default=1200)
    args = ap.parse_args(argv)

    drops: list[Drop] = []
    secs = load_notes(args.notes, mdn=args.mdn, min_words=args.min_words,
                      max_words=args.max_words, drops=drops)
    print(split_report(secs, drops))
    picked = select(secs, args.n, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for c in to_cases(picked):
            f.write(c.model_dump_json() + "\n")
    print(f"{len(secs)} eligible sections; wrote {len(picked)} to {args.out}")
    for s in picked:
        print(f"  {s.id}  ({s.words}w)")


if __name__ == "__main__":
    main()
