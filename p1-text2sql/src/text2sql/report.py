"""Stage 2 report from stored results (no model calls).

    uv run python -m text2sql.report results/stage2                  # -> results/stage2/report.md
    uv run python -m text2sql.report results/stage2 --labels-template # add unlabelled failures

CIs: 95% percentile bootstrap resampling questions. Each clear question has exactly one reading,
so the cluster bootstrap by question (evalkit.cluster_bootstrap) reduces to this plain bootstrap
over questions. Dev and test are reported separately; the gate uses test only.

Failure types: the automatic type from score.py, replaced by the hand label in
failure_labels.csv where one exists. A failure is a lenient miss; extra columns that fail only the
strict score are counted separately, not as failures.
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import Counter
from pathlib import Path

from evalkit import Result, bootstrap_ci, load_results, paired_bootstrap
from text2sql.freeze import ROOT
from text2sql.score import FAILURE_TYPES
from text2sql.testset import TESTSET_DIR, load
from text2sql.validate_testset import FILES

GATE = 0.50  # pre-registered, docs/LOG.md 2026-11-25; lenient, test split, point estimate
LABEL_COLUMNS = ["model", "case_id", "type", "note", "question", "gold_sql", "pred_sql",
                 "reason_seed0", "pred_rows_seed0", "gold_rows_seed0"]


def load_runs(d: Path) -> dict[str, list[Result]]:
    runs = {}
    for p in sorted(d.glob("*.jsonl")):
        rs = load_results(p)
        if rs:
            runs[rs[0].meta["model"]] = rs
    return runs


def load_labels(d: Path) -> dict[tuple[str, str], dict]:
    p = d / "failure_labels.csv"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8-sig", newline="") as f:
        return {(r["model"], r["case_id"]): r for r in csv.DictReader(f) if r.get("type")}


def failure_type(r: Result, labels) -> str:
    lab = labels.get((r.meta["model"], r.case_id))
    if lab:
        return lab["type"]
    return r.meta.get("auto_type") or "unclassified"


def _non_decode_s(r: Result) -> float:
    m = r.meta
    if m.get("prompt_eval_duration_s"):
        return sum(m["prompt_eval_duration_s"])
    decode = sum(e / t for e, t in zip(m["eval_count"], m["tok_s"]) if t)
    return max(0.0, r.latency_s - decode)


def _ci(xs: list[float]) -> tuple[float, float, float]:
    if not xs:
        return float("nan"), float("nan"), float("nan")
    lo, hi, _ = bootstrap_ci(xs, statistics.fmean)
    return statistics.fmean(xs), lo, hi


def _fmt(t) -> str:
    m, lo, hi = t
    return f"{m:.2f} [{lo:.2f}, {hi:.2f}]"


def model_rows(runs, labels) -> list[dict]:
    rows = []
    for model, rs in runs.items():
        by = {s: [r for r in rs if r.meta["split"] == s] for s in ("test", "dev")}
        t, d = by["test"], by["dev"]
        lat = [r.latency_s for r in t + d]
        tps = [r.meta["tok_s"][0] for r in t + d if r.meta["tok_s"] and r.meta["tok_s"][0]]
        # Time not spent decoding (prompt processing + overhead). Ollama's prompt_eval_count
        # reports the whole prompt even when its prefix cache is reused (docs/LOG.md), so the
        # cache is judged from time, not from that count.
        pe = [_non_decode_s(r) for r in t + d]
        ran = [r for r in t if r.output.get("sql") is not None]
        exec_fail = sum(1 for r in ran
                        if not all(v["pred"]["ok"] for v in r.meta["seeds"].values()))
        rows.append({
            "model": model, "n_test": len(t), "n_dev": len(d),
            "test_lenient": _ci([r.scores["lenient"] for r in t]),
            "test_strict": _ci([r.scores["strict"] for r in t]),
            "dev_lenient": statistics.fmean([r.scores["lenient"] for r in d]) if d else float("nan"),
            "dev_strict": statistics.fmean([r.scores["strict"] for r in d]) if d else float("nan"),
            "valid_first_try": statistics.fmean([r.scores["valid_first_try"] for r in t + d]),
            "exec_fail_test": exec_fail,
            "infra_errors": sum(r.error is not None for r in t + d),
            "lat_p50": statistics.median(lat) if lat else float("nan"),
            "tps_p50": statistics.median(tps) if tps else float("nan"),
            "prompt_p50": statistics.median(pe) if pe else float("nan"),
            "failures": Counter(failure_type(r, labels) for r in t + d
                                if not r.scores["lenient"]),
            "failures_test": Counter(failure_type(r, labels) for r in t
                                     if not r.scores["lenient"]),
            "extra_only": sum(bool(r.scores["lenient"] and not r.scores["strict"]) for r in t + d),
        })
    return rows


def paired(runs) -> list[str]:
    """Paired differences in test lenient accuracy, every model vs every other (same questions)."""
    models = list(runs)
    if len(models) < 2:
        return []
    sc = {m: {r.case_id: r.scores["lenient"] for r in runs[m] if r.meta["split"] == "test"}
          for m in models}
    L = ["", "## Paired differences, test lenient (row minus column; 95% CI, bootstrap over "
         "questions)", "", "| | " + " | ".join(models) + " |", "|---|" + "---|" * len(models)]
    for a in models:
        cells = []
        for b in models:
            if a == b:
                cells.append("")
                continue
            ids = sorted(set(sc[a]) & set(sc[b]))
            before, after = [sc[b][i] for i in ids], [sc[a][i] for i in ids]
            lo, hi = paired_bootstrap(before, after)
            d = statistics.fmean(after) - statistics.fmean(before)
            cells.append(f"{d:+.2f} [{lo:+.2f}, {hi:+.2f}]")
        L.append(f"| {a} | " + " | ".join(cells) + " |")
    return L


def markdown(runs, labels) -> str:
    rows = model_rows(runs, labels)
    L = ["# Stage 2: plain SQL accuracy on the clear questions", "",
         f"Gate (pre-registered): test lenient >= {GATE:.2f}, point estimate. 95% CIs: bootstrap "
         "over questions (one reading per clear question, so this is the cluster bootstrap by "
         "question). Correct = same results as the gold SQL on both seeds.", "",
         "| model | test lenient (n) | test strict | gate | dev lenient / strict (n) | valid 1st try "
         "| test queries that fail to run | infra errors | latency p50 | tok/s p50 | non-decode time p50 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        gate = "pass" if r["test_lenient"][0] >= GATE else "FAIL"
        L.append(f"| {r['model']} | {_fmt(r['test_lenient'])} ({r['n_test']}) | "
                 f"{_fmt(r['test_strict'])} | {gate} | {r['dev_lenient']:.2f} / {r['dev_strict']:.2f}"
                 f" ({r['n_dev']}) | {r['valid_first_try']:.2f} | {r['exec_fail_test']} | "
                 f"{r['infra_errors']} | {r['lat_p50']:.1f} s | {r['tps_p50']:.1f} | "
                 f"{r['prompt_p50']:.1f} s |")
    L += paired(runs)
    types = list(FAILURE_TYPES) + ["unclassified"]
    L += ["", "## Failure types (lenient misses, test + dev; test only in brackets)", "",
          "| model | " + " | ".join(types) + " | total | extra columns only (strict miss) |",
          "|---|" + "---|" * (len(types) + 2)]
    for r in rows:
        f, ft = r["failures"], r["failures_test"]
        L.append(f"| {r['model']} | " + " | ".join(
            f"{f[t]} ({ft[t]})" if f[t] else "" for t in types)
            + f" | {sum(f.values())} ({sum(ft.values())}) | {r['extra_only']} |")
    qtext = {q.id: q for fn in FILES.values() for q in load(TESTSET_DIR / fn)}
    L += ["", "## Every failure", ""]
    for model, rs in runs.items():
        fails = [r for r in rs if not r.scores["lenient"]]
        L += [f"### {model} ({len(fails)})", ""]
        for r in fails:
            q = qtext[r.meta["qid"]]
            lab = labels.get((model, r.case_id), {})
            s0 = r.meta["seeds"].get("0", {})
            L += [f"- **{r.case_id}** `{failure_type(r, labels)}`: {q.question}"
                  + (f"  \n  note: {lab['note']}" if lab.get("note") else ""),
                  f"  - gold: `{q.spec.interpretations[0].gold_sql}`",
                  f"  - pred: `{r.output.get('sql')}`" + (f" (error: {r.error})" if r.error else ""),
                  f"  - seed 0: {s0.get('reason', '-')}", ""]
    return "\n".join(L) + "\n"


def labels_template(d: Path, runs) -> int:
    """Append unlabelled failures to failure_labels.csv (existing rows are kept as they are)."""
    p = d / "failure_labels.csv"
    existing = []
    if p.exists():
        with open(p, encoding="utf-8-sig", newline="") as f:
            existing = list(csv.DictReader(f))
    have = {(r["model"], r["case_id"]) for r in existing}
    qtext = {q.id: q for fn in FILES.values() for q in load(TESTSET_DIR / fn)}
    new = []
    for model, rs in runs.items():
        for r in rs:
            if r.scores["lenient"] or (model, r.case_id) in have:
                continue
            q = qtext[r.meta["qid"]]
            s0 = r.meta["seeds"].get("0", {})
            auto = r.meta.get("auto_type")
            new.append({"model": model, "case_id": r.case_id,
                        "type": "" if auto in (None, "unclassified") else auto, "note": "",
                        "question": q.question, "gold_sql": q.spec.interpretations[0].gold_sql,
                        "pred_sql": r.output.get("sql") or "", "reason_seed0": s0.get("reason", ""),
                        "pred_rows_seed0": str(s0.get("pred", {}).get("first_rows", ""))[:200],
                        "gold_rows_seed0": str(s0.get("gold", {}).get("first_rows", ""))[:200]})
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_COLUMNS)
        w.writeheader()
        w.writerows(existing + new)
    return len(new)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", nargs="?", default="results/stage2")
    ap.add_argument("--labels-template", action="store_true")
    a = ap.parse_args(argv)
    d = Path(a.dir)
    if not d.is_absolute():
        d = ROOT / d
    runs = load_runs(d)
    if a.labels_template:
        print(f"{labels_template(d, runs)} unlabelled failures added -> {d / 'failure_labels.csv'}")
    (d / "report.md").write_text(markdown(runs, load_labels(d)), encoding="utf-8")
    print(f"report -> {d / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
