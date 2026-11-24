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


@pytest.mark.live
@pytest.mark.skipif(not _ollama_running(), reason="Ollama not running")
def test_live_tree_rss_is_positive():
    assert ollama_tree_rss() > 10 * MB


def test_phases_split_load_spike_from_steady_state():
    # baseline 50, load spike to 400, settles at 250 when marked, grows to 300 by the end
    vals = [50, 400, 260, 250] + [250, 280, 300] + [300] * 10000
    it = iter(v * MB for v in vals)
    m = MemProbe(sampler=lambda: next(it), interval_s=3600)  # thread samples once at start
    with m:
        m._sample(); m._sample()      # 260, 250 (load phase)
        m.mark("loaded")              # 250
        m._sample(); m._sample()      # 280, 300 (generation)
    p = m.phases()
    assert p["baseline_mb"] == 50 and p["load_peak_delta_mb"] == 350
    assert p["loaded_delta_mb"] == 200 and p["gen_peak_delta_mb"] == 250
    assert p["end_delta_mb"] == 250 and p["peak_delta_mb"] == 350
    assert m.series_1hz()[0][1] == 400


def test_phases_without_mark_reports_overall_peak_only():
    it = iter(v * MB for v in [10, 30, 20, 20])
    with MemProbe(sampler=lambda: next(it), interval_s=3600) as m:
        pass
    assert "loaded_delta_mb" not in m.phases() and m.phases()["peak_delta_mb"] == 20
