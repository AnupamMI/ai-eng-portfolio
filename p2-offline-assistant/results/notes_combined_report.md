# Report: notes_full, notes_full_phi3

Ollama 0.40.18, prompt v1, num_ctx 4096, num_predict 1536, retries 2, passes 1, on battery: ['False']. Thresholds: tau_quote=0.85, tau_answer=0.4. 1235 questions in questions.csv.

## Sessions

Timing and RAM are only comparable between models run in the same session: sessions ran at different times with different background load.

| run dir | models | commit | started | finished | system RAM at start (used / available MB) | available before each model load (MB) |
|---|---|---|---|---|---|---|
| `runs/notes_full` | llama3.2-3b, qwen2.5-3b | `a5ea99b` | 2026-11-25T02:05:02 | n/a | 8933 / 6840 | llama3.2:3b: 8869, qwen2.5:3b: 8799 |
| `runs/notes_full_phi3` | phi3-mini | `c2305f0` | 2026-11-25T11:15:52 | 2026-11-25T12:44:25 | 6486 / 9287 | phi3:mini: 9284 |

## Reliability

*schema fail / runaway / infra error* count sections that never produced valid output, by cause. *Cap hits* counts attempts that stopped at num_predict, including ones a retry recovered. *Retried* = sections needing >= 1 retry. Infra-error sections have no attempts recorded and are excluded from retries.

| model | mode | n | valid 1st try | valid | schema fail | runaway | infra error | retried | mean retries | cap hits (attempts) | ctx overflow | tok/s p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llama3.2-3b | constrained | 42 | 1.00 | 1.00 | 0 | 0 | 0 | 0 | 0.00 | 0 | 0 | 13.9 |
| llama3.2-3b | json | 42 | 0.79 | 0.93 | 3 | 0 | 0 | 9 | 0.36 | 0 | 0 | 14.0 |
| phi3-mini | constrained | 42 | 0.95 | 0.98 | 0 | 0 | 1 | 1 | 0.02 | 1 | 0 | 11.6 |
| phi3-mini | json | 42 | 0.95 | 0.98 | 0 | 0 | 1 | 1 | 0.02 | 0 | 0 | 11.6 |
| qwen2.5-3b | constrained | 42 | 1.00 | 1.00 | 0 | 0 | 0 | 0 | 0.00 | 0 | 0 | 14.9 |
| qwen2.5-3b | json | 42 | 1.00 | 1.00 | 0 | 0 | 0 | 0 | 0.00 | 0 | 0 | 14.8 |

## Groundedness

Grounded = quote_fidelity >= tau_quote and answer support vs the QUOTE >= tau_answer. Section-supported = answer support vs the whole SECTION >= tau_answer. Wrong quote = section-supported but not grounded. All but 'grounded (all)' are over questions from valid outputs.

| model | mode | grounded (all) | grounded (valid only) | section-supported | wrong quote | quote fid. p50 | ans. support (quote) p50 | ans. support (section) p50 |
|---|---|---|---|---|---|---|---|---|
| llama3.2-3b | constrained | 0.91 | 0.91 | 0.99 | 0.08 | 1.00 | 1.00 | 1.00 |
| llama3.2-3b | json | 0.82 | 0.88 | 0.99 | 0.11 | 1.00 | 1.00 | 1.00 |
| phi3-mini | constrained | 0.81 | 0.83 | 0.99 | 0.16 | 1.00 | 1.00 | 1.00 |
| phi3-mini | json | 0.83 | 0.85 | 0.99 | 0.14 | 1.00 | 1.00 | 1.00 |
| qwen2.5-3b | constrained | 0.88 | 0.88 | 1.00 | 0.12 | 1.00 | 0.92 | 1.00 |
| qwen2.5-3b | json | 0.85 | 0.85 | 1.00 | 0.15 | 1.00 | 0.94 | 1.00 |

## Memory

MB of working set above the idle `ollama serve` baseline. *Loaded* = after warm-up (model ready); *load peak* includes the transient weight-repack copy.

| model | loaded | generation peak | load peak | end of run | server baseline |
|---|---|---|---|---|---|
| llama3.2-3b | 2448 | 4293 | 2448 | 4290 | 27 |
| phi3-mini | 3646 | 10523 | 3646 | 10146 | 28 |
| qwen2.5-3b | 2055 | 2854 | 2055 | 2854 | 27 |

## Decoding mode, paired by section (95% bootstrap CI)

**llama3.2-3b**: json (before) -> constrained (after)

| metric | n | before | after | delta | 95% CI | sig |
|---|---|---|---|---|---|---|
| grounded | 42 | 0.819 | 0.914 | +0.095 | [+0.024, +0.181] | yes |
| valid | 42 | 0.929 | 1.000 | +0.071 | [+0.000, +0.167] | no |
| valid_first_try | 42 | 0.786 | 1.000 | +0.214 | [+0.095, +0.357] | yes |

**phi3-mini**: json (before) -> constrained (after)

| metric | n | before | after | delta | 95% CI | sig |
|---|---|---|---|---|---|---|
| grounded | 42 | 0.833 | 0.810 | -0.024 | [-0.057, +0.010] | no |
| valid | 42 | 0.976 | 0.976 | +0.000 | [+0.000, +0.000] | no |
| valid_first_try | 42 | 0.952 | 0.952 | +0.000 | [-0.071, +0.071] | no |

**qwen2.5-3b**: json (before) -> constrained (after)

| metric | n | before | after | delta | 95% CI | sig |
|---|---|---|---|---|---|---|
| grounded | 42 | 0.848 | 0.881 | +0.033 | [-0.019, +0.090] | no |
| valid | 42 | 1.000 | 1.000 | +0.000 | [+0.000, +0.000] | no |
| valid_first_try | 42 | 1.000 | 1.000 | +0.000 | [+0.000, +0.000] | no |

## Threshold sensitivity

Grounded rate vs tau_quote (tau_answer fixed at 0.4):

| model | mode | tau_quote=0.8 | tau_quote=0.85 | tau_quote=0.9 | tau_quote=0.95 | tau_quote=1.0 |
|---|---|---|---|---|---|---|
| llama3.2-3b | constrained | 0.92 | 0.91 | 0.91 | 0.90 | 0.90 |
| llama3.2-3b | json | 0.89 | 0.88 | 0.88 | 0.87 | 0.86 |
| phi3-mini | constrained | 0.84 | 0.83 | 0.82 | 0.80 | 0.78 |
| phi3-mini | json | 0.86 | 0.85 | 0.85 | 0.83 | 0.80 |
| qwen2.5-3b | constrained | 0.88 | 0.88 | 0.88 | 0.87 | 0.87 |
| qwen2.5-3b | json | 0.85 | 0.85 | 0.84 | 0.84 | 0.82 |

Grounded rate vs tau_answer (tau_quote fixed at 0.85):

| model | mode | tau_answer=0.3 | tau_answer=0.4 | tau_answer=0.5 | tau_answer=0.6 | tau_answer=0.7 |
|---|---|---|---|---|---|---|
| llama3.2-3b | constrained | 0.93 | 0.91 | 0.90 | 0.87 | 0.84 |
| llama3.2-3b | json | 0.90 | 0.88 | 0.86 | 0.84 | 0.81 |
| phi3-mini | constrained | 0.87 | 0.83 | 0.81 | 0.77 | 0.73 |
| phi3-mini | json | 0.89 | 0.85 | 0.83 | 0.80 | 0.76 |
| qwen2.5-3b | constrained | 0.91 | 0.88 | 0.86 | 0.80 | 0.73 |
| qwen2.5-3b | json | 0.88 | 0.85 | 0.82 | 0.75 | 0.70 |

Section-supported rate vs tau_answer:

| model | mode | tau_answer=0.3 | tau_answer=0.4 | tau_answer=0.5 | tau_answer=0.6 | tau_answer=0.7 |
|---|---|---|---|---|---|---|
| llama3.2-3b | constrained | 1.00 | 0.99 | 0.99 | 0.99 | 0.98 |
| llama3.2-3b | json | 0.99 | 0.99 | 0.99 | 0.99 | 0.97 |
| phi3-mini | constrained | 1.00 | 0.99 | 0.98 | 0.97 | 0.94 |
| phi3-mini | json | 1.00 | 0.99 | 0.97 | 0.95 | 0.93 |
| qwen2.5-3b | constrained | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 |
| qwen2.5-3b | json | 1.00 | 1.00 | 1.00 | 1.00 | 0.99 |