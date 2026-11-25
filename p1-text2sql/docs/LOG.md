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

## 2026-11-25: stage 1, problems found while drafting the test set (before any model run)
All fixed before the hand check. Nothing here has been seen by a model.
1. **Four ambiguous drafts were not really ambiguous on the data.** Validator rule R4 rejected a03
   (best category: revenue, units and order count all picked Electronics), a04 (biggest UK customer:
   gross and net of refunds picked the same customer, because refunds are rare), a06 (countries
   ranked by revenue or by order count: the same order, because country size dominates both) and a16
   ("paid us": any payment vs net positive, the same count). **Fix:** the questions were replaced, not
   the data: a03 became a ranking (revenue vs units), a04 "most popular product" (units vs distinct
   customers), a06 "3 most valuable customers in India" (revenue vs orders), a16 "new customers in
   2026" (signup vs first order). Changing the generator to separate the readings would have tuned
   the data to the questions. **Metric:** R4 errors 6 -> 0 (4 questions).
2. **Validator bug: R4 compared rankings as unordered sets.** The new a03 (two different
   rankings of the same 6 categories) was rejected as "same result". **Why:** R4 called the
   comparator without the reading's `ordered` flag, unlike the benchmark scorer. **Fix:** R4 now
   scores each reading against the other with the target reading's `ordered` flag, exactly as the
   benchmark does. Regression test `test_r4_respects_row_order`. **Metric:** false R4 errors 1 -> 0.
3. **The clear questions were easier SQL than the ambiguous ones.** The validator's difficulty table
   (test set, mean per question, clear vs ambiguous): joins 0.60 vs 1.00, uses dates 0.40 vs 0.72,
   SQL length 137 vs 174 characters. That would bias the stage-2 gate: clear accuracy would overstate
   the SQL ceiling on ambiguous questions. **Fix:** replaced the 5 most trivial clear questions
   (c01, c08, c11, c13, c23: single table, no dates) with join and date questions. **After:** joins
   0.96 vs 1.00, dates 0.56 vs 0.72, length 171 vs 174. The remaining date gap is structural:
   the time-window category is about dates by definition. The README will state it.
4. **Glossary gap:** "units sold" did not say whether cancelled orders count, so every "how many
   did we sell" question carried a second, hidden ambiguity that its clarifying answer did not
   resolve. **Fix (before the freeze):** the glossary now says units sold excludes cancelled orders.
