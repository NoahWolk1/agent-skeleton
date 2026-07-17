# CLAUDE.md — agent_skeleton

Working notes for anyone (human or Claude) editing **inside this template**. For the
walkthrough see [`README.md`](README.md); for the Path-B deep dive see
[`INTEGRATION_GUIDE.md`](INTEGRATION_GUIDE.md); for the optional endpoint feature see
[`endpoint_wrapper/README.md`](endpoint_wrapper/README.md).

---

## 1. What this is

A small, self-contained template for building an **A2A agent**. It isolates the
~70% of every agent that is plumbing into "copy, don't edit" files, and the ~30%
that is the actual agent into a few "write" files. It offers two build paths (plus
one optional third), all driven by one frozen engine:

- **Path A** — a hand-authored LLM tool loop (`tool_schemas.py` + `tools.py` +
  `prompt.py`), run by `llm_loop.run_tool_loop`.
- **Path B** — a custom handler: subclass `AgentHandler` and implement
  `handle_structured`, run by `HandlerExecutor`.
- **Optional** — the `endpoint_wrapper/` subpackage: front an existing HTTP/API
  endpoint with an LLM loop, no code. Fully self-contained (code, tests, docs).

## 2. The two contracts

| Contract | Role | Here |
|---|---|---|
| **Agent Card** (`agent.card.json`) | identity + skills + endpoint | `a2a-sdk` `AgentCard` model, loaded by `serve.load_agent_card` |
| **A2A** | the actual call (HTTP/JSON-RPC) | `SkeletonAgentExecutor.execute()` (Path A) / `HandlerExecutor.execute()` (Path B) |

(Publishing a card into a directory so a planner can *discover* it is a deployment
concern, out of scope for this template.)

## 3. File map — where to edit, where not to

**Path A — the tool-loop engine:**

| File | Status | Notes |
|---|---|---|
| `tool_schemas.py` | **WRITE** | `TOOL_SCHEMAS`: Chat Completions shape |
| `prompt.py` | **WRITE** | `SYSTEM_PROMPT` + `normalize_result()` |
| `tools.py` | **WRITE bodies** | tool fns + `TOOL_REGISTRY` + `validate_tool_registry()` |
| `agent.card.json` | **WRITE** | skills, url, version |
| `config.py` | edit defaults | name, host/port, model |
| `llm_loop.py` | copy | generic loop; `run_agent()` wires prompt/tools/dispatch |
| `spec.py` | copy | `AgentSpec` seam (prompt+tools as data) + `default_demo_spec` + `llm_wrapper_spec` |
| `executor.py` | copy | `SkeletonAgentExecutor.execute()` + A2A I/O |
| `serve.py` | copy | `create_app`, CLI (`check` / `serve-a2a` / `serve-handler`) |
| `a2a_runtime.py` | copy | SDK import guard + `data_part`/`text_part`/`task_updater` |

**Path B — custom handler:**

| File | Status | Notes |
|---|---|---|
| `base.py` | copy | `AgentHandler` (subclass + `handle_structured()`) + `FileInput` |
| `handler_executor.py` | copy | `HandlerExecutor` — wraps any `AgentHandler` in A2A (heartbeat, runtime cap, credential context) |

**Separation of concerns to preserve:** `executor.py` / `handler_executor.py` are the
*only* files that know about A2A; `llm_loop.py` + `tools.py` + `prompt.py` are the
engine and know nothing about A2A. Keep it that way — it's what lets you unit-test the
engine and run `serve check` with no network and no `a2a-sdk` installed.

## 4. How to add a tool (Path A)

1. Add a schema to `TOOL_SCHEMAS` in `tool_schemas.py`.
2. Write the function in `tools.py` with **keyword args named exactly like the
   schema properties**; optional properties must have a default.
3. Add it to `TOOL_REGISTRY`.
4. `python -m agent_skeleton.serve check` — confirms schema and function agree
   before you ever serve.

## 5. The alignment check (and making drift impossible)

`validate_tool_registry()` (in `tools.py`) verifies name coverage (both directions),
property↔parameter correspondence, and that optional properties have defaults. It runs
in `create_app()` and as `serve check`.

**Stronger option — make drift impossible:** instead of hand-writing `TOOL_SCHEMAS`
*and* the function and checking they match, generate the schema *from* a typed function
(introspect type hints + docstring, or a `pydantic` model → `model_json_schema()`).
Then there is one source of truth and the schema cannot disagree. The current check is
the cheaper belt-and-suspenders version; both can coexist.

## 6. Gotchas

- **Dummy key guard:** `OPENAI_API_KEY` must be non-empty even for vLLM; set a
  placeholder.
- **vLLM tool calling needs launch flags:** `--enable-auto-tool-choice
  --tool-call-parser <parser>`, or the model silently stops calling tools.
- **Model-name matching:** raw OpenAI clients send the model string verbatim; it must
  equal vLLM's `--served-model-name`.
- **Step cap:** the loop is bounded by `MAX_TOOL_STEPS` (`config.py`); a task needing
  more rounds is truncated.
- **Blocking handlers (Path B):** a blocking call freezes the heartbeat — wrap it in
  `await asyncio.to_thread(...)`.
- **No auth:** the served app binds `0.0.0.0` with empty `securitySchemes` — fine for
  local dev, not for exposure.
- **Import name:** the folder is `agent-skeleton`, the package is `agent_skeleton`;
  `pip install -e .` (package-dir maps `agent_skeleton` to `.`) so imports resolve.

## 7. Testing

```bash
python -m agent_skeleton.serve check                        # schema/function alignment (stdlib only)
python -m pytest agent_skeleton/tests -q                    # engine tests
python -m pytest agent_skeleton/endpoint_wrapper/tests -q   # optional endpoint feature
python -m py_compile agent_skeleton/*.py                    # syntax
```

Because `executor.py`/`serve.py` degrade gracefully when `a2a-sdk` is missing (the
base class becomes `object`), you can import and test the engine and the alignment
check without the SDK; only *serving* requires it.
