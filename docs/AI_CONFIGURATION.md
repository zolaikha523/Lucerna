# AI Configuration

## Default: local Ollama
`.env`: `OLLAMA_URL=http://localhost:11434/api/chat`, `OLLAMA_MODEL=gemma3:4b`. Install the model with
`ollama pull gemma3:4b`. Check it in **Settings › AI & Models › Check connection**.

| Setting | Meaning |
|---|---|
| `OLLAMA_NUM_GPU` | empty = Ollama decides; `0` = CPU only (use when GPU memory runs out) |
| `OLLAMA_TIMEOUT_SECONDS` | per call; raise for slow CPUs |
| `LLM_JSON_RETRIES` | retries when the model's JSON fails validation |
| `MAX_SEGMENTS_PER_LLM_BATCH` | segments per coding call (1 is slowest but most reliable on small models) |
| `LLM_NUM_PREDICT` | maximum output tokens |

Other models (e.g. `qwen2.5:7b`, `llama3.1:8b`) can be added as providers in AI & Models. Prompts are versioned in
`lucerna/ai/prompts.py`; the version is recorded with every AI run and on AI-created codes.

## External providers (off by default)
OpenAI-compatible endpoints can be registered but are used only when **all** hold:
1. `LUCERNA_EXTERNAL_AI_ENABLED=1` in `.env`;
2. external AI is switched on in **Privacy & System**;
3. a system administrator recorded a terms review (retention, training exclusion, contract) for that provider;
4. the project is not classified Restricted (Restricted is always blocked).
Endpoints must use HTTPS. API keys are read from an environment variable you name; they are never stored in the
database. If any condition fails, nothing is sent and the user sees why. There is no silent fallback between providers.

## What is logged
`ai_runs` stores provider, model, prompt name/version, input/output sizes, attempts, duration, status and errors — not content.
Lucerna never trains or fine-tunes models on your data.
