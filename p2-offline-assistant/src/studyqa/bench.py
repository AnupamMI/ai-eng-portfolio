"""Benchmark models x decoding modes over a frozen section set.

    uv run python -m studyqa.bench --cases data/smoke_public.jsonl --out runs/smoke_public

Protocol (to keep CPU timing noise out of the comparisons):
- models run one at a time, unloaded before and after; model order rotates per pass
- one warm-up call per model absorbs load time and is excluded
- the two decoding modes are interleaved per section, alternating which goes first
- peak RAM is the ollama process tree's working set above its idle baseline
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import faulthandler
import hashlib
import json
import platform
import subprocess
from pathlib import Path

import httpx
import psutil

from evalkit import Case, Ollama, Result, load_cases, run, save_results
from studyqa.generate import NUM_CTX, NUM_PREDICT, RETRIES, generate
from studyqa.grounding import ground
from studyqa.memprobe import MemProbe
from studyqa.prompt import PROMPT_VERSION

MODELS = ["llama3.2:3b", "qwen2.5:3b", "phi3:mini"]
MODES = {"constrained": True, "json": False}
TAU_QUOTE, TAU_ANSWER = 0.85, 0.4  # frozen 2026-11-25 from the smoke run; see docs/LOG.md


def model_slug(model: str) -> str:
    return model.replace(":", "-").replace("/", "-")


def make_system(llm: Ollama, constrained: bool, retries: int):
    def system(section: dict) -> dict:
        g = generate(llm, section, constrained=constrained, retries=retries)
        out = g.model_dump(mode="json")
        out["first_try_valid"] = g.first_try_valid
        out["ctx_overflow"] = g.ctx_overflow
        out["grounding"] = ([x.model_dump() for x in ground(g.questions, section["text"])]
                            if g.questions else [])
        return out
    return system


def _grounded_rate(case: Case, out: dict) -> float:
    gs = out["grounding"]
    if not gs:
        return 0.0  # invalid output: nothing usable for the student
    return sum(g["quote_fidelity"] >= TAU_QUOTE and g["answer_support"] >= TAU_ANSWER
               for g in gs) / len(gs)


SCORERS = {
    "valid_first_try": lambda c, o: float(o["first_try_valid"]),
    "valid": lambda c, o: float(o["valid"]),
    "grounded": _grounded_rate,
}


@contextlib.contextmanager
def stall_dump(seconds: float):
    """Dump every thread's stack to stderr if the block runs longer than `seconds`
    (repeating), so a hung generation shows where it is stuck. Does not kill it."""
    if seconds > 0:
        faulthandler.dump_traceback_later(seconds, repeat=True)
    try:
        yield
    finally:
        if seconds > 0:
            faulthandler.cancel_dump_traceback_later()


def _meta(args, cases_path: Path) -> dict:
    def sh(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    try:
        version = httpx.get(f"{args.url}/api/version", timeout=5).json().get("version")
    except httpx.HTTPError:
        version = None
    battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    vm = psutil.virtual_memory()
    return {
        "system_ram_at_start_mb": {"total": round(vm.total / 2**20),
                                   "used": round(vm.used / 2**20),
                                   "available": round(vm.available / 2**20)},
        "started": dt.datetime.now().isoformat(timespec="seconds"),
        "git_commit": sh("git", "rev-parse", "--short", "HEAD"),
        "git_dirty": bool(sh("git", "status", "--porcelain", "--untracked-files=no")),
        "ollama_version": version,
        "prompt_version": PROMPT_VERSION,
        "cases_file": str(cases_path),
        "cases_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest()[:16],
        "models": args.models, "modes": args.modes, "passes": args.passes,
        "retries": args.retries, "num_ctx": args.num_ctx, "num_predict": args.num_predict,
        "seed": 0, "temperature": 0.0,
        "tau_quote": TAU_QUOTE, "tau_answer": TAU_ANSWER,
        "cpu": platform.processor(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "on_battery": (battery is not None and not battery.power_plugged),
        "memory": {},  # filled per model/pass
    }


def bench(args) -> None:
    cases = load_cases(args.cases)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(out_dir / "log.txt", "a", encoding="utf-8")

    def log(msg: str) -> None:  # console + log.txt, flushed so progress is visible live
        print(msg, flush=True)
        log_file.write(msg + "\n")
        log_file.flush()

    meta = _meta(args, Path(args.cases))
    if meta["on_battery"]:
        log("WARNING: on battery power; timings will be throttled and noisy")
    if meta["git_dirty"]:
        log("WARNING: uncommitted changes; results may not match git_commit")

    for p in range(args.passes):
        order = args.models[p % len(args.models):] + args.models[:p % len(args.models)]
        for model in order:
            llm = Ollama(model, url=args.url, num_ctx=args.num_ctx,
                         num_predict=args.num_predict, keep_alive="10m", timeout=600)
            for m in args.models:  # nothing else resident while we measure
                Ollama(m, url=args.url).unload()
            results: dict[str, list[Result]] = {mode: [] for mode in args.modes}
            avail = round(psutil.virtual_memory().available / 2**20)
            log(f"[pass {p}] {model}: system RAM available before load {avail} MB")
            with MemProbe() as probe:
                llm.chat([{"role": "user", "content": "Reply with OK."}])  # warm-up
                probe.mark("loaded")
                for i, case in enumerate(cases):
                    modes = args.modes if i % 2 == 0 else list(reversed(args.modes))
                    for mode in modes:
                        system = make_system(llm, MODES[mode], args.retries)
                        # a start line makes a slow section distinguishable from a dead process
                        log(f"[pass {p}] {model:12} {mode:11} {case.id[:55]:55} start "
                            f"{dt.datetime.now():%H:%M:%S}")
                        with stall_dump(args.stall_dump_s):
                            (r,) = run(system, [case], SCORERS)
                        results[mode].append(r)
                        o = r.output or {}
                        tps = (o.get("responses") or [{}])[0]
                        tps = (tps.get("eval_count", 0) / tps["eval_duration_s"]
                               if tps.get("eval_duration_s") else 0)
                        reasons = ",".join(x.get("done_reason") or "?"
                                           for x in o.get("responses", []))
                        log(f"[pass {p}] {model:12} {mode:11} {case.id[:55]:55} "
                            f"valid={o.get('valid')} att={o.get('attempts')} [{reasons}] "
                            f"grounded={r.scores['grounded']:.2f} {tps:.1f}tok/s "
                            f"{r.latency_s:.0f}s {'ERR ' + r.error if r.error else ''}")
            llm.unload()
            meta["memory"][f"{model}|pass{p}"] = {
                **probe.phases(), "system_available_before_mb": avail, "samples": probe.samples}
            with open(out_dir / f"mem_{model_slug(model)}_p{p}.csv", "w", encoding="utf-8") as f:
                f.write("second,mb\n" + "".join(f"{s},{v}\n" for s, v in probe.series_1hz()))
            for mode, rs in results.items():
                save_results(rs, out_dir / f"{model_slug(model)}__{mode}__p{p}.jsonl")
            (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    meta["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    log(f"done -> {out_dir}")
    log_file.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--models", nargs="+", default=MODELS)
    ap.add_argument("--modes", nargs="+", default=list(MODES), choices=list(MODES))
    ap.add_argument("--passes", type=int, default=1)
    ap.add_argument("--retries", type=int, default=RETRIES)
    ap.add_argument("--num-ctx", type=int, default=NUM_CTX)
    ap.add_argument("--num-predict", type=int, default=NUM_PREDICT)  # rationale: generate.py
    ap.add_argument("--url", default="http://localhost:11434")
    # 900 s: worst legitimate generation is 3 capped attempts (~3 x 175 s for phi3)
    ap.add_argument("--stall-dump-s", type=float, default=900,
                    help="dump stacks to stderr if one generation exceeds this (0 = off)")
    bench(ap.parse_args(argv))


if __name__ == "__main__":
    main()
