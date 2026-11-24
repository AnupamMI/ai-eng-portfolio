# p2: Offline study assistant

Turns one section of markdown study notes into 5 structured revision questions
(`question`, `answer`, `difficulty`, `source_quote`) with a local 3B model via
Ollama, and benchmarks `llama3.2:3b`, `qwen2.5:3b` and `phi3:mini` on CPU.

Scope: one section in, questions out. No chunking, retrieval or vector search
(that is p4), no tool calling (that is p3).

## Datasets

| Set | Source | Sections | Role |
|---|---|---|---|
| `notes_sample/` | 6 ML study-note files, **LLM-generated** (not hand-written notes) | 42 | main benchmark |
| `sample_data/mdn/` | 8 MDN Web Docs pages, CC-BY-SA 2.5 ([attribution](sample_data/mdn/ATTRIBUTION.md)) | 61 eligible | public reproducibility set + 8-section smoke test |

Because the main notes are LLM-generated, they are cleaner and more uniform than
real student notes: every section is 249-319 words of well-formed prose with no
code, tables or fragments. Results may overstate quality on messy real notes.

### Section extraction

A section is the text under one heading, split at the shallowest heading level;
sections over 1200 words are split again at their subheadings, sections under
150 words are dropped. `#` lines inside code fences are not headings.

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
- **Hand grades**: 20 sections per model, both modes (120 rows), blind, 1-3 rubric.

`difficulty` is generated and schema-validated but **not evaluated**: there is no
ground truth for it, and the hand-grading rubric does not score it.

## Results

_TBD: full run on notes_sample._

### Caveats that apply to the results

- **The phi3 runaway was seen only on the longest section.** In the smoke run, phi3:mini generated without stopping (until the context filled and the prompt was discarded) on one MDN section, the longest at 1035 words; the next-longest smoke section was 602 words. The 1536-token output cap now turns this into a fast, retried failure. The main notes sections are 249-319 words, so the runaway may not appear in the main results at all; its absence there is not evidence that phi3 is robust on long inputs.
- **Runs are single samples.** Temperature 0 with a fixed seed was not bit-reproducible on this CPU (a rerun of one section changed phi3's outcome; see LOG), so per-section results can flip between runs. Comparisons use paired bootstrap CIs over sections for that reason.
- **Notes are LLM-generated** (see Datasets), so they are cleaner than real notes.

## Failures and fixes

See [docs/LOG.md](docs/LOG.md).

## Trade-offs

_TBD._
