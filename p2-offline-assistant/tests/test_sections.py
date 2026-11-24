from pathlib import Path

import pytest

from studyqa.sections import load_notes, select, split_markdown, strip_mdn_macros, to_cases

W = "word " * 200  # a 200-word paragraph


def test_short_doc_is_one_section():
    secs = split_markdown(f"# Title\n\n{W}\n\n## A\n\n{W}", "n.md", max_words=1000)
    assert len(secs) == 1 and secs[0].words > 400


def test_long_doc_splits_at_headings_and_drops_stubs():
    doc = f"intro {W}\n## A\n{W}\n## B\ntoo short\n## C\n{W}{W}"
    secs = split_markdown(doc, "notes/n.md", min_words=150, max_words=500)
    assert [s.title for s in secs] == ["n", "n > A", "n > C"]
    assert secs[0].text.startswith("intro")
    assert all(s.id.startswith("n--") for s in secs)


def test_oversized_section_recurses_into_subheadings():
    doc = f"## A\n{W}\n### A1\n{W}\n### A2\n{W}\n## B\n{W}"
    secs = split_markdown(doc, "n.md", min_words=150, max_words=450)
    assert [s.title for s in secs] == ["n > A", "n > A > A1", "n > A > A2", "n > B"]


def test_hash_lines_in_code_fences_are_not_headings():
    doc = f"## Py\n{W}\n```python\n# not a heading\nx = 1\n```\n{W}\n## B\n{W}"
    secs = split_markdown(doc, "n.md", min_words=150, max_words=500)
    assert [s.title for s in secs] == ["n > Py", "n > B"]
    assert "# not a heading" in secs[0].text


def test_front_matter_gives_title_and_is_removed():
    doc = f"---\ntitle: Closures\nslug: x\n---\n\n{W}"
    (s,) = split_markdown(doc, "c.md")
    assert s.title == "Closures" and "slug" not in s.text


def test_strip_mdn_macros():
    t = ('Use {{HTTPHeader("Cache-Control")}} and {{Glossary("CORS", "cross-origin")}} '
         'or {{Glossary("Cookie")}}.\n{{Specifications}}')
    assert strip_mdn_macros(t) == "Use `Cache-Control` and cross-origin or Cookie.\n"
    assert strip_mdn_macros('{{domxref("Window/fetch", "fetch()")}} and '
                            '{{jsxref("Object.create()")}}') == "`fetch()` and `Object.create()`"


def test_duplicate_headings_get_unique_ids():
    doc = f"## A\n### Example\n{W}\n## B\n### Example\n{W}"
    ids = [s.id for s in split_markdown(doc, "n.md", max_words=300)]
    assert len(ids) == len(set(ids)) == 2


def test_select_round_robins_sources_and_is_deterministic():
    secs = (split_markdown(f"## A\n{W}\n## B\n{W}\n## C\n{W}", "x.md", max_words=300)
            + split_markdown(f"## D\n{W}", "y.md", max_words=300))
    picked = select(secs, 2, seed=1)
    assert {s.source for s in picked} == {"x.md", "y.md"}
    assert [s.id for s in picked] == [s.id for s in select(secs, 2, seed=1)]
    with pytest.raises(ValueError):
        select(secs, 10)


def test_sample_data_yields_enough_sections():
    root = Path(__file__).parents[1] / "sample_data" / "mdn"
    secs = load_notes(root, mdn=True)
    assert len({s.source for s in secs}) == 8
    assert len(secs) >= 36  # enough for the full public benchmark
    assert all(150 <= s.words <= 1200 for s in secs)
    assert not any("{{" in s.text for s in secs)
    cases = to_cases(select(secs, 8))
    assert len({c.tags[0] for c in cases}) == 8  # smoke set: one section per page
