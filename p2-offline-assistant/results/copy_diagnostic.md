# Copy diagnostic (LLM-graded (ChatGPT))

Copy = answer >= 6 tokens with best-window match >= 0.85 against the quote or the section. Defined before computing; see module docstring.

Predictions: **P1** models with a higher copy share have a lower mean grade; **P2** within a model, copied answers get lower grades than non-copied ones (CI of non-copy minus copy above 0); **P3** copied answers are grounded more often than non-copied ones (the mechanism by which copying would inflate groundedness).

## All valid questions, full run (both modes)

| model | questions | copy share | grounded@0.85/0.4: copies | non-copies | P3: non-copy minus copy, 95% CI |
|---|---|---|---|---|---|
| llama3.2-3b | 405 | 0.60 | 0.95 | 0.82 | -0.12 [-0.19, -0.06] * |
| phi3-mini | 410 | 0.51 | 0.89 | 0.79 | -0.11 [-0.18, -0.04] * |
| qwen2.5-3b | 420 | 0.53 | 0.92 | 0.81 | -0.11 [-0.18, -0.04] * |

## Graded rows (LLM-graded (ChatGPT))

| model | graded | copy share | mean grade | grade: copies (n) | non-copies (n) | P2: non-copy minus copy, 95% CI |
|---|---|---|---|---|---|---|
| llama3.2-3b | 40 | 0.57 | 2.05 | 2.13 (23) | 1.94 (17) | -0.19 [-0.53, +0.15] |
| phi3-mini | 40 | 0.47 | 2.50 | 2.47 (19) | 2.52 (21) | +0.05 [-0.35, +0.44] |
| qwen2.5-3b | 40 | 0.47 | 2.38 | 2.42 (19) | 2.33 (21) | -0.09 [-0.49, +0.32] |
| all (pooled) | 120 | 0.51 | 2.31 | 2.33 (61) | 2.29 (59) | -0.04 [-0.27, +0.19] |

`*` = 95% CI excludes 0. Unpaired bootstrap (evalkit.bootstrap_diff); uncorrected for the number of comparisons. P1 has only 3 points (one per model) and is descriptive: compare the ordering of the copy-share and mean-grade columns. Model-vs-model rows are confounded by section (each model was graded on its own sample); P2 is within model, so it is not.