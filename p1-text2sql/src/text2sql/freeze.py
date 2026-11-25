"""Frozen files and their git blob hashes (docs/LOG.md, 2026-11-26 FREEZE entry).

The benchmark refuses to run if any of these files differs from its frozen version, so the rule "no
frozen file changes during measurement" is checked rather than promised. A deliberate change
needs a LOG entry and new hashes here (and in LOG.md).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # p1-text2sql/

FROZEN = {
    "testset/questions.jsonl": "bc0274de052e9fe10c8a25a14130019804438499",
    "testset/dev.jsonl": "fd02051206a4257bb03ff35f4a5ae1a8a7cb42dd",
    "src/text2sql/prompt.py": "1f34cf2ec86c896f59d2edaf9bee5edaef4f967a",
    "src/text2sql/db.py": "c089cdca8c18843b1878d9d8d5be52b62414464c",
    "src/text2sql/execute.py": "5a6811b7098e7263adee72ebb8a09fe683a00a05",
}


def blob(path: Path) -> str:
    # `git hash-object` applies the repo's line-ending normalisation, like `git add` would.
    return subprocess.run(["git", "hash-object", str(path)], capture_output=True, text=True,
                          check=True, cwd=ROOT).stdout.strip()


def changed() -> list[str]:
    """Frozen files whose working-copy blob differs from the frozen hash."""
    return [rel for rel, h in FROZEN.items() if blob(ROOT / rel) != h]
