# Submitting an agent

This mirrors the "what to build / what to include / how you're done" part of the
walkthrough. You build your agent one of two ways, test it locally, then hand it over
with a few required files. You write no server, protocol, or discovery code — that's
generated for you.

## 1. Pick a path and build it

- **Option A — an LLM tool loop.** Edit `tool_schemas.py`, `tools.py`, `prompt.py`,
  and `agent.card.json`. See [README.md](README.md).
- **Option B — wrap your own code.** Add a small `handler.py` that subclasses
  `AgentHandler`. See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md).

## 2. Test it locally (this is how you know you're done)

Run it until it returns the expected output — locally, before handing it over.

```bash
# Option A:
python -m agent_skeleton.serve check        # schemas <-> functions align (no LLM, no deps)
python -m agent_skeleton.serve serve-a2a    # run the agent

# Option B:
python -m agent_skeleton.serve serve-handler --file handler.py --class MyHandler --port 9110
```

**Definition of done:** it runs locally and returns a dict with an `"answer"` (Option B)
or your agent produces its final answer through the loop (Option A).

## 3. What to include when you hand it over

**A `README.md`** with:
- a plain-language description of what the agent does;
- its explicit **input/output** (what it takes, what it returns);
- the **entry-point file and class name** (for Option B) or the fact that it's a
  tool-loop agent (Option A).

**Your dependencies**, in three kinds — the second is the one that silently breaks:

| Kind | How to declare |
|---|---|
| Python packages | `requirements.txt` or a `pyproject.toml` |
| **System binaries** (pip can't install these) | list them explicitly, e.g. `tesseract-ocr`, `ffmpeg`, `poppler-utils` — only you know your code needs them |
| Hardware | note any GPU / large-RAM needs |

**Your secrets, handled safely:**
- Reference each secret by an **environment-variable name**; leave the actual values
  (and any `.env` / config file) out of what you send.
- For per-user keys, read them from `context["credentials"]` in your handler (Option B) —
  never hard-code a key. This lets each user slot in their own.

## 4. If your agent calls an LLM

- We're working on providing a shared endpoint; in the meantime use a free option or
  tunnel into a RIS compute node.
- Prefer **stateless** calls (the OpenAI Chat Completions standard) — that's what the
  template's loop uses, so the same code works against hosted OpenAI or a self-hosted
  vLLM endpoint (set `OPENAI_BASE_URL`).

## 5. Send it

Share a repo with us! 

> **Submit to:** _<owner / channel — fill in>_ · **by:** _<deadline>_

## Checklist

- [ ] Built as Option A (3 config files) or Option B (`handler.py` + your code).
- [ ] Runs locally and returns `{"answer": ...}` / a final answer.
- [ ] `README.md` with description, explicit I/O, and entry-point file + class.
- [ ] Dependencies listed — pip packages **and** any system binaries **and** hardware.
- [ ] Secrets referenced by env-var name; no keys or config files included.
- [ ] (Option A) `python -m agent_skeleton.serve check` passes.
