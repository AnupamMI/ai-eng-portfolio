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
