# Portfolio: 5 AI engineering projects
Goal: each project must end with (1) a measured before/after result, (2) at least one documented failure + fix, (3) a README with trade-offs.

## Rules
- Python 3.11+, uv or venv, Pydantic for all structured output, pytest for tests.
- Shared eval code lives in shared/evalkit and is reused across projects; don't duplicate it.
- Before writing any non-trivial code, explain the design choice and the alternative you rejected in 2-3 lines. I need to defend these in interviews.
- Never silently fix a failure. Append it to the project's docs/LOG.md: what broke, why, how fixed, metric before/after.
- Keep costs at zero: local Ollama or free-tier APIs only.
- Small commits, one logical change each.

## Layout
shared/evalkit, p2-offline-assistant, p1-text2sql, p4-rag-evals, p3-mcp-server, p5-code-reviewer

## Environment
- Windows 11, Python 3.12, uv available.
- Ollama 0.40.18 at http://localhost:11434 with models: llama3.2:3b, qwen2.5:3b, phi3:mini.
