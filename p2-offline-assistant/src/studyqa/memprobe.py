"""Peak RAM of the Ollama server process tree, sampled in a background thread.

The model runs in a child process of `ollama serve` (named llama-server.exe on
Ollama 0.40; older versions used other names), so we walk the tree instead of
matching names. Children are re-discovered on every sample because the runner
only starts when the model loads. Working set (RSS) includes memory-mapped
model weights that are resident, which is what decides whether a model fits.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

import psutil

MB = 1024 * 1024


def find_ollama_server() -> psutil.Process:
    for p in psutil.process_iter(["name", "cmdline"]):
        name = (p.info["name"] or "").lower()
        cmd = p.info["cmdline"] or []
        if name.startswith("ollama") and "serve" in cmd:
            return p
    raise RuntimeError("`ollama serve` process not found; is Ollama running?")


def ollama_tree_rss() -> int:
    """Bytes of working set across `ollama serve` and all its descendants."""
    server = find_ollama_server()
    total = 0
    for p in [server, *server.children(recursive=True)]:
        try:
            total += p.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass  # runner exited between listing and sampling
    return total


class MemProbe:
    """with MemProbe() as m: ...; m.mark("loaded"); ...  ->  m.phases()

    A single peak mixes very different things (on Ollama 0.40 the load-time
    weight repack briefly holds two copies of the weights; llama-server's prompt
    cache grows across requests), so the full series is kept and split at marks.
    """

    def __init__(self, sampler: Callable[[], int] = ollama_tree_rss, interval_s: float = 0.1):
        self.sampler = sampler
        self.interval_s = interval_s
        self.baseline = 0
        self.peak = 0
        self.series: list[tuple[float, int]] = []  # (seconds since start, bytes)
        self.marks: dict[str, float] = {}  # label -> seconds since start
        self._t0 = 0.0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    @property
    def samples(self) -> int:
        return len(self.series)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(self.interval_s)

    def _sample(self) -> int:
        v = self.sampler()
        self.series.append((time.perf_counter() - self._t0, v))  # list.append is atomic
        self.peak = max(self.peak, v)
        return v

    def mark(self, label: str) -> None:
        """Record a phase boundary (and a sample at it)."""
        self._sample()
        self.marks[label] = self.series[-1][0]

    def phases(self, split: str = "loaded") -> dict[str, float]:
        """MB above baseline: peak before the mark, value at the mark, peak after
        it, and the last sample. Without the mark, only the overall peak."""
        d = lambda v: round((v - self.baseline) / MB)
        out = {"baseline_mb": round(self.baseline_mb), "peak_delta_mb": d(self.peak),
               "end_delta_mb": d(self.series[-1][1]) if self.series else 0}
        if split in self.marks:
            t = self.marks[split]
            before = [v for s, v in self.series if s <= t]
            after = [v for s, v in self.series if s > t]
            at = next(v for s, v in reversed(self.series) if s <= t)
            out |= {"load_peak_delta_mb": d(max(before)), "loaded_delta_mb": d(at),
                    "gen_peak_delta_mb": d(max(after)) if after else d(at)}
        return out

    def series_1hz(self) -> list[tuple[int, int]]:
        """(second, max MB in that second) for plotting/saving."""
        by_s: dict[int, int] = {}
        for s, v in self.series:
            by_s[int(s)] = max(by_s.get(int(s), 0), v)
        return [(s, round(v / MB)) for s, v in sorted(by_s.items())]

    def __enter__(self) -> MemProbe:
        self._t0 = time.perf_counter()
        self.baseline = self.sampler()
        self.peak = self.baseline
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()
        self._sample()  # one final sample so short runs are not missed

    @property
    def baseline_mb(self) -> float:
        return self.baseline / MB

    @property
    def peak_mb(self) -> float:
        return self.peak / MB

    @property
    def peak_delta_mb(self) -> float:
        return (self.peak - self.baseline) / MB
