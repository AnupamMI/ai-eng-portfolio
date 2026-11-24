"""Peak RAM of the Ollama server process tree, sampled in a background thread.

The model runs in a child process of `ollama serve` (named llama-server.exe on
Ollama 0.40; older versions used other names), so we walk the tree instead of
matching names. Children are re-discovered on every sample because the runner
only starts when the model loads. Working set (RSS) includes memory-mapped
model weights that are resident, which is what decides whether a model fits.
"""

from __future__ import annotations

import threading
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
    """with MemProbe() as m: ...  ->  m.peak_delta_mb"""

    def __init__(self, sampler: Callable[[], int] = ollama_tree_rss, interval_s: float = 0.1):
        self.sampler = sampler
        self.interval_s = interval_s
        self.baseline = 0
        self.peak = 0
        self.samples = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(self.interval_s)

    def _sample(self) -> None:
        self.peak = max(self.peak, self.sampler())
        self.samples += 1

    def __enter__(self) -> MemProbe:
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
