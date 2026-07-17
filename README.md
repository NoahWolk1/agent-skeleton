# agent_skeleton

A small, copy-to-start template for building an **A2A agent**. It hands you the
~70% of every agent that is plumbing (the LLM loop, the A2A server wiring, request
parsing, the dual-channel response) so you only write the part that is *your* agent.

There are **two main ways** to build on it:

- **Path A — an LLM tool loop.** You supply a system prompt + a set of tools; a
  frozen engine runs the model-calls-tools loop. Best when the agent's value is
  reasoning: deciding which tool to call, chaining calls, synthesizing an answer.
- **Path B — a custom handler.** You already have working code; you wrap it by
  subclassing `AgentHandler` and implementing one method. Best when you just want
  existing code reachable as an agent.

> There's also an optional third path — front an existing HTTP/API endpoint with an
> LLM loop, writing no code — in the self-contained
> [`endpoint_wrapper/`](endpoint_wrapper/README.md) subpackage.

When your agent is ready, [`HACKATHON_CHEATSHEET.md`](HACKATHON_CHEATSHEET.md) covers
what to include (README, dependencies, secrets) and how to hand it over.

---

## Install

The import package is `agent_skeleton`; this folder is `agent-skeleton`. Install it
editable so the import name resolves:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

The Path-A **engine** and the `serve check` command run on the standard library
alone — you can validate an agent without installing anything. `a2a-sdk` + `uvicorn`
(pulled by `pip install -e .`) are only needed to actually **serve**.

---

## Path A — build an LLM tool loop

Edit four "write" files; leave everything else alone:

| File | You write |
|---|---|
| `tool_schemas.py` | `TOOL_SCHEMAS` — a JSON description of each tool (OpenAI Chat Completions shape) |
| `tools.py` | one Python function per tool + the `TOOL_REGISTRY` `{name: fn}` map |
| `prompt.py` | `SYSTEM_PROMPT` + `normalize_result()` (the stable output shape) |
| `agent.card.json` | your agent's name, url, and skills |

The rules that keep a tool correct (checked for you — see below):

- each function's keyword args are named **exactly** like its schema properties;
- every **optional** property (not in `required`) has a Python default;
- each function returns a JSON-able dict.

Then verify and run:

```bash
python -m agent_skeleton.serve check       # validates schemas <-> functions (no deps, no LLM)
python -m agent_skeleton.serve serve-a2a   # runs the agent over A2A (needs a2a-sdk + uvicorn)
```

`serve check` is the safety net: it fails fast if a schema and its function
disagree, in both directions, so you never discover a mismatch at runtime.

For an LLM: set `OPENAI_API_KEY` (any non-empty placeholder for a local vLLM) and
optionally `OPENAI_BASE_URL`. Against vLLM, launch it with `--enable-auto-tool-choice
--tool-call-parser <parser>`, or the model silently stops calling tools.

### Path A without editing the template in place

If you'd rather not edit the module globals, build an `AgentSpec` in your own script:

```python
from agent_skeleton import llm_wrapper_spec
spec = llm_wrapper_spec(
    name="My Agent",
    system_prompt="You are ...",
    preset_tools=["calculator", "current_time"],   # from system_tools/preset_tools
)
# from agent_skeleton.serve import create_app, load_agent_card
# app = create_app(load_agent_card("agent.card.json"), spec=spec)  # serve under uvicorn
```

---

## Path B — wrap your own code as a handler

You do **not** rewrite your code — you add a thin adapter class:

```python
from agent_skeleton import AgentHandler, FileInput

class MyHandler(AgentHandler):
    async def handle_structured(self, user_input, files=[], context=None) -> dict:
        # ... call your real code ...
        return {"answer": "the human-readable reply"}   # "answer" is REQUIRED
```

- `user_input` is the caller's text; `files` are attached files (`.bytes`,
  `.name`, `.as_tempfile()`); declare a `context` parameter to receive per-user
  credentials.
- If your code is blocking, wrap it in `await asyncio.to_thread(...)` so the
  heartbeat keeps flowing.

Run it locally:

```bash
python -m agent_skeleton.serve serve-handler --file handler.py --class MyHandler --port 9110
```

The framework gives you, for free: A2A request parsing, base64 file decoding into
`FileInput`, a heartbeat (so long calls don't time out), a runtime cap, credential
injection, error handling, and the dual machine+human response. See
[`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md) for the full walkthrough (the six
questions to answer about your code, dependencies, credentials, and a worked example).

---

## File map — where to edit, where not to

**Write (Path A):** `tool_schemas.py`, `tools.py`, `prompt.py`, `agent.card.json`, `config.py` (defaults).
**Write (Path B):** your `handler.py` (subclass `AgentHandler`).
**Copy — the frozen plumbing, rarely edited:**

| File | Role |
|---|---|
| `llm_loop.py` | the generic Chat-Completions tool loop (`run_tool_loop`, `run_agent`) |
| `spec.py` | `AgentSpec` — prompt + tools as data; one engine serves many agents |
| `executor.py` | `SkeletonAgentExecutor` — the Path-A A2A boundary |
| `handler_executor.py` | `HandlerExecutor` — wraps any `AgentHandler` for A2A (heartbeat, runtime cap, credentials) |
| `base.py` | `AgentHandler` + `FileInput` (the Path-B contract) |
| `a2a_runtime.py` | a2a-sdk import guard + `data_part`/`text_part`/`task_updater` |
| `serve.py` | `create_app` + `check` / `serve-a2a` / `serve-handler` |

---

## How it works (concepts)

- **Stateless tool loop.** Chat Completions has no server-side memory, so the loop
  holds the whole `messages` history locally and resends it each step, appending the
  assistant's tool-call message *before* the tool results. Tool calls are read from
  the model's typed `tool_calls` field — never regex-parsed.
- **Dual-channel response.** Every reply carries a machine-readable `DataPart`
  (structured output the planner reads) *and* a human-readable text message.
- **The alignment check** (`tools.validate_tool_registry`) reconciles each tool
  schema against its function signature; it runs in `create_app` and `serve check`.
  (A tool that declares `**kwargs` opts out of the check.)

---

## Testing

```bash
python -m agent_skeleton.serve check                        # schema/function alignment (stdlib only)
python -m pytest agent_skeleton/tests -q                    # engine tests
python -m pytest agent_skeleton/endpoint_wrapper/tests -q   # optional endpoint feature
```

Because `a2a_runtime.py` degrades to a no-op when `a2a-sdk` is absent, you can import
the package, unit-test tool bodies, and run `serve check` without installing the SDK;
only serving requires it.
