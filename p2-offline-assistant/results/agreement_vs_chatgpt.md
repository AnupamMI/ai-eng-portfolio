# Agreement: hand vs ChatGPT

30 rows, matched by `source_id`. Grades 1-3.

| statistic | value | bootstrap 95% CI |
|---|---|---|
| Spearman rho | 0.53 | [+0.17, +0.79] (5 of 10000 resamples undefined) |
| exact agreement | 0.70 (21/30) | [+0.53, +0.87] |
| weighted kappa, quadratic | 0.53 | [+0.13, +0.78] |
| weighted kappa, linear | 0.46 | [+0.12, +0.73] |
| mean grade hand | 2.10 |
| mean grade ChatGPT | 2.33 |
| grade counts 1 / 2 / 3, hand | 2 / 23 / 5 |
| grade counts 1 / 2 / 3, ChatGPT | 2 / 16 / 12 |

Confusion (rows: hand, columns: ChatGPT):

| | ChatGPT 1 | ChatGPT 2 | ChatGPT 3 | total |
|---|---|---|---|---|
| hand 1 | 2 | 0 | 0 | 2 |
| hand 2 | 0 | 15 | 8 | 23 |
| hand 3 | 0 | 1 | 4 | 5 |
| total | 2 | 16 | 12 | 30 |