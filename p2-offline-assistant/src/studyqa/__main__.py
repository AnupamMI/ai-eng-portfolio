"""python -m studyqa <command>. Commands: ask."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from studyqa.ask import DEFAULT_MODEL, DEFAULT_URL, run_ask


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m studyqa")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="revision questions for one section of a notes file",
                       description="Generate 5 structured revision questions for one section "
                                   "of a markdown notes file with a local Ollama model.")
    a.add_argument("notes", type=Path, help="markdown notes file (.md); PDF is not supported yet")
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--list-sections", action="store_true", help="print numbered section titles")
    g.add_argument("--section", type=int, metavar="N", help="section number from --list-sections")
    a.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Ollama model (default {DEFAULT_MODEL}: chosen for reliability, speed "
                        "and memory in the benchmark, not for question quality)")
    a.add_argument("--json", action="store_true", help="print the validated JSON only")
    a.add_argument("--url", default=DEFAULT_URL, help=f"Ollama URL (default {DEFAULT_URL})")
    args = ap.parse_args(argv)

    # A note with characters outside the console code page (e.g. cp1252) must not crash
    # printing after a minute of generation; --json output is ASCII-only anyway.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    return run_ask(args.notes, list_only=args.list_sections, section=args.section,
                   model=args.model, as_json=args.json, url=args.url)


if __name__ == "__main__":
    sys.exit(main())
