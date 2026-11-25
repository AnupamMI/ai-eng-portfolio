# Grades: hand-graded
Source sheet: `to_grade.csv`. Grades: **hand-graded**.
Grade scaled to [0, 1] for the paired comparison: (grade - 1) / 2.

| model | mode | n | mean grade (1-3) |
|---|---|---|---|
| llama3.2-3b | constrained | 5 | 1.80 |
| llama3.2-3b | json | 5 | 2.00 |
| phi3-mini | constrained | 5 | 2.20 |
| phi3-mini | json | 5 | 2.20 |
| qwen2.5-3b | constrained | 5 | 2.40 |
| qwen2.5-3b | json | 5 | 2.00 |

## json (before) -> constrained (after), paired by section

**llama3.2-3b**

| metric | n | before | after | delta | 95% CI | sig |
|---|---|---|---|---|---|---|
| grade | 5 | 0.500 | 0.400 | -0.100 | [-0.300, +0.000] | no |

**phi3-mini**

| metric | n | before | after | delta | 95% CI | sig |
|---|---|---|---|---|---|---|
| grade | 5 | 0.600 | 0.600 | +0.000 | [-0.300, +0.300] | no |

**qwen2.5-3b**

| metric | n | before | after | delta | 95% CI | sig |
|---|---|---|---|---|---|---|
| grade | 5 | 0.500 | 0.700 | +0.200 | [+0.000, +0.400] | no |

## Does the lexical metric track the grades (hand-graded)? (Spearman, all graded rows)

| metric | rho | bootstrap 95% CI |
|---|---|---|
| quote_fidelity | -0.27 | [-0.62, +0.09] (49 of 10000 resamples undefined) |
| answer_support | -0.05 | [-0.39, +0.29] (5 of 10000 resamples undefined) |
| grounded@0.85/0.4 | -0.09 | [-0.44, +0.18] (33 of 10000 resamples undefined) |