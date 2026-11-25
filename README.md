# AI engineering portfolio

Small, measured AI engineering projects. Each one ends with a before/after measurement,
at least one documented failure and its fix, and a README with the trade-offs. Everything
runs locally at zero cost (Ollama on CPU).

| Project | What it is | Status |
|---|---|---|
| [`shared/evalkit`](shared/evalkit/) | Shared eval code: case/result schema, runner, scorers, paired bootstrap comparisons, agreement statistics, a minimal Ollama client with Pydantic-validated structured output | used by p2 |
| [`p2-offline-assistant`](p2-offline-assistant/) | Study notes section in, structured revision questions out; benchmarks `llama3.2:3b`, `qwen2.5:3b` and `phi3:mini`, constrained vs JSON-mode decoding | done: [README](p2-offline-assistant/README.md), [failure log](p2-offline-assistant/docs/LOG.md), [results](p2-offline-assistant/results/) |
| p1-text2sql, p3-mcp-server, p4-rag-evals, p5-code-reviewer | | planned |

## Setup

Python 3.11+ and [uv](https://docs.astral.sh/uv/). The repo is a uv workspace:

```
uv sync
uv run pytest            # unit tests; tests that need a live Ollama server are skipped
uv run pytest -m live    # only those (needs Ollama at localhost:11434)
```

## License

MIT ([LICENSE](LICENSE)), except `p2-offline-assistant/sample_data/mdn/`, which is
CC-BY-SA 2.5 (MDN Web Docs).
