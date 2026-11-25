# p2: Offline study assistant

Turns one section of markdown study notes into 5 structured revision questions
(`question`, `answer`, `difficulty`, `source_quote`) with a local 3B model via
Ollama, and benchmarks `llama3.2:3b`, `qwen2.5:3b` and `phi3:mini` on CPU.

Scope: one section in, questions out. No chunking, retrieval or vector search
(that is p4), no tool calling (that is p3).

## Usage

Needs [Ollama](https://ollama.com) running locally with the model pulled
(`ollama pull qwen2.5:3b`). From `p2-offline-assistant/`:

```
uv run python -m studyqa ask notes_sample/03_transformers_and_attention.md --list-sections
  1. 1. From Sequence Models to Transformers (280 words)
  2. 2. Tokens, Embeddings, and Positional Information (278 words)
  3. 3. Scaled Dot-Product Self-Attention (274 words)
  ...
  7. 7. Training, Evaluation, and Common Failure Modes (268 words)

uv run python -m studyqa ask notes_sample/03_transformers_and_attention.md --section 3
Generating 5 questions for section 3 with qwen2.5:3b (about a minute on CPU)...
Section 3/7: 3. Scaled Dot-Product Self-Attention (274 words)
Model qwen2.5:3b, constrained decoding, valid on attempt 1, 45 s, 543 tokens at 16.7 tok/s

1. [easy] What does the query, key, and value represent in self-attention?
   Answer: The query expresses what a position is seeking, the key expresses what a position offers for matching, and the value contains the information that may be passed onward.
   Source: "Self-attention transforms each input representation into a query, a key, and a value through learned linear projections. A query expresses what a position is seeking, a key expresses what a position offers for matching, and a value contains the information that may be passed onward."

2. [medium] What is the purpose of dividing the dot product scores by the square root of the key dimension?
   Answer: To keep score magnitudes in a manageable range and prevent softmax from producing small gradients for many alternatives.
   Source: "Scaling matters because dot products can grow in magnitude with vector dimension. Large logits can make softmax extremely peaked, producing small gradients for many alternatives. Dividing by the square root of the key dimension helps keep score magnitudes in a manageable range."

3. [medium] How do attention masks prevent a position from attending to certain tokens?
   Answer: A causal mask, for example, blocks future positions in an autoregressive language model so that prediction at a given position cannot use later tokens.
   Source: "Attention masks can prevent a position from attending to certain tokens. A causal mask, for example, blocks future positions in an autoregressive language model so that prediction at a given position cannot use later tokens."

4. [medium] What is the limitation of interpreting attention weights as explanations?
   Answer: A high weight indicates how the attention operation mixes values, not necessarily the full causal importance of a token to the final prediction.
   Source: "Attention weights are sometimes interpreted as explanations, but that interpretation is limited. A high weight indicates how the attention operation mixes values, not necessarily the full causal importance of a token to the final prediction."

5. [hard] What components contribute to the final prediction in addition to attention?
   Answer: Residual paths, multiple heads, feed-forward layers, and later blocks also contribute to the final prediction.
   Source: "Residual paths, multiple heads, feed-forward layers, and later blocks also contribute to the final prediction."
   ! quote not found verbatim in the section (best match 0.75)
```

(The first number is the one to pass to `--section`; these sample notes number their own
headings too.)

The output above is unedited, from one live run (2026-11-25, Ryzen 5 5600H, CPU only, Ollama
0.40.18, no other load): **45 s wall time** including loading the model, **543 generated tokens
at 16.7 tok/s** decode speed, valid on the first attempt. A second run of the same section with
`--json` took 37 s (model already loaded), 552 tokens at 15.8 tok/s. These are single runs, not
the benchmark's medians (14.8-14.9 tok/s for qwen2.5:3b over 84 generations, in a session with
more background load).

The flag on question 5 is correct: the section says "...and later blocks also contribute.";
the model appended "to the final prediction" to its "quote".

- `--json` prints only the validated JSON (`{"questions": [...]}`, the schema in `schema.py`), ASCII-escaped, so it can be piped; status lines go to stderr.
- `--model M` picks another pulled Ollama model.
- **Default model `qwen2.5:3b`** is a reliability/speed/memory choice from the benchmark below (1.00 first-try validity in both modes, highest median tok/s, lowest loaded RAM). It is **not** a claim that it writes the best questions: no model is declared best (see Results).
- Generation uses exactly the benchmarked settings: schema-constrained decoding, up to 2 retries shown the validation error, 1536-token output cap, 4096-token context.
- Errors are explicit, with exit codes 2 (file not found, not markdown, PDF, section out of range, no usable sections), 3 (Ollama not running, model not pulled, request failed) and 1 (no valid output after 3 attempts; each attempt's error is printed).
- Input is one markdown file. Sections follow the splitter rule below: a file of 1200 words or less is a single section; `--list-sections` shows skipped (too short / too long) parts with the reason. **PDF is not supported yet** (no PDF parser; the project adds no dependencies). Convert PDFs to `.md` first.
- On CPU expect roughly half a minute to a minute per section (more if the model hits the output cap and retries).

## Datasets

| Set | Source | Sections | Role |
|---|---|---|---|
| `notes_sample/` | 6 ML study-note files, **LLM-generated by ChatGPT** (not hand-written notes) | 42 | main benchmark |
| `sample_data/mdn/` | 8 MDN Web Docs pages, CC-BY-SA 2.5 ([attribution](sample_data/mdn/ATTRIBUTION.md)) | 61 eligible | public reproducibility set + 8-section smoke test |

Because the main notes are LLM-generated, they are cleaner and more uniform than
real student notes: every section is 249-319 words of well-formed prose with no
code, tables or fragments. Results may overstate quality on messy real notes.

### Section extraction

A heading's text (including its subheadings) is kept as one section if it is 150-1200
words. Only text over 1200 words is split, at its next heading level, recursively; pieces
under 150 words are dropped. So a file of 1200 words or less is **one** section even if it
has several `##` headings. `#` lines inside code fences are not headings. (Every
`notes_sample/` file is 1931-2140 words, so each splits into its seven `##` sections.)

| Set | Kept | Filtered | Why |
|---|---|---|---|
| notes_sample | 42 (7 per file) | 0 | each file's `# Title` holds no text of its own (6 empty container headings, not content) |
| MDN | 61 | 22 | all `too_short` (<150 words): "See also" link lists, empty "Specifications"/"Browser compatibility" stubs after macro removal, short intros |

Reproduce: `uv run python -m studyqa.build_dataset --notes notes_sample --n 42 --out data/notes_full.jsonl`
(the drop list with reasons is printed).

## Metrics

- **Valid on first try / valid after retries**: output parses into the Pydantic schema. Up to 2 retries, each shown the validation error.
- **Retries needed**: attempts - 1.
- **Groundedness** (lexical, per question):
  `quote_fidelity` = does `source_quote` actually appear in the section (1.0 if verbatim after normalization, else best fuzzy window match; markdown link targets and URLs are stripped first);
  `answer_support` = share of the answer's content words found in the **quote**;
  `section_support` = the same against the **whole section**.
  Grounded = `quote_fidelity >= 0.85` and `answer_support >= 0.4`.
  Thresholds were **frozen before the main run** from the 8-section MDN smoke run, with the evidence in [docs/LOG.md](docs/LOG.md); they were not tuned on the results reported below.
  Answer support is reported against both the quote and the section. Section support turned out to be near-saturated (about 1.00 for every model and mode in the smoke run: a whole section contains almost every content word an on-topic answer uses), so it is not a quality signal. It is a diagnostic: an answer that is section-supported but not quote-grounded is a *wrong quote*, not a made-up answer.
- **Failure kinds** for sections that never produce valid output: *schema* (invalid JSON or wrong shape), *runaway* (an attempt hit the 1536-token output cap), *infra error* (HTTP error or timeout).
- **Tokens/sec**: Ollama's `eval_count / eval_duration` (decode only; excludes load and prompt processing).
- **RAM**: working set of the `ollama serve` process tree above its idle baseline, split into load peak, *loaded* (after warm-up; the headline), generation peak and end of run. A single peak was misleading: loading briefly holds two copies of the weights (see LOG).
- **LLM-graded (ChatGPT)**: 20 sections per model, both modes (120 rows), paired by section, blind (the sheet carries no model or mode; the key is kept separately), 1-3 rubric. The grades were produced by ChatGPT, **not by a human**. ChatGPT also wrote the source notes, so the grader is judging questions about text it generated itself. **LLM-graded, human-validated on 30 rows:** a blind, paired 30-row subsample (10 per model, 5 sections x 2 modes) was hand-graded to measure how far the ChatGPT grades can be trusted (see Results).

`difficulty` is generated and schema-validated but **not evaluated**: there is no
ground truth for it, and the grading rubric does not score it.

## Results

42 notes sections x 3 models x 2 decoding modes, one sample each, thresholds frozen at
tau_quote = 0.85 / tau_answer = 0.4 before the run. Full tables, committed in
[`results/`](results/) (aggregates only):

- [`notes_combined_report.md`](results/notes_combined_report.md): reliability, groundedness, memory, paired mode comparisons, sensitivity grids
- [`grades_report_llm_graded__chatgpt.md`](results/grades_report_llm_graded__chatgpt.md): LLM grades (ChatGPT), 120 rows
- [`grades_report_hand_graded.md`](results/grades_report_hand_graded.md): hand grades, 30 rows
- [`agreement_vs_chatgpt.md`](results/agreement_vs_chatgpt.md): hand vs ChatGPT, row by row
- [`copy_diagnostic.md`](results/copy_diagnostic.md): copy diagnostic

Raw runs, per-question CSVs, grading sheets and keys are not committed. To regenerate the
reports, use the commands in each module's docstring (`studyqa.report`, `studyqa.grading`,
`studyqa.diagnostics`); they write to `runs/` and `grading/`, and `results/` holds copies.

**No model is declared best.** The two quality measures disagree (below), the grades are
LLM-graded (human-validated on 30 rows only), and model-vs-model grade differences are
confounded by section.

### Reliability and speed

| model | mode | valid 1st try | valid | failures (schema / runaway / infra) | sections retried | cap hits | tok/s p50 |
|---|---|---|---|---|---|---|---|
| llama3.2:3b | constrained | 1.00 | 1.00 | 0 / 0 / 0 | 0 | 0 | 13.9 |
| llama3.2:3b | json | 0.79 | 0.93 | 3 / 0 / 0 | 9 | 0 | 14.0 |
| phi3:mini | constrained | 0.95 | 0.98 | 0 / 0 / 1 | 1 | 1 | 11.6 |
| phi3:mini | json | 0.95 | 0.98 | 0 / 0 / 1 | 1 | 0 | 11.6 |
| qwen2.5:3b | constrained | 1.00 | 1.00 | 0 / 0 / 0 | 0 | 0 | 14.9 |
| qwen2.5:3b | json | 1.00 | 1.00 | 0 / 0 / 0 | 0 | 0 | 14.8 |

RAM above the idle server (MB, loaded / generation peak): llama 2448 / 4293, qwen 2055 / 2854,
phi3 3646 / 10523. phi3 ran in a separate session (see caveats), so its tok/s and RAM are not
strictly comparable with the other two.

### Constrained vs JSON decoding (paired by section, 95% bootstrap CI)

Of 12 paired comparisons (3 models x {valid first try, valid, grounded} on 42 sections, plus
3 models x LLM grade on 20 sections), two CIs exclude zero, both for llama3.2:3b:

- **First-try validity 0.79 -> 1.00** (+0.21, CI [+0.10, +0.36]). This is the one clear effect: schema-constrained decoding removed llama's JSON-mode schema failures and retries.
- **Lexical groundedness 0.82 -> 0.91** (+0.10, CI [+0.02, +0.18]), end to end (invalid outputs count as ungrounded). This is on the lexical metric that does not track the grades (next section), so it is a statement about quote copying and overlap, not established quality.

CIs are uncorrected for 12 comparisons. Every other comparison, including **all three
LLM-grade comparisons** (llama +0.00, phi3 +0.15 [-0.05, +0.35], qwen -0.03 [-0.20, +0.13] on a
0-1 scale), has a CI containing zero: **quality effects of constraining are not detectable at
this sample size** (n = 20 graded pairs per model).

### Groundedness and LLM grades disagree

| model | grounded, valid only (constrained / json) | mean LLM grade 1-3 (constrained / json) |
|---|---|---|
| llama3.2:3b | 0.91 / 0.88 | 2.05 / 2.05 |
| qwen2.5:3b | 0.88 / 0.85 | 2.35 / 2.40 |
| phi3:mini | 0.83 / 0.85 | 2.65 / 2.35 |

- **They rank the models in opposite orders.** Constrained mode: groundedness llama > qwen > phi3, grades phi3 > qwen > llama (exact reverse). JSON mode: llama is first on groundedness and last on grades; qwen and phi3 tie on groundedness (0.85).
- **Per question, they are uncorrelated:** Spearman between the LLM grade and quote fidelity -0.05, answer support -0.09, grounded@0.85/0.4 +0.05 (120 graded rows).
- **The grades are LLM-graded (ChatGPT), human-validated on 30 rows** (next sections). ChatGPT also wrote the source notes. n = 20 sections per model per mode.
- **Model-vs-model grade differences are confounded by section:** each model was graded on its own random 20 sections (pairs of models share 9-11 sections; all three share 5). Only the within-model json-vs-constrained comparisons are paired.
- The groundedness ordering is also threshold-dependent: llama is first at every grid point, but qwen and phi3 swap at tau_answer >= 0.6 (sensitivity grids in the report).

### Diagnostic: does verbatim copying explain the disagreement?

Hypothesis, written before computing: the lexical metric rewards answers copied from the
text, while the rubric's 3 requires an answer that tests understanding, so copying raises
groundedness and lowers grades. *Copy* = answer of >= 6 tokens with a best-window match
>= 0.85 (the frozen tau_quote) against its quote or the section; computed from stored outputs,
no model calls.

| model | copy share, all valid questions | grounded: copies / non-copies | copy share, graded rows | LLM grade: copies / non-copies | non-copy minus copy (grade), 95% CI |
|---|---|---|---|---|---|
| llama3.2:3b | 0.60 | 0.95 / 0.82 | 0.57 | 2.13 / 1.94 | -0.19 [-0.53, +0.15] |
| qwen2.5:3b | 0.53 | 0.92 / 0.81 | 0.47 | 2.42 / 2.33 | -0.09 [-0.49, +0.32] |
| phi3:mini | 0.51 | 0.89 / 0.79 | 0.47 | 2.47 / 2.52 | +0.05 [-0.35, +0.44] |

- **P3, copying inflates groundedness: supported.** Copied answers are grounded 0.10-0.13 more often in every model (CIs exclude 0).
- **P1, models that copy more get lower grades: consistent but weak.** The copy-share order (llama > qwen ≈ phi3) matches the reverse of the grade order, but this is 3 points, the qwen/phi3 gap is 0.02, and it is confounded by section.
- **P2, within a model, copied answers get lower grades: not supported.** No model shows it; llama's copies are graded slightly *higher*; pooled difference -0.04 [-0.27, +0.19].
- **Verdict: the hypothesis is not supported.** Copying explains part of what the lexical metric measures, but not why it disagrees with the LLM grades. Whatever the grader rewards, it is not "not copying" at the answer level.

### Human validation of the LLM grades (30 rows)

30 of the 120 ChatGPT-graded rows were hand-graded blind (10 per model: 5 sections x both
modes, seeded; drawn from the blank sheet, without seeing ChatGPT's grades), then matched to
ChatGPT's grade for the same row. 95% CIs are percentile bootstraps over rows (10,000
resamples; resamples where a statistic is undefined, e.g. all grades equal, are dropped and
counted in [`results/agreement_vs_chatgpt.md`](results/agreement_vs_chatgpt.md)).

| hand vs ChatGPT | value | 95% CI |
|---|---|---|
| weighted kappa, quadratic | 0.53 | [0.13, 0.78] |
| weighted kappa, linear | 0.46 | [0.12, 0.73] |
| Spearman rho | 0.53 | [0.17, 0.79] |
| exact agreement | 0.70 (21/30) | [0.53, 0.87] |
| mean grade (hand / ChatGPT) | 2.10 / 2.33 | |

| | ChatGPT 1 | ChatGPT 2 | ChatGPT 3 |
|---|---|---|---|
| **hand 1** | 2 | 0 | 0 |
| **hand 2** | 0 | 15 | 8 |
| **hand 3** | 0 | 1 | 4 |

- **Agreement is moderate** (quadratic-weighted kappa 0.53), with a wide CI at n = 30 (0.13-0.78).
- **ChatGPT is more lenient:** in 8 of the 9 disagreements ChatGPT gave the higher grade (hand 2 vs ChatGPT 3); it gave 12 threes to the hand grader's 5.
- **Both graders agreed on the two 1-grades.** With n = 2 that is weak evidence that ChatGPT catches clearly bad questions.
- **The lexical metrics show no detectable correlation with either grader.** Every CI contains 0:

| Spearman with the lexical metric | hand grades (n = 30) | ChatGPT grades (n = 120) |
|---|---|---|
| quote_fidelity | -0.27 [-0.62, +0.09] | -0.05 [-0.26, +0.18] |
| answer_support | -0.05 [-0.39, +0.29] | -0.09 [-0.29, +0.11] |
| grounded@0.85/0.4 | -0.09 [-0.44, +0.18] | +0.05 [-0.14, +0.24] |

- **Per model:** llama3.2:3b has the lowest mean grade from both graders (hand 1.90 vs 2.20 for the other two; ChatGPT 2.05 vs 2.375-2.50). This is a weak, small-sample signal (10 hand-graded rows per model, section-confounded), not a finding. The hand-graded per-mode comparisons (n = 5 per model) are too small to report.

- [x] Human validation: hand-grade 30 of the 120 rows blind and report agreement with ChatGPT and with the lexical metrics.

### Caveats that apply to the results

- **The phi3 runaway is not limited to long sections.** In the smoke run, phi3:mini generated without stopping (until the context filled and the prompt was discarded) on the longest MDN section, 1035 words. It also happens on a short notes section: `05-reinforcement-learning-basics--1-the-reinforcement-learning-setting` (285 words) hit the 1536-token cap in constrained mode in all three runs that reached it (the host-killed first full run, a standalone reproduction, and the final run), each time recovered by the retry. The cap turns it into a bounded, retried failure rather than a hang; the report counts it under *cap hits*, and as a *runaway* failure only if no retry recovers it.
- **phi3 ran in a separate session.** llama and qwen ran in `runs/notes_full` (started 02:05, 6.8 GB RAM available at start); phi3 ran in `runs/notes_full_phi3` (started 11:15, 9.3 GB available) after the first run was killed by the host. The commits differ (`a5ea99b` vs `c2305f0`; the change between them is diagnostics only: start lines and stall dumps), and the generation protocol (case file hash, prompt, num_ctx, num_predict, retries, seed, thresholds) is identical, which the report checks. But tok/s and RAM for phi3 are not strictly comparable with the other two.
- **Runs are single samples.** Temperature 0 with a fixed seed was not bit-reproducible on this CPU (a rerun of one section changed phi3's outcome; see LOG), so per-section results can flip between runs. Comparisons use paired bootstrap CIs over sections for that reason.
- **Notes are LLM-generated** (by ChatGPT; see Datasets), so they are cleaner than real notes.
- **Grades are LLM-graded (ChatGPT), human-validated on 30 rows.** ChatGPT both wrote the notes and graded the questions about them (which ChatGPT model, and whether the same one, is not recorded). Only 30 of 120 rows have a human grade, from a single grader, and agreement with ChatGPT is moderate.

## License

Code: MIT ([LICENSE](../LICENSE)). The MDN sample in `sample_data/mdn/` is not covered by
the MIT license; it remains CC-BY-SA 2.5 ([attribution](sample_data/mdn/ATTRIBUTION.md)).

## Failures and fixes

See [docs/LOG.md](docs/LOG.md).

## Trade-offs

| Decision | Chosen | Rejected | What it cost / bought here |
|---|---|---|---|
| Decoding | Schema-constrained (`format=<schema>`) | JSON mode + validation retries | Bought llama 0.79 -> 1.00 first-try validity at no measurable speed cost (13.9 vs 14.0 tok/s). Did not stop phi3's runaway: constrained decoding can still loop inside one string field. qwen and phi3 gained nothing measurable. |
| Output cap | `num_predict = 1536` | 1024 (proposed), or no cap | No cap: a runaway hung 10 min and context-shifted the prompt away. 1024 would have truncated a valid 1043-token phi3 answer. 1536 bounds a runaway to ~3 min per attempt, and the retry recovered it every time. |
| Retry after truncation | Tell the model it was cut off; don't echo the output | Echo the failed output with the error | Echoing a 1536-token truncation could overflow the context on retry. |
| Groundedness | Lexical (quote fidelity + content-word overlap) | LLM judge | Free, deterministic, re-computable from stored outputs (fixes needed no re-run). But it does not track the LLM grades (Spearman ~0) and rewards copying. Kept as a cheap screen for fabricated quotes, not a quality score. |
| Section-support metric | Reported | Dropped | Saturated (~1.00 everywhere), so useless as a score, but it separates "wrong quote" from "made-up answer". |
| Grades | LLM-graded (ChatGPT), 120 rows, human-validated on 30 | Hand-grading all 120 rows | Cheap and fast, and ChatGPT also wrote the notes. The 30-row check gives moderate agreement (kappa 0.53) and shows ChatGPT grading higher, so absolute LLM-grade levels run high relative to the hand grader. |
| Grading sample | Paired by section within a model | The same sections for all models | Within-model mode comparisons are clean, but model-vs-model grade comparisons are confounded by section. A shared section set (drawn from sections valid for every model in both modes) would have avoided that at almost no cost; next time, sample once for all models. |
| Samples | 1 per section | Several per section | ~3 h total on CPU. Temperature 0 is not reproducible here, so per-section results can flip; only paired CIs over 42 sections are reported. |
| Hardware | CPU only, models run one at a time | GPU, or concurrent models | Zero cost and isolated RAM numbers, but long runs: one was killed by the host for low memory, so phi3 ran in a separate session. |
