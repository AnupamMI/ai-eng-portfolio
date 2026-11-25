# p2 failure log

Every failure found during development or benchmarking, appended in order.
Format: what broke, why, how fixed, metric before/after.

## 2026-11-25: BOM in JSONL/markdown input broke loading

- **What broke:** `bench` crashed in `load_cases` with `Invalid JSON: expected value at line 1 column 1`; the file started with a UTF-8 byte-order mark (U+FEFF).
- **Why:** PowerShell 5.1 `Set-Content -Encoding utf8` (and Notepad) write a BOM; readers used `encoding="utf-8"`, which keeps it as a character. In markdown notes the same BOM would stop YAML front matter from matching, silently giving sections the filename as their title.
- **Fix:** read with `utf-8-sig` in `evalkit.load_cases` / `load_results` and `studyqa.sections.load_notes`; regression tests for both.
- **Metric before/after:** BOM-prefixed case file: crash -> 1/1 cases loaded. BOM-prefixed note: front-matter title lost -> kept. No benchmark metrics existed yet.

## 2026-11-25: Markdown link targets under-scored verbatim quotes

- **What broke:** in the 8-section MDN smoke run (`runs/smoke_public`, commit `65dc247`), quotes that were word-for-word copies of the section scored 0.86-0.89 quote fidelity instead of 1.0.
- **Why:** MDN text contains links like ``[`hasOwnProperty`](/en-US/docs/Web/...)``. The tokenizer kept the URL, so the source token stream had `en us docs web ...` tokens the model's quote did not (or the model copied a URL the window comparison then mis-aligned on). Fidelity compares fixed-length token windows, so a few extra tokens drop the ratio below 1.
- **Fix:** `grounding.strip_links` keeps link text and drops `(url "title")` targets, `<autolinks>` and bare URLs on both sides before tokenizing (commit `c762dff`). The report now recomputes grounding from stored questions + the frozen section file (sha-checked against `meta.json`), so this fix needed no model re-run.
- **Metric before/after (same 225 smoke questions):** quotes scored exactly 1.0: 186 -> 194. Questions in [0.85, 0.95): 7 -> 2. Grounded rate at the frozen 0.85/0.4: unchanged in all 6 model x mode cells (the 8 affected quotes were already >= 0.85); at the provisional 0.9 it would have moved them. Answer support changed for 1 question.

## 2026-11-25: Peak RAM measured load spikes, not model footprint

- **What broke:** smoke run reported peak RAM above baseline of 3785 MB (llama3.2), 2517 MB (qwen2.5) and 7555 MB (phi3:mini), but Ollama's own load log gives steady allocations of about 2450 / 2120 / 3690 MB (model buffers + KV cache + compute buffer).
- **Why:** the probe kept only the maximum over the whole run. Ollama 0.40 loads with mmap disabled and repacks weights (`CPU_REPACK` buffer), briefly holding two copies; llama-server's host prompt cache can also grow across requests. One "peak" mixed load transient, steady state and cache growth. KV cache size alone differs 10x across models (qwen 144 MiB with grouped-query attention vs phi3 1536 MiB without), so ordering was right but magnitudes were not interpretable.
- **Fix:** `MemProbe` keeps the full series; `bench` marks the end of warm-up; reported phases are load peak, loaded (headline), generation peak, end of run, plus a 1 Hz CSV per model; `meta.json` records system RAM at start and available RAM before each load (commit `84db539`).
- **Metric before/after:** single number per model -> 4 phases. Not re-measured on the smoke set (per the decision to skip the 45-min re-run); first measured on the full run.

## 2026-11-25: phi3 runaway generation filled the context and hung for 10 minutes

- **What broke:** in the smoke run, phi3:mini on the longest section (`web-javascript-reference-execution-model--agent-clusters-and-memory-sharing`, 1035 words, the only one over 602 words) timed out at 600 s in **both** modes, and one more phi3 call returned HTTP 500 after 90 s. The Ollama log shows `slot context shift, n_keep = 4, n_discard = 2045 ... truncated = 1`.
- **Why:** no output cap was set. phi3 never emitted a stop token (one JSON string field kept growing, even under schema-constrained decoding), generated until the 4096-token context filled, after which llama-server shifted the context (discarding half of it, including the prompt) and kept going until the client timed out. Retries would have made it worse: each retry echoed the previous output, so a retry after a long output could itself overflow the context.
- **Fix (commits `9aae0c6`, `55cd899`):** `num_predict=1536` on every call; `done_reason` recorded per attempt; after a `length` cut-off the retry tells the model it was cut off and does **not** echo the truncated output; every retry sends the original messages plus only the latest attempt (prompt no longer grows per retry); report classifies failures as schema / runaway (hit cap) / infra error. Cap choice: in the smoke run the largest successful outputs were 615 tokens (llama), 835 (qwen) and **1043 (phi3, valid on first try)**, so the proposed 1024 would have truncated a correct answer and was rejected; the largest prompt was 2024 tokens and 2024 + 1536 = 3560 < 4096, so a capped call cannot trigger a context shift.
- **Metric before/after (phi3, that section, `runs/runaway_check`):** before: 0/2 modes valid, 1202 s total, both timeouts. After: 2/2 valid, 376 s total. Constrained: attempt 1 stopped with `done_reason=length` at exactly 1536 tokens after 251 s (context 0.83 full, no shift), retry valid at 520 tokens in 65 s. JSON: valid on first try, 511 tokens, 61 s.
- **Side finding:** at temperature 0 and a fixed seed the JSON-mode output was *not* the same as in the smoke run (it previously ran past 1536 tokens; now it stopped at 511). Greedy decoding on CPU is not bit-reproducible across runs here (thread-scheduling-dependent float reductions in llama.cpp are the likely cause; this run also had a second model loaded, see next entry). Consequence: each run is one sample, not a deterministic answer; a single rerun can flip an individual section's validity. The report's "pass 0 is canonical because quality is deterministic" comment was wrong and has been corrected.

## 2026-11-25: Live tests ran concurrently with a benchmark

- **What broke:** while the phi3 runaway check (`runs/runaway_check`) was running, the Ollama log showed extra 1.9 s `/api/chat` calls: the evalkit live test (`qwen2.5:3b`, "capital of France") ran every time the full pytest suite ran, loading a second model alongside the one being measured.
- **Why:** live tests were only skipped when Ollama was *down*, never when it was busy; nothing kept tests and benchmarks apart.
- **Fix:** `live` pytest marker on the 2 tests that call Ollama; root `addopts` deselects it (`-m 'not live'`), so they run only on `pytest -m live`.
- **Metric before/after:** phi3 decode speed in the check run 7.4-8.4 tok/s vs 9.4 tok/s median in the uncontended smoke run, so the check's timing is contaminated (its done_reason / validity results are not). The smoke run itself was not affected: the Ollama log has 55 `/api/chat` calls between 00:42 and 01:49 and the only ones under 5 s are the bench's own 3 warm-ups (00:42:33, 00:55:31, 01:08:36).

## 2026-11-25: Groundedness thresholds frozen (not a failure; recorded so they cannot drift)

Frozen at **tau_quote = 0.85, tau_answer = 0.4**, chosen on the 8-section MDN smoke run (225 questions, 3 models x 2 modes) **before** the 42-section notes run, and not to be changed after it. Grounded = `quote_fidelity >= 0.85 and answer_support >= 0.4`. Set in `bench.TAU_QUOTE/TAU_ANSWER`, `report` CLI defaults, and the `grading` Spearman column.

Evidence (quote fidelity after the link fix above):

- Distribution: 194/225 quotes are exactly 1.0; the rest spread over 0.5-0.97 with no single gap, so the boundary was set by reading the cases.
- All 7 quotes in 0.85-0.97 are verbatim except 1-3 substituted or skipped words (checked with difflib opcodes against the best source window): e.g. 0.86 *"Third-party cookies have many legitimate uses include ..."* = MDN's own sentence with "they" replaced by its referent; 0.93 joins two adjacent sentences across a skipped `Origin: <origin>` code line; 0.96 says "HTTP" where the source says "it".
- Below 0.85 are paraphrases presented as quotes: 0.82 *"third-party cookies can also be used to create a profile of a user's browsing history"* (source: "a third-party server can create a profile ..."); 0.79 *"A WeakMap object has its keys weakly held"* (source: "because WeakMap objects have their keys weakly held"); 0.78 *"In the lexical environment for add5, x is 5"* (source says it of add10, with different wording).
- Answer support 0.4-0.5 (quote verbatim) is mostly correct paraphrase, e.g. 0.43 "To observe garbage collection and perform cleanup" vs quote "register objects and be notified when they are garbage collected". Below 0.4 answers start asserting things the quote does not contain, e.g. 0.33 claims `hasOwnProperty` is "a method of the object itself" vs a quote only about inheritance.
- Sensitivity on the smoke set (grounded among valid outputs): tau_quote 0.8-0.95 moves any cell by <= 0.03 (low sensitivity). tau_answer is the sensitive one: 0.3 -> 0.5 moves cells by up to 0.18 (qwen constrained 0.75 -> 0.57), and the qwen-vs-phi3 ordering in constrained mode flips between 0.4 and 0.5. Full grids go in the README.
- Known limitation: lexical overlap rewards copying and penalizes paraphrase; whether these thresholds track quality is tested by the Spearman correlation with the hand grades, reported whatever it turns out to be.

## 2026-11-25: Full run stopped twice; second stop was silent and undiagnosable

- **What broke:** (1) the 42-section run (`runs/notes_full`) was killed by the host (Claude Code's low-memory reaper) at 03:45, 1 phi3 generation in; llama and qwen were complete (168/168). (2) The phi3-only rerun (`runs/notes_full_phi3`, started 09:05) logged only "system RAM available before load" and nothing for over an hour until stopped by hand.
- **Why (2), as far as the evidence goes:** Ollama's log shows warm-up OK (4.8 s), the first generation running normally (11-13 tok/s, 640 tokens), then `500 | 1m10s` + `cancel task` at 09:06:40 with no server-side error, which is how Ollama logs a client closing the connection, and **no further requests** from the bench. The bench's timeout is 600 s, and if it had been alive to receive a 500 it would have written an `ERR` line and continued; so the bench process was killed, interrupted or frozen at 09:06:40. No Windows crash/sleep/resource events. Root cause not determined: console output was not captured, and `log.txt` only gets progress lines written *after* a generation, so a slow phi3 section (up to 3 attempts x ~175 s at the cap) and a dead process looked identical.
- **Not the cause:** a reproduction of the bench's exact sequence (unload all, warm-up, case 0 constrained) ran fine: warm-up 3.6 s, attempt 1 hit the 1536 cap (~175 s), retry valid at 768 tokens, 249 s total. The same section hit the cap in the killed full run, so **the runaway does occur on ~280-word notes sections**, not only the 1035-word MDN one (README caveat to be corrected).
- **Fix (diagnostics, so a recurrence can be explained):** `log.txt` gets a `start <section> <mode> HH:MM:SS` line before each generation; each generation is wrapped in `faulthandler.dump_traceback_later(900 s, repeat)` so a hang dumps every thread's stack to stderr; console (stdout + stderr) is redirected to `console.txt` in the run dir with `cmd /c` (PowerShell 5.1 `*>`/`Tee-Object` write UTF-16, wrap stderr as error records, and tee would block the bench if the console is paused by a QuickEdit click). The aborted run dir was kept as `runs/notes_full_phi3_aborted`.
- **Metric before/after:** time to tell "slow" from "dead": unbounded (no signal for 60+ min) -> a start line within seconds, a stack dump at 15 min, a traceback in `console.txt` on any crash. No benchmark metric changed.

## 2026-11-25: The silent phi3 stall was a frozen console (correction to the entry above)

- **What broke:** the phi3 rerun at 09:05 stopped making progress after its first generation and stayed stopped for over an hour with no error anywhere.
- **Why:** the bench was frozen by its console window. Windows consoles in QuickEdit mode pause any process that writes to them while a selection is active (e.g. after a click in the window). `bench.log()` calls `print(..., flush=True)` **before** writing `log.txt`, so the blocked `print` kept the result line out of `log.txt` and stopped the loop from sending the next request. Ollama's log fits this: at 09:06:40 it returned a 500 for the first generation (see next point), the bench received it, then tried to print the `ERR` line and blocked.
- **Correction:** the entry above inferred that `500` + `cancel task` with no server-side error meant *the client closed the connection*. That was wrong. The final phi3 run shows Ollama returning exactly that pattern to a live client (two 500s at 1m40s-1m50s, ~1119 tokens into generation, both logged by the bench as `ERR HTTPStatusError`). So the 09:06:40 500 was server-side, and the stall that followed was the console.
- **Fix:** the rerun was started with stdout+stderr redirected to `console.txt` via `cmd /c` (nothing is written to the console window, so it cannot block the bench), plus the start lines and stall dumps from the entry above.
- **Metric before/after:** phi3 rerun: stalled after 1 of 84 generations (60+ min, no output) -> 84/84 generations in 1 h 29 min (11:15-12:44), 0 stall dumps, 0 tracebacks in `console.txt`.
- **Not fixed (open):** writing to the console before the file is still the order in `bench.log()`; with console output redirected it cannot block. The two server-side 500s (section `02-convolutional-neural-networks--1-why-convolutions-suit-images`, 295 words, both modes, phi3 only) are counted as *infra error* in the report; their cause is not diagnosed (Ollama logs no error message for them), and they were not retried.
