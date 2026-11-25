"""Run model-written SQL safely, and compare result sets (not SQL text).

Safety is enforced by SQLite itself: a read-only URI connection, an authorizer that allows only
SELECT/READ/FUNCTION/RECURSIVE actions (so INSERT, DROP, ATTACH, PRAGMA ... are refused at
prepare time), a progress-handler deadline and a row cap.

Comparison (`compare`): rows are compared as multisets of normalised values (floats and ints
rounded to 2 decimals, NULL kept as NULL); column names are ignored and column order may be
permuted. The prediction may carry EXTRA columns: it matches if some ordered choice of its
columns reproduces the gold result. `Match.extra_columns` records when that leniency was used,
so a strict count can be reported too. Row order matters only when `ordered=True`.
"""

from __future__ import annotations

import re
import sqlite3
import time
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

TIMEOUT_S = 5.0
MAX_ROWS = 10_000

ErrorKind = Literal["syntax", "schema", "timeout", "denied", "multiple_statements", "runtime"]

_ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_RECURSIVE}


class ExecResult(BaseModel):
    ok: bool
    columns: list[str] = []
    rows: list[tuple] = []
    truncated: bool = False
    error: str | None = None
    error_kind: ErrorKind | None = None
    seconds: float = 0.0
    uses_now: bool = False  # model ignored the fixed "today" and used the wall clock


class Match(BaseModel):
    match: bool
    extra_columns: bool = False
    reason: str = ""


def _authorizer(action, *_):
    return sqlite3.SQLITE_OK if action in _ALLOWED else sqlite3.SQLITE_DENY


def connect_ro(path: Path) -> sqlite3.Connection:
    """Read-only connection with the authorizer installed."""
    conn = sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)
    conn.set_authorizer(_authorizer)
    return conn


def guard(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Install the authorizer on an existing connection (used for in-memory test databases)."""
    conn.set_authorizer(_authorizer)
    return conn


_NOW = re.compile(r"""['"]now['"]|\bcurrent_(date|timestamp|time)\b""", re.I)


def _kind(msg: str) -> ErrorKind:
    m = msg.lower()
    if "not authorized" in m:
        return "denied"
    if "interrupted" in m:
        return "timeout"
    if "one statement at a time" in m:
        return "multiple_statements"
    if "syntax error" in m or "incomplete input" in m or "unrecognized token" in m:
        return "syntax"
    if "no such table" in m or "no such column" in m or "ambiguous column" in m:
        return "schema"
    return "runtime"


def execute(conn: sqlite3.Connection, sql: str, *, timeout_s: float = TIMEOUT_S,
            max_rows: int = MAX_ROWS) -> ExecResult:
    sql = sql.strip().rstrip(";").strip()
    uses_now = bool(_NOW.search(sql))
    deadline = time.monotonic() + timeout_s
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
    t0 = time.perf_counter()
    try:
        cur = conn.execute(sql)
        rows = cur.fetchmany(max_rows + 1)
        columns = [d[0] for d in cur.description or []]
    except (sqlite3.Error, sqlite3.Warning) as e:
        return ExecResult(ok=False, error=str(e), error_kind=_kind(str(e)),
                          seconds=time.perf_counter() - t0, uses_now=uses_now)
    finally:
        conn.set_progress_handler(None, 0)
    return ExecResult(ok=True, columns=columns, rows=[tuple(r) for r in rows[:max_rows]],
                      truncated=len(rows) > max_rows, seconds=time.perf_counter() - t0,
                      uses_now=uses_now)


def _norm(v):
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return round(float(v), 2) + 0.0  # 1 == 1.0; -0.0 -> 0.0
    return v


def _column(rows: list[tuple], j: int) -> list:
    return [_norm(r[j]) for r in rows]


def _project(rows: list[tuple], cols: tuple[int, ...]) -> list[tuple]:
    return [tuple(_norm(r[j]) for j in cols) for r in rows]


def compare(gold: ExecResult, pred: ExecResult, *, ordered: bool = False) -> Match:
    if not gold.ok:
        raise ValueError(f"gold query failed: {gold.error}")
    if not pred.ok:
        return Match(match=False, reason=f"prediction failed ({pred.error_kind})")
    if pred.truncated or gold.truncated:
        return Match(match=False, reason="result truncated")
    if len(gold.rows) != len(pred.rows):
        return Match(match=False, reason=f"{len(pred.rows)} rows, expected {len(gold.rows)}")
    k = len(gold.columns)
    m = len(pred.columns)
    if m < k:
        return Match(match=False, reason=f"{m} columns, expected at least {k}")
    if not gold.rows:  # both empty
        return Match(match=True, extra_columns=m > k)

    # Candidate prediction columns for each gold column: same multiset (or sequence) of values.
    def sig(col: list):
        return col if ordered else sorted(col, key=repr)

    gold_sigs = [sig(_column(gold.rows, j)) for j in range(k)]
    pred_sigs = [sig(_column(pred.rows, j)) for j in range(m)]
    cands = [[p for p in range(m) if pred_sigs[p] == g] for g in gold_sigs]
    if any(not c for c in cands):
        return Match(match=False, reason="no column with the expected values")
    target = _project(gold.rows, tuple(range(k)))
    target_key = target if ordered else Counter(target)

    def search(i: int, used: tuple[int, ...]) -> bool:
        if i == k:
            got = _project(pred.rows, used)
            return (got if ordered else Counter(got)) == target_key
        return any(search(i + 1, used + (p,)) for p in cands[i] if p not in used)

    if search(0, ()):
        return Match(match=True, extra_columns=m > k)
    return Match(match=False, reason="same columns individually, rows differ")
