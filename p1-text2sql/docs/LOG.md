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

## 2026-11-26: hand check rejected four ambiguous test questions (before any model run)
**What happened:** the user hand-checked every reading in `testset/check_sheet.csv` (dev and
test, 92 rows). All gold SQL was accepted (`gold_ok = y` everywhere). Every label was accepted
except four ambiguous test questions, marked `label_ok = n`: the user judged that they have
one natural reading, so they are not ambiguous. Reasons, verbatim from the user:
- a07 ("How many orders, including cancelled ones, did we get last month?"): "Last month" means the previous calendar month (May), not the current month (June), so reading B isn't a natural interpretation.
- a08 ("What was our revenue this year?"): "This year" normally means the current calendar year (2026 YTD), not the past 12 months.
- a10 ("How many new customers signed up last quarter?"): "Last quarter" means the previous completed calendar quarter (January-March), not the current quarter (April-June).
- a12 ("How many active customers do we have?"): "Active customers" is ambiguous, but the readings aren't sufficiently well-defined alternatives: registered customers aren't necessarily active, and the 90-day cutoff is arbitrary.

**Why it got through:** the validator checks only that readings give different *results* (R4).
It cannot judge whether a second reading is one a real person would choose. Three of the four
are "last/this + calendar unit" questions, where the second reading was manufactured.
**What is done:** the marks are in the check sheet. The four questions stay in `questions.jsonl`
unchanged until the user approves replacements. They are not reworded to pass, and
nothing is frozen yet. The replacements keep 25 ambiguous questions and the category counts
(3 time_window, 1 entity), and they go through the same hand check before the freeze.
**Metric:** labels accepted 46/50 questions (83/92 rows: the 4 rejected questions have 9 readings);
gold SQL accepted 92/92 rows.

## 2026-11-26: replacements for the four rejected questions, hand checked and approved
**What was done:** four replacements were drafted under the user's guidance (time window: both
readings must be natural, e.g. "past N weeks" or "recently"; entity: alternatives must be precise
rules people use; readings must differ by at least 5 on both seeds and not coincide with any
existing answer). Drafts that failed these checks were dropped before the hand check: a "top 5
products" ranking (ties at the LIMIT boundary on both seeds), units per category (per-category gaps
of 2), an open-order count (91, the same value as a19 on seed 0), and a distinct-customer count
(gap of 1 on seed 1).
**Hand check (user, all calls theirs):** approved 4/4, label_ok = y and gold_ok = y for every
reading. The user's note: all four are genuinely ambiguous; a12 is the strongest pair, with "not
yet delivered" the more conventional reading.

| id | question | readings (seed 0 / seed 1) |
|---|---|---|
| a07 | How many orders, of any status, did we get over the past 4 weeks? | 28 days to today 409 / 421; last 4 full Mon-Sun weeks 403 / 412 |
| a08 | How many units did we sell over the past two weeks? | 14 days to today 663 / 617; last 2 full Mon-Sun weeks 636 / 635 |
| a10 | What was our revenue from customers in India recently? | last 30 days 50079.84 / 42794.41; last 90 days 123705.23 / 90365.68 |
| a12 | What is the total value of the orders that are still open? | not shipped 12710.07 / 8033.21; not delivered 52375.38 / 49604.97 |

**The rejected questions:** moved, unchanged and byte for byte, to `testset/rejected.jsonl` under
their original ids. The validator does not load that file. The replacements reuse the ids a07,
a08, a10 and a12 to keep the numbering, so **an id in an entry before this one refers to the
rejected question**. The rejected versions also remain in git history (commit 439d301).
`check_sheet.csv` was regenerated: 91 rows, all y/y. Test pairs went from 77 to 76 because the
old a12 had 3 readings.
**Metric:** validator 0 errors and 1 warning (da1 on seed 1 only, unchanged); 130 tests pass.

**Scoring rules fixed with the set (not in the glossary, which is frozen):**
- **Date boundaries:** "the last N days" includes today, so it starts on today minus (N-1) days
  (a07: 2026-06-03 to 2026-06-30). A model that writes `>= date('2026-06-30', '-28 days')` gets
  one extra day and is scored wrong. Such off-by-one-day answers are reported as the `date` error
  type in the error taxonomy. The same rule already applied to a09 and a11. Size, seed 0: a07 409
  -> 424, a08 663 -> 688, a10 (90d) 123705.23 -> 124825.54.
- **Numbers (e.g. c22, a percentage with many decimals):** the comparator rounds gold and
  predicted values to 2 decimals and then requires them to be equal (`execute.py`). This is not a
  plus/minus tolerance, but it behaves like plus/minus 0.005 except at a rounding boundary. c22 is
  8.2855 (-> 8.29) on seed 0 and 8.8889 (-> 8.89) on seed 1, far from a boundary compared with
  float error. A model that rounds to 1 decimal or returns a fraction (0.0829) is scored wrong.

## 2026-11-26: FREEZE of the test set, dev set, prompt and generator (before any model run)
Git blob hashes at commit 7d03863. Check them with
`git rev-parse HEAD:p1-text2sql/<path>` or `git hash-object p1-text2sql/<path>`; blob hashes
are computed after line-ending normalisation, so they are the same on Windows and Linux.

| file | git blob |
|---|---|
| `testset/questions.jsonl` (test: 25 clear + 25 ambiguous, 76 pairs) | `bc0274de052e9fe10c8a25a14130019804438499` |
| `testset/dev.jsonl` (dev: 5 clear + 5 ambiguous, 15 pairs) | `fd02051206a4257bb03ff35f4a5ae1a8a7cb42dd` |
| `src/text2sql/prompt.py` (rules, schema text, glossary) | `1f34cf2ec86c896f59d2edaf9bee5edaef4f967a` |
| `src/text2sql/db.py` (generator; seeds 0 and 1) | `c089cdca8c18843b1878d9d8d5be52b62414464c` |
| `src/text2sql/execute.py` (executor and comparator; added so the scoring rules are frozen too) | `5a6811b7098e7263adee72ebb8a09fe683a00a05` |

**Rule from here on:** none of these files changes while results are being measured. If one has
to change (for example a gold-SQL bug found in the audit), the change gets its own LOG entry
saying what, why and which results it invalidates, plus new hashes, and the affected runs are
repeated. The test set is never edited to match model output. Prompt iteration (few-shot
fallback, stage 2 gate) uses dev only, and a new prompt is a new, logged file version.
