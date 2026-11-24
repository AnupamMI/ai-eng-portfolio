import pytest

from studyqa.grounding import QuestionGrounding, content_words, ground, quote_fidelity, support
from studyqa.schema import QuestionSet

SECTION = ("A **closure** is the combination of a function bundled together with references "
           "to its surrounding state. In JavaScript, closures are created every time a "
           "function is created, at function creation time.")


def test_verbatim_quote_ignoring_markdown_and_case():
    assert quote_fidelity("A closure is the combination of a function bundled together",
                          SECTION) == 1.0


def test_near_verbatim_quote_scores_high_but_below_one():
    f = quote_fidelity("closures are created each time a function is created", SECTION)
    assert 0.8 < f < 1.0


def test_fabricated_quote_scores_low():
    assert quote_fidelity("Closures are garbage collected by the V8 engine when idle",
                          SECTION) < 0.5


def test_support_uses_content_words_and_stems():
    assert content_words("The functions are created") == {"function", "creat"}
    assert support("Functions bundled with state", SECTION) == 1.0
    assert support("It is garbage collection", SECTION) == 0.0
    assert support("the and of", SECTION) == 0.0  # no content words


def test_ground_per_question_and_thresholds():
    q = {"question": "What is a closure?", "difficulty": "easy",
         "answer": "A function bundled with references to its surrounding state.",
         "source_quote": "A closure is the combination of a function bundled together with "
                         "references to its surrounding state."}
    bad = {**q, "answer": "A memory leak in Python.", "source_quote": "Python leaks memory."}
    gs = ground(QuestionSet(questions=[q] * 4 + [bad]), SECTION)
    assert gs[0].grounded(0.9, 0.5) and not gs[4].grounded(0.9, 0.5)
    assert gs[0].quote_fidelity == 1.0 and gs[0].answer_support == pytest.approx(1.0)


def test_thresholds_are_inclusive():
    g = QuestionGrounding(quote_fidelity=0.9, answer_support=0.5, section_support=0.5)
    assert g.grounded(0.9, 0.5) and not g.grounded(0.91, 0.5)
