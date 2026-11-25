# p1 failure log

Every failure found during development or benchmarking, appended in order.
Format: what broke, why, how fixed, metric before/after.

## 2026-11-25: generator let one customer dominate every ranking (seed 1)
- **What broke:** `test_features_that_make_interpretations_diverge[1]` failed. On seed 1 the top
  customer by revenue and the top customer by order count were the same (customer 193), and the
  top-5 lists were identical. "Best customer" would then have had one answer on seed 1, so that
  ambiguity would measure nothing there.
- **Why:** order frequency was Pareto(1.6) with no cap. Seed 1 drew one extreme value: customer 193
  had 237 orders (8.7% of all 3,000, more than twice the next customer), which outweighs basket
  size in any ranking. Seed 0 happened not to draw such a value (max share 5.4%). The docstring
  claim that the two rankings "differ naturally" was true for seed 0 only.
- **Fix:** cap the frequency weight at 6x the minimum (`FREQ_CAP`). **The cap was chosen after
  seeing results** for caps of none, 10, 6 and 4: 10 still tied top-1 on seed 1, while 6 and 4 did not.
  The rejected alternative, anti-correlating basket size with frequency, would force the two readings
  apart by construction. Added `test_no_customer_dominates` (max order share < 3%) and a top-5
  overlap check (<= 3), so the test is not just about the single top spot.
- **Before/after (seed 0 / seed 1):** max customer share of orders 0.054 / 0.087 -> 0.014 / 0.013;
  top-1 differs True / False -> True / True; top-5 overlap 3 / 5 -> 1 / 0.

## 2026-11-25: PRE-REGISTERED stage-2 gate (written before any model run)
Not a failure. It is recorded here so it is dated and committed before stage 2 produces numbers.
Clarification (B) and the oracle (C) can only be as good as the model's plain SQL. If plain SQL is
poor, the A/B/C comparison is mostly SQL noise and cannot be interpreted.
- **Measure:** execution accuracy on the ~25 clear test questions (match on both seeds), per model,
  as a point estimate. The CI is reported but is not used for the decision, which is fixed in advance.
- **Gate: 0.50.** Below it, more than half of the failures on ambiguous questions would be SQL
  failures and not ambiguity. With ~25 questions the 95% CI half-width is about ±0.19 near 0.5, so a
  clarification effect would not be separable from SQL errors.
- **A model below the gate** is still reported in stage 2, but it is excluded from the
  clarification headline (its A/B/C numbers go to an appendix, labelled uninterpretable).
- **If every 3B model is below the gate**, these steps apply in order, stopping at the first that
  passes. Each step is logged here with the numbers before and after:
  1. Use `qwen2.5-coder:7b` as the main model. Nothing about the prompt changes, so the test set
     stays clean.
  2. Add up to 3 few-shot examples, written and tuned **on the dev set only**, and rerun stage 2 for
     all models. Both the zero-shot and few-shot numbers are reported.
  3. Simplify the schema description (for example, column notes or a view for revenue). This is
     last because it changes the task, and the README will say so.
- **If no model passes after step 3**, the README reports plain-SQL accuracy as the result and says
  the clarification comparison was not interpretable. No headline A/B/C number is given.
- **Not allowed:** editing test questions, gold SQL or the glossary after seeing model output; or
  moving the gate.

## 2026-11-25: DECISION, headline metric allows extra columns (made before stage 2)
Not a failure; recorded before any model run, like the gate above.
- **Headline and gate metric: lenient execution accuracy.** A prediction matches if some ordered
  choice of its columns reproduces the gold result (`execute.compare`). Extra columns are allowed;
  rows, values and multiplicities must match exactly.
- **Reported next to it in every table: strict (Spider-style)**, which also requires the same number
  of columns (`Match.extra_columns` is False).
- **Why lenient for the headline:** small models often add a helpful column (a name next to an id,
  or the total next to a ranked name). That is a formatting choice, not a wrong answer, and the
  project measures whether the SQL answers the question. Strict next to it shows how much the
  leniency buys. A large gap between the two would itself be a finding about format adherence.
- **Mitigation in the prompt:** the SQL prompt tells the model to return only the columns the
  question asks for (`prompt.py`, frozen with the test set). The glossary also fixes how entities
  are returned (by name), so most format variation is removed at the source, not by the scorer.
- **The 0.50 gate stays as pre-registered:** per model, point estimate, applied to the lenient metric.
