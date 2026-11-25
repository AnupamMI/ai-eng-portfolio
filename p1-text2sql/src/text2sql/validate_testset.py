"""Validate the dev and test sets, and export the hand-check sheet.

    uv run python -m text2sql.validate_testset            # report -> testset/validation.md
    uv run python -m text2sql.validate_testset --sheet    # also testset/check_sheet.csv

Errors (exit 1) must be fixed before the set is frozen:
  R0  schema: Pydantic `Spec`, unique ids, split sizes (dev 5+5, test 25+25), no question text
      shared between dev and test.
  R1  every gold query runs on seeds 0 and 1 (read-only, time limit) and does not use the clock.
  R2  deterministic: a LIMIT needs an ORDER BY, `ordered` needs an ORDER BY, and the result is
      unchanged under PRAGMA reverse_unordered_selects (which exposes order-dependent ties).
  R3  empty only when `expect_empty` (and then empty on both seeds).
  R4  the readings of an ambiguous question give different results on seed 0 (in both comparison
      directions, with the lenient comparator used for scoring).
  R5  every question has a non-empty `note` (clear: why there is one reading; this part is a
      MANUAL check, done by the hand checker).
Warnings: readings identical on seed 1 (the ambiguity matters on seed 0 only), single-value answers
of 0 or NULL (weak tests: a wrong query can hit them by accident).
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

from text2sql.db import build
from text2sql.execute import ExecResult, compare, execute, guard
from text2sql.testset import AMBIGUITY_CATEGORIES, TESTSET_DIR, Question, load

SEEDS = (0, 1)
EXPECTED_SIZES = {"dev": (5, 5), "test": (25, 25)}  # (clear, ambiguous)
FILES = {"dev": "dev.jsonl", "test": "questions.jsonl"}


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    results: dict[tuple[str, str, int], ExecResult] = field(default_factory=dict)


def databases() -> dict[tuple[int, bool], sqlite3.Connection]:
    """(seed, reversed) -> guarded in-memory database."""
    out = {}
    for seed in SEEDS:
        for rev in (False, True):
            conn = build(sqlite3.connect(":memory:"), seed)
            if rev:
                conn.execute("PRAGMA reverse_unordered_selects = ON")
            out[(seed, rev)] = guard(conn)
    return out


def _same(a: ExecResult, b: ExecResult, ordered: bool) -> bool:
    return compare(a, b, ordered=ordered).match and compare(b, a, ordered=ordered).match


def _has(sql: str, word: str) -> bool:
    return re.search(rf"\b{word}\b", sql, re.I) is not None


_TIEBREAK = re.compile(r",\s*([\w.]+)(\s+(?:ASC|DESC))?\s+(LIMIT\s+\d+)\s*;?\s*$", re.I)


def flip_tiebreak(sql: str) -> str | None:
    """Reverse the direction of the last ORDER BY term before a final LIMIT (the tie-break).
    If the result changes, rows tied on the real sort key straddle the LIMIT boundary."""
    m = _TIEBREAK.search(sql)
    if not m:
        return None
    desc = (m.group(2) or "").strip().upper() == "DESC"
    return sql[:m.start()] + f", {m.group(1)} {'ASC' if desc else 'DESC'} {m.group(3)}"


def check(splits: dict[str, list[Question]], dbs) -> Report:
    rep = Report()
    E, W = rep.errors.append, rep.warnings.append

    all_ids = [q.id for qs in splits.values() for q in qs]
    if len(all_ids) != len(set(all_ids)):
        E("R0 question ids are not unique across dev and test")
    for name, qs in splits.items():
        want = EXPECTED_SIZES.get(name)
        got = (sum(q.label == "clear" for q in qs), sum(q.label == "ambiguous" for q in qs))
        if want and got != want:
            E(f"R0 {name}: {got[0]} clear + {got[1]} ambiguous, expected {want[0]} + {want[1]}")
    if "dev" in splits and "test" in splits:
        norm = lambda s: re.sub(r"\W+", " ", s.lower()).strip()
        shared = {norm(q.question) for q in splits["dev"]} & {norm(q.question) for q in splits["test"]}
        for s in shared:
            E(f"R0 question text in both dev and test: {s!r}")

    for qs in splits.values():
        for q in qs:
            if not q.spec.note.strip():
                E(f"R5 {q.id}: empty note")
            for it in q.spec.interpretations:
                key = f"{q.id}/{it.id}"
                sql = it.gold_sql
                if (_has(sql, "LIMIT") or it.ordered) and not re.search(r"\border\s+by\b", sql, re.I):
                    E(f"R2 {key}: LIMIT/ordered without ORDER BY")
                for seed in SEEDS:
                    r = execute(dbs[(seed, False)], sql)
                    rep.results[(q.id, it.id, seed)] = r
                    if not r.ok:
                        E(f"R1 {key} seed {seed}: {r.error_kind}: {r.error}")
                        continue
                    if r.uses_now:
                        E(f"R1 {key}: gold SQL uses the wall clock")
                    if r.truncated:
                        E(f"R1 {key} seed {seed}: result truncated")
                    rr = execute(dbs[(seed, True)], sql)
                    if rr.ok and not _same(r, rr, ordered=it.ordered or _has(sql, "LIMIT")):
                        E(f"R2 {key} seed {seed}: result depends on row order (ties?)")
                    if _has(sql, "LIMIT"):
                        flipped = flip_tiebreak(sql)
                        if flipped is None:
                            E(f"R2 {key}: a LIMIT query must end with ', <tie-break> LIMIT n'")
                        else:
                            rf = execute(dbs[(seed, False)], flipped)
                            if rf.ok and not _same(r, rf, ordered=it.ordered):
                                E(f"R2 {key} seed {seed}: tie at the LIMIT boundary "
                                  "(the answer depends on the tie-break)")
                    if bool(r.rows) == it.expect_empty:
                        E(f"R3 {key} seed {seed}: {len(r.rows)} rows, expect_empty={it.expect_empty}")
                    if len(r.rows) == 1 and len(r.columns) == 1 and r.rows[0][0] in (0, 0.0, None):
                        W(f"{key} seed {seed}: single value {r.rows[0][0]!r} (weak test)")

            if q.label == "ambiguous":
                its = q.spec.interpretations
                for seed in SEEDS:
                    for a in range(len(its)):
                        for b in range(a + 1, len(its)):
                            ra = rep.results[(q.id, its[a].id, seed)]
                            rb = rep.results[(q.id, its[b].id, seed)]
                            if not (ra.ok and rb.ok):
                                continue
                            # Score each reading against the other exactly as the benchmark
                            # would (the target reading's `ordered` flag decides row order).
                            if (compare(ra, rb, ordered=its[a].ordered).match
                                    or compare(rb, ra, ordered=its[b].ordered).match):
                                msg = f"{q.id}: readings {its[a].id} and {its[b].id} give the same result on seed {seed}"
                                (E if seed == 0 else W)(("R4 " if seed == 0 else "") + msg)
    return rep


AGG = re.compile(r"\b(count|sum|avg|min|max)\s*\(", re.I)
DATEF = re.compile(r"\b(strftime|date|julianday)\s*\(|\border_date\b|\bsignup_date\b|\bpayment_date\b", re.I)


def difficulty(qs: list[Question]) -> dict[str, float]:
    """Mean structural counts of the gold SQL per question (first reading for ambiguous ones,
    so each question counts once)."""
    sqls = [q.spec.interpretations[0].gold_sql for q in qs]
    if not sqls:
        return {}
    return {
        "joins": statistics.fmean(len(re.findall(r"\bjoin\b", s, re.I)) for s in sqls),
        "aggregates": statistics.fmean(len(AGG.findall(s)) for s in sqls),
        "subqueries/CTEs": statistics.fmean(len(re.findall(r"\(\s*select\b", s, re.I))
                                            + len(re.findall(r"\bwith\b", s, re.I)) for s in sqls),
        "uses dates": statistics.fmean(bool(DATEF.search(s)) for s in sqls),
        "GROUP BY": statistics.fmean(_has(s, "group") for s in sqls),
        "HAVING": statistics.fmean(_has(s, "having") for s in sqls),
        "chars": statistics.fmean(len(s) for s in sqls),
    }


def _preview(r: ExecResult, n: int = 5) -> str:
    if not r.ok:
        return f"ERROR {r.error_kind}: {r.error}"
    fmt = lambda v: f"{v:.2f}" if isinstance(v, float) else str(v)
    return " | ".join("(" + ", ".join(fmt(v) for v in row) + ")" for row in r.rows[:n])


def markdown(splits, rep: Report) -> str:
    L = ["# Test-set validation", "",
         f"**{len(rep.errors)} errors, {len(rep.warnings)} warnings.**", ""]
    if rep.errors:
        L += ["## Errors", ""] + [f"- {e}" for e in rep.errors] + [""]
    if rep.warnings:
        L += ["## Warnings", ""] + [f"- {w}" for w in rep.warnings] + [""]
    L += ["## Composition", "", "| split | clear | ambiguous | " +
          " | ".join(AMBIGUITY_CATEGORIES) + " | (question, reading) pairs |",
          "|---|---|---|" + "---|" * len(AMBIGUITY_CATEGORIES) + "---|"]
    for name, qs in splits.items():
        cats = [sum(q.spec.category == c for q in qs) for c in AMBIGUITY_CATEGORIES]
        L.append(f"| {name} | {sum(q.label == 'clear' for q in qs)} | "
                 f"{sum(q.label == 'ambiguous' for q in qs)} | " + " | ".join(map(str, cats)) +
                 f" | {sum(len(q.spec.interpretations) for q in qs)} |")
    L += ["", "## Gold SQL difficulty, clear vs ambiguous (test set, mean per question)", "",
          "Ambiguous questions use their first reading. The groups should differ in ambiguity,",
          "not in SQL difficulty.", ""]
    test = splits.get("test", [])
    dc = difficulty([q for q in test if q.label == "clear"])
    da = difficulty([q for q in test if q.label == "ambiguous"])
    if dc and da:
        L += ["| measure | clear | ambiguous |", "|---|---|---|"]
        L += [f"| {k} | {dc[k]:.2f} | {da[k]:.2f} |" for k in dc]
    L += ["", "## Results per reading (seed 0 rows / seed 1 rows)", "",
          "| id | reading | rows s0 | rows s1 | first rows (seed 0) |", "|---|---|---|---|---|"]
    for qs in splits.values():
        for q in qs:
            for it in q.spec.interpretations:
                r0 = rep.results.get((q.id, it.id, 0))
                r1 = rep.results.get((q.id, it.id, 1))
                if r0 and r1:
                    prev = _preview(r0, 3).replace("|", "/")
                    L.append(f"| {q.id} | {it.id} | {len(r0.rows)} | {len(r1.rows)} | {prev[:120]} |")
    return "\n".join(L) + "\n"


SHEET_COLUMNS = ["split", "id", "question", "label", "category", "note", "reading",
                 "description", "clarifying_answer", "gold_sql", "ordered", "rows_seed0",
                 "first_rows_seed0", "label_ok", "gold_ok", "notes"]


def write_sheet(splits, rep: Report, path: Path) -> None:
    # utf-8-sig: Excel reads accented names (e.g. "Müller") correctly only with a BOM.
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(SHEET_COLUMNS)
        for name, qs in splits.items():
            for q in qs:
                for it in q.spec.interpretations:
                    r0 = rep.results[(q.id, it.id, 0)]
                    w.writerow([name, q.id, q.question, q.label, q.spec.category, q.spec.note,
                                it.id, it.description, it.clarifying_answer or "", it.gold_sql,
                                it.ordered, len(r0.rows) if r0.ok else "ERROR", _preview(r0),
                                "", "", ""])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=TESTSET_DIR)
    ap.add_argument("--sheet", action="store_true", help="also write check_sheet.csv")
    a = ap.parse_args(argv)
    splits = {name: load(a.dir / fn) for name, fn in FILES.items() if (a.dir / fn).exists()}
    rep = check(splits, databases())
    (a.dir / "validation.md").write_text(markdown(splits, rep), encoding="utf-8")
    for e in rep.errors:
        print("ERROR", e)
    for w in rep.warnings:
        print("warn ", w)
    print(f"{len(rep.errors)} errors, {len(rep.warnings)} warnings -> {a.dir / 'validation.md'}")
    if a.sheet:
        if rep.errors:
            print("not writing the check sheet while there are errors")
        else:
            write_sheet(splits, rep, a.dir / "check_sheet.csv")
            print(f"check sheet -> {a.dir / 'check_sheet.csv'}")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
