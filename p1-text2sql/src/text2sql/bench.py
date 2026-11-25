"""Stage 2: plain SQL accuracy on the clear questions (dev and test), one model at a time.

    uv run python -m text2sql.bench --out results/stage2

Run protocol (lessons from p2's LOG):
- refuses to start if a frozen file differs from its hash (text2sql.freeze)
- one model loaded at a time: everything resident is unloaded before each model and after it
- a warm-up call per model absorbs the load time and fills Ollama's prompt cache with the
  system prefix; it is not scored
- num_predict cap, HTTP timeout, and a stack dump if one question runs past --stall-dump-s
- a `start` line before every question and a result line after it, written to log.txt first and
  then to the console (in p2 a paused console blocked the run before the file got the line)
- every result is appended to <out>/<model>.jsonl as soon as it exists, so a killed run resumes
  where it stopped: questions already in the file are skipped
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import platform
import statistics
import subprocess
from pathlib import Path

import httpx
import psutil

from evalkit import Case, Ollama, Result, run, stall_dump
from text2sql.execute import execute
from text2sql.freeze import FROZEN, ROOT, changed
from text2sql.generate import NUM_CTX, NUM_PREDICT, RETRIES, generate_sql
from text2sql.prompt import sql_messages
from text2sql.score import score
from text2sql.testset import TESTSET_DIR, Question, load
from text2sql.validate_testset import FILES, databases

MODELS = ["qwen2.5:3b", "llama3.2:3b", "qwen2.5-coder:3b", "qwen2.5-coder:7b"]
SPLITS = ["dev", "test"]


def model_slug(model: str) -> str:
    return model.replace(":", "-").replace("/", "-")


def clear_questions(splits: list[str]) -> list[tuple[str, Question]]:
    return [(s, q) for s in splits for q in load(TESTSET_DIR / FILES[s]) if q.label == "clear"]


def done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return {json.loads(line)["case_id"] for line in f if line.strip()}


def drop_errors(path: Path) -> int:
    """Remove infra-error results (HTTP failures, timeouts) so a resume retries them."""
    if not path.exists():
        return 0
    lines = path.read_text(encoding="utf-8").splitlines()
    keep = [x for x in lines if x.strip() and json.loads(x).get("error") is None]
    path.write_text("".join(x + "\n" for x in keep), encoding="utf-8")
    return len(lines) - len(keep)


def loaded_models(url: str) -> list[str]:
    return [m["name"] for m in httpx.get(f"{url}/api/ps", timeout=10).json().get("models", [])]


def pulled_models(url: str) -> set[str]:
    return {m["name"] for m in httpx.get(f"{url}/api/tags", timeout=10).json().get("models", [])}


def run_question(llm: Ollama, split: str, q: Question, dbs, gold) -> Result:
    case = Case(id=f"{split}/{q.id}", input=q.question)
    (r,) = run(lambda question: generate_sql(llm, question), [case], {})
    out = r.output or {}
    it = q.spec.interpretations[0]
    s = score(it, out.get("sql"), dbs, gold, gen_error=r.error)
    resp = out.get("responses", [])
    r.scores = {"lenient": s["lenient"], "strict": s["strict"],
                "valid": float(out.get("sql") is not None),
                "valid_first_try": float(bool(out.get("first_try_valid")))}
    r.output = {k: out.get(k) for k in ("sql", "attempts", "first_try_valid", "errors")}
    r.meta = {
        "split": split, "qid": q.id, "model": llm.model, "auto_type": s["auto_type"],
        "seeds": {str(k): v for k, v in s["seeds"].items()},
        "prompt_eval_count": [x["prompt_eval_count"] for x in resp],
        "prompt_eval_duration_s": [x["prompt_eval_duration_s"] for x in resp],
        "eval_count": [x["eval_count"] for x in resp],
        "tok_s": [round(x["eval_count"] / x["eval_duration_s"], 1) if x["eval_duration_s"] else 0
                  for x in resp],
        "done_reason": [x["done_reason"] for x in resp],
    }
    return r


def _sh(*cmd) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=ROOT
                              ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def bench(args) -> int:
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    log_file = open(out / "log.txt", "a", encoding="utf-8")

    def log(msg: str) -> None:  # file first, then console (see module docstring)
        log_file.write(msg + "\n")
        log_file.flush()
        print(msg, flush=True)

    bad = changed()
    if bad:
        log(f"REFUSING TO RUN: frozen files changed: {bad} (see text2sql/freeze.py)")
        return 2
    missing = [m for m in args.models if m not in pulled_models(args.url)]
    if missing:
        log(f"REFUSING TO RUN: models not pulled: {missing}")
        return 2

    meta_path = out / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"sessions": []}
    try:
        version = httpx.get(f"{args.url}/api/version", timeout=5).json().get("version")
    except httpx.HTTPError:
        version = None
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    session = {
        "started": dt.datetime.now().isoformat(timespec="seconds"),
        "git_commit": _sh("git", "rev-parse", "--short", "HEAD"),
        "git_dirty": bool(_sh("git", "status", "--porcelain", "--untracked-files=no")),
        "frozen": FROZEN, "ollama_version": version, "models": args.models,
        "splits": args.splits, "num_ctx": args.num_ctx, "num_predict": args.num_predict,
        "retries": args.retries, "timeout_s": args.timeout, "temperature": 0.0, "seed": 0,
        "cpu": platform.processor(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "on_battery": battery is not None and not battery.power_plugged, "per_model": {},
    }
    meta["sessions"].append(session)
    if session["on_battery"]:
        log("WARNING: on battery power; timings will be throttled and noisy")
    if session["git_dirty"]:
        log("WARNING: uncommitted changes; results may not match git_commit")

    items = clear_questions(args.splits)
    dbs = databases()
    seeds = sorted({k[0] for k in dbs})
    gold = {(s, q.id): {seed: execute(dbs[(seed, False)], q.spec.interpretations[0].gold_sql)
                        for seed in seeds} for s, q in items}
    log(f"session {session['started']} commit {session['git_commit']}: {len(args.models)} models x "
        f"{len(items)} clear questions ({', '.join(args.splits)})")

    for model in args.models:
        path = out / f"{model_slug(model)}.jsonl"
        if args.retry_errors:
            n = drop_errors(path)
            if n:
                log(f"{model}: dropped {n} infra-error results to retry them")
        done = done_ids(path)
        todo = [(s, q) for s, q in items if f"{s}/{q.id}" not in done]
        if not todo:
            log(f"{model}: all {len(items)} questions already done, skipping")
            continue
        for m in loaded_models(args.url):  # nothing else resident
            Ollama(m, url=args.url).unload()
        avail = round(psutil.virtual_memory().available / 2**20)
        log(f"{model}: {len(todo)} to do ({len(done)} done); RAM available before load {avail} MB")
        llm = Ollama(model, url=args.url, num_ctx=args.num_ctx, num_predict=args.num_predict,
                     keep_alive="10m", timeout=args.timeout)
        t0 = dt.datetime.now()
        try:
            w = llm.chat(sql_messages("Warm-up request. Reply with: SELECT 1"))
            log(f"{model}: warm-up {w.total_duration_s:.0f}s (load {w.load_duration_s:.0f}s, "
                f"prompt {w.prompt_eval_count} tokens)")
        except httpx.HTTPError as e:
            log(f"{model}: warm-up failed: {type(e).__name__}: {e}; skipping model")
            continue
        lat = []
        with open(path, "a", encoding="utf-8") as f:
            for i, (split, q) in enumerate(todo, 1):
                tag = f"{model:17} {split}/{q.id}"
                log(f"{tag} start {dt.datetime.now():%H:%M:%S} ({i}/{len(todo)})")
                with stall_dump(args.stall_dump_s):
                    r = run_question(llm, split, q, dbs, gold[(split, q.id)])
                f.write(r.model_dump_json() + "\n")
                f.flush()
                lat.append(r.latency_s)
                m = r.meta
                log(f"{tag} lenient={r.scores['lenient']:.0f} strict={r.scores['strict']:.0f} "
                    f"att={r.output.get('attempts')} [{','.join(x or '?' for x in m['done_reason'])}] "
                    f"type={m['auto_type'] or '-'} prompt={m['prompt_eval_count']} "
                    f"{m['tok_s'][0] if m['tok_s'] else 0}tok/s {r.latency_s:.0f}s"
                    + (f" ERR {r.error}" if r.error else ""))
        llm.unload()
        session["per_model"][model] = {
            "started": t0.isoformat(timespec="seconds"), "minutes": round(
                (dt.datetime.now() - t0).total_seconds() / 60, 1),
            "questions": len(todo), "ram_available_before_mb": avail,
            "median_latency_s": round(statistics.median(lat), 1) if lat else None}
        meta_path.write_text(json.dumps(meta, indent=2))
    session["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    meta_path.write_text(json.dumps(meta, indent=2))
    log(f"done -> {out}")
    log_file.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="results/stage2")
    ap.add_argument("--models", nargs="+", default=MODELS)
    ap.add_argument("--splits", nargs="+", default=SPLITS, choices=SPLITS)
    ap.add_argument("--retries", type=int, default=RETRIES)
    ap.add_argument("--num-ctx", type=int, default=NUM_CTX)
    ap.add_argument("--num-predict", type=int, default=NUM_PREDICT)
    # 300 s per HTTP call: the 7B worst case is ~35 s of prompt + 256 tokens at ~6 tok/s ≈ 80 s
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--stall-dump-s", type=float, default=600)
    ap.add_argument("--retry-errors", action="store_true",
                    help="drop infra-error results first so they are retried")
    ap.add_argument("--url", default="http://localhost:11434")
    return bench(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
