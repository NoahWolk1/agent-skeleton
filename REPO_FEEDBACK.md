# Starter-repo feedback

Friction and defects we hit while building the GeoContext agent on the
`agent-skeleton` starter template, with reproduction and suggested fixes.

> **Where these are filed:** the upstream template (`washu-dev/agent-skeleton`)
> is behind WashU org SAML SSO, so our token couldn't open issues there. We filed
> them on our fork's tracker instead (links below); they're written to port
> straight upstream. Happy to re-file on `washu-dev/agent-skeleton` or send PRs if
> given access.

## Filed issues

| # | Severity | Title | Link |
|---|---|---|---|
| 1 | High | Path-B sibling package omitted by non-editable `pip install .` (deploy-time ImportError) | [issues/1](https://github.com/NoahWolk1/agent-skeleton/issues/1) |
| 2 | Medium | `MAX_TOOL_STEPS = 4` silently truncates the Path-A tool loop | [issues/2](https://github.com/NoahWolk1/agent-skeleton/issues/2) |
| 3 | Medium | Credential-access example inconsistent (`base.py` vs `INTEGRATION_GUIDE` §7); null-value footgun | [issues/3](https://github.com/NoahWolk1/agent-skeleton/issues/3) |

### 1. Path-B sibling package not installed by `pip install .` *(deployability)*
`pyproject.toml` maps `agent_skeleton` to `.` and lists sub-packages explicitly.
A Path-B handler that imports a sibling package it ships (our `skills/`) works
under `pip install -e .` but is **silently omitted** from a non-editable
`pip install .` unless added to `[tool.setuptools].packages`. Loaded by path from
another cwd, `from skills... import` then raises `ModuleNotFoundError` at deploy
time. **Repro / fix:** see issue #1. *(We worked around it by adding `skills` to
`packages`.)*

### 2. `MAX_TOOL_STEPS = 4` silently truncates the tool loop
Four rounds is too few for any multi-source Path-A agent, and the loop returns
partial results with no error or signal when the cap is hit. **Fix:** raise the
default and/or surface a `truncated` marker. See issue #2.

### 3. Credential-access docs inconsistent + null footgun
`base.py`'s docstring uses `creds.get("openai_api_key", {}).get("api_key")`, which
raises `AttributeError` when the credential is present-but-null; `INTEGRATION_GUIDE`
§7 uses the null-safe `(... or {}).get(...)`. **Fix:** make `base.py` match. See
issue #3. *(Our handler uses the null-safe form.)*

## Minor friction (not filed as separate issues)

- **`StarletteDeprecationWarning` on every serve.** `a2a-sdk[http-server]==0.3.2`
  imports `HTTP_413_REQUEST_ENTITY_TOO_LARGE`, which newer Starlette renamed to
  `HTTP_413_CONTENT_TOO_LARGE`, so a deprecation warning prints on import/serve.
  Cosmetic, but noisy for first-time users. Consider bumping the pin or filtering.
- **`serve-handler` doesn't load a local `.env`.** Local Path-B testing needs
  credentials exported manually (`set -a; . ./.env; set +a`); a documented note or
  optional dotenv load would smooth first-run. *(We auto-load `.env` in our
  `handler.py` as a workaround.)*
- **No pre-serve structural check for Path B.** `serve check` validates only the
  Path-A schema/function alignment; a `--file/--class` sanity check (subclass +
  `handle_structured` present) before `serve-handler` would catch typos earlier.

## What worked well
The two-path split, the frozen A2A boundary (`executor.py`/`handler_executor.py`),
the graceful `a2a-sdk`-absent degradation (engine + `serve check` run without it),
and the heartbeat/runtime-cap in `HandlerExecutor` all made a 17-skill Path-B
agent straightforward to build and test offline.
