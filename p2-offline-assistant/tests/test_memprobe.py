import time

import pytest

from studyqa.memprobe import MB, MemProbe, find_ollama_server, ollama_tree_rss


def test_probe_tracks_peak_above_baseline():
    values = iter([100 * MB, 150 * MB, 400 * MB, 200 * MB] + [200 * MB] * 1000)
    with MemProbe(sampler=lambda: next(values), interval_s=0.001) as m:
        time.sleep(0.05)
    assert m.baseline_mb == 100 and m.peak_mb == 400 and m.peak_delta_mb == 300
    assert m.samples >= 4


def test_probe_catches_spike_even_in_short_runs():
    values = iter([10 * MB, 50 * MB, 20 * MB])  # baseline, thread's first sample, exit
    with MemProbe(sampler=lambda: next(values), interval_s=60) as m:
        pass
    assert m.peak_delta_mb == 40


def _ollama_running() -> bool:
    try:
        find_ollama_server()
        return True
    except RuntimeError:
        return False


@pytest.mark.skipif(not _ollama_running(), reason="Ollama not running")
def test_live_tree_rss_is_positive():
    assert ollama_tree_rss() > 10 * MB
