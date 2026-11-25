from studyqa.diagnostics import is_copy

SECTION = ("Q-learning updates a value estimate for each state-action pair using the reward "
           "and the discounted value of the best next action. It is an off-policy method.")
QUOTE = ("Q-learning updates a value estimate for each state-action pair using the reward and "
         "the discounted value of the best next action.")


def test_verbatim_answer_is_a_copy():
    assert is_copy("it updates a value estimate for each state-action pair using the reward",
                   QUOTE, SECTION)


def test_copy_from_section_outside_the_quote_counts():
    assert is_copy("It is an off-policy method.", QUOTE, SECTION)  # not in the quote


def test_paraphrase_is_not_a_copy():
    assert not is_copy("It learns how good each move is from rewards plus the best future "
                       "move, even while following a different policy", QUOTE, SECTION)


def test_short_answers_are_never_copies():
    assert not is_copy("off-policy method", QUOTE, SECTION)
