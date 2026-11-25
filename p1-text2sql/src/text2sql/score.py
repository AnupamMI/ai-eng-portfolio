"""Score one predicted query against one gold reading, on both seeds.

- lenient (headline): the prediction's results match the gold results on BOTH seeds. Extra
  columns are allowed (`compare` finds the gold columns inside the prediction).
- strict (Spider-style): lenient, and no extra columns on either seed.

Failure types. These are assigned automatically only where the evidence is mechanical;
everything else is `unclassified` until it is labelled by reading the SQL
(`results/<run>/failure_labels.csv`):
  empty     no valid SQL produced (invalid JSON after the retry, or an empty string)
  timeout   generation timed out, or the query hit the execution deadline
  syntax    SQLite could not parse the query
  schema    a table or column that does not exist
  shape     ran, but with fewer columns than asked for (a different row count is not
            labelled automatically: it can be a wrong filter as well as a wrong granularity)
  other     refused (write/PRAGMA), multiple statements, runtime errors, infra errors
Hand labels: filter, date (including off-by-one-day windows), aggregate, join, shape, other.
"""

from __future__ import annotations

import sqlite3

from text2sql.execute import ExecResult, compare, execute
from text2sql.testset import Interpretation

AUTO_TYPES = ("empty", "timeout", "syntax", "schema", "shape", "other")
HAND_TYPES = ("filter", "date", "aggregate", "join", "shape", "other")
FAILURE_TYPES = ("syntax", "schema", "filter", "date", "aggregate", "join", "shape", "timeout",
                 "empty", "other")


def _brief(r: ExecResult, n: int = 3) -> dict:
    if not r.ok:
        return {"ok": False, "error_kind": r.error_kind, "error": r.error}
    return {"ok": True, "n_rows": len(r.rows), "n_cols": len(r.columns),
            "first_rows": [list(x) for x in r.rows[:n]], "uses_now": r.uses_now}


def score(it: Interpretation, sql: str | None, dbs: dict[tuple[int, bool], sqlite3.Connection],
          gold: dict[int, ExecResult] | None = None, *, gen_error: str | None = None) -> dict:
    """`dbs` maps (seed, reversed) -> guarded connection, as `validate_testset.databases()`.
    Returns {"lenient", "strict", "auto_type", "seeds": {seed: {...}}}."""
    seeds = sorted({s for s, _ in dbs})
    gold = gold or {s: execute(dbs[(s, False)], it.gold_sql) for s in seeds}
    if sql is None:
        t = "timeout" if gen_error and "timeout" in gen_error.lower() else (
            "other" if gen_error else "empty")
        return {"lenient": 0.0, "strict": 0.0, "auto_type": t, "seeds": {}}
    per, matches = {}, []
    for s in seeds:
        p = execute(dbs[(s, False)], sql)
        m = compare(gold[s], p, ordered=it.ordered)
        matches.append(m)
        per[s] = {"match": m.match, "extra_columns": m.extra_columns, "reason": m.reason,
                  "pred": _brief(p), "gold": _brief(gold[s])}
    lenient = all(m.match for m in matches)
    strict = lenient and not any(m.extra_columns for m in matches)
    return {"lenient": float(lenient), "strict": float(strict),
            "auto_type": None if lenient else _auto_type(per), "seeds": per}


def _auto_type(per: dict) -> str:
    # Use the first seed that failed; the error kind is the same on both seeds for a broken query.
    d = next(v for v in per.values() if not v["match"])
    p, g = d["pred"], d["gold"]
    if not p["ok"]:
        return {"syntax": "syntax", "schema": "schema", "timeout": "timeout"}.get(
            p["error_kind"], "other")
    if p["n_cols"] < g["n_cols"]:
        return "shape"  # a different row count can be a filter error too: left to the hand label
    return "unclassified"
