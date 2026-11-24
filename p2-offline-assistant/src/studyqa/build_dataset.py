"""Freeze a section selection to JSONL so every model sees identical input.

    uv run python -m studyqa.build_dataset --notes sample_data/mdn --mdn --n 8 \
        --out data/smoke_public.jsonl
"""

from __future__ import annotations

import argparse
from pathlib import Path

from studyqa.sections import load_notes, select, to_cases


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

    secs = load_notes(args.notes, mdn=args.mdn, min_words=args.min_words,
                      max_words=args.max_words)
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
