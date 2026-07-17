# Endpoint wrapper (optional feature)

This folder is a **third, optional** way to build an agent on top of the skeleton,
separate from the two main template paths:

- **Path A** — hand-author an LLM tool loop (edit `tool_schemas.py` / `tools.py` /
  `prompt.py`). See the repo `README.md`.
- **Path B** — wrap your own code as a custom-upload handler (`AgentHandler` +
  `handle_structured`). See `INTEGRATION_GUIDE.md`.
- **Endpoint wrapper (here)** — point an LLM loop at an *existing HTTP/JSON or A2A
  endpoint*. You write **no tool bodies and no handler**: the model turns each user
  request into a call to your endpoint, reads the reply, and answers.

Everything for this feature — code, tests, and docs — lives in this folder. The
rest of the skeleton references it only in passing.

## When to use it

Use the endpoint wrapper when you already have a running web service (your own or a
third party's) and just want to expose it to the network as a conversational agent,
without writing any glue code. If you have *code* rather than a running service, use
Path B. If you want the model to reason across several tools you author, use Path A.

## Quick start

```bash
python -m agent_skeleton.endpoint_wrapper \
    --card my.card.json \
    --endpoint-url https://api.example.com/run \
    --endpoint-protocol http \
    --endpoint-auth-env MY_API_TOKEN
```

- `--endpoint-url` — the service to wrap (goes in the public card; not a secret).
- `--endpoint-protocol` — `http` (POST a JSON body `{"input": request, ...payload}`)
  or `a2a` (wrap the request in an A2A JSON-RPC `message/send` envelope).
- `--endpoint-auth-env` — the **name** of an environment variable holding the auth
  token (e.g. `MY_API_TOKEN`). The token itself is read at call time and never
  stored in code, the card, or logs.

All flags also read from env vars (`AGENT_ENDPOINT_URL`, `AGENT_ENDPOINT_PROTOCOL`,
`AGENT_ENDPOINT_METHOD`, `AGENT_ENDPOINT_AUTH_ENV`).

## Building a spec in code

```python
from agent_skeleton.endpoint_wrapper import EndpointConfig, endpoint_wrapper_spec

spec = endpoint_wrapper_spec(
    name="Weather",
    endpoint=EndpointConfig(url="https://api.example.com/run", auth_env="MY_API_TOKEN"),
    description="Returns a forecast for a city.",
    io_criteria="city name in, forecast text out",
)
# hand `spec` to agent_skeleton.serve.create_app(card, spec=spec)
```

Three builders are available:

| Builder | Shape |
|---|---|
| `endpoint_wrapper_spec` | one endpoint, one generic `call_endpoint(request, payload)` tool |
| `multi_endpoint_wrapper_spec` | several endpoints, one `call_<name>` tool each — the model routes |
| `operation_wrapper_spec` | one API, one **typed** tool per operation (structured, validated args) |

## What's in this folder

| File | Role |
|---|---|
| `call_endpoint.py` | the stdlib-only HTTP/A2A caller (`EndpointConfig`, `make_call_endpoint`, typed `make_operation_tool`), secret redaction, no-redirect + size cap |
| `specs.py` | the three spec builders above |
| `prompts.py` | the system-prompt builders for each shape |
| `serve_wrapper.py` | the `python -m agent_skeleton.endpoint_wrapper` CLI |
| `tests/` | endpoint-wrapper tests (stdlib only) |

It is deliberately **dependency-free** (stdlib `urllib` only) so it runs without
`httpx` / `a2a-sdk` installed and is unit-testable without a network.
