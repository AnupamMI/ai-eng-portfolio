# Grades: LLM-graded (ChatGPT)
Source sheet: `graded_to_grade.csv`. Grades: **LLM-graded (ChatGPT)**.
Grade scaled to [0, 1] for the paired comparison: (grade - 1) / 2.

| model | mode | n | mean grade (1-3) |
|---|---|---|---|
| llama3.2-3b | constrained | 20 | 2.05 |
| llama3.2-3b | json | 20 | 2.05 |
| phi3-mini | constrained | 20 | 2.65 |
| phi3-mini | json | 20 | 2.35 |
| qwen2.5-3b | constrained | 20 | 2.35 |
| qwen2.5-3b | json | 20 | 2.40 |

## json (before) -> constrained (after), paired by section

**llama3.2-3b**

| metric | n | before | after | delta | 95% CI | sig |
|---|---|---|---|---|---|---|
| grade | 20 | 0.525 | 0.525 | +0.000 | [-0.175, +0.175] | no |

**phi3-mini**

| metric | n | before | after | delta | 95% CI | sig |
|---|---|---|---|---|---|---|
| grade | 20 | 0.675 | 0.825 | +0.150 | [-0.050, +0.350] | no |

**qwen2.5-3b**

| metric | n | before | after | delta | 95% CI | sig |
|---|---|---|---|---|---|---|
| grade | 20 | 0.700 | 0.675 | -0.025 | [-0.200, +0.125] | no |

## Does the lexical metric track the grades (LLM-graded (ChatGPT))? (Spearman, all graded rows)

| metric | rho | bootstrap 95% CI |
|---|---|---|
| quote_fidelity | -0.05 | [-0.26, +0.18] |
| answer_support | -0.09 | [-0.29, +0.11] |
| grounded@0.85/0.4 | 0.05 | [-0.14, +0.24] |