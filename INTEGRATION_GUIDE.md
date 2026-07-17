# Integration Guide: Turning Your Code Into an Agent

**Who this is for:** you have working code that does something useful (reads a PDF, calls an API, crunches data, runs an LLM loop) and you want to turn it into an agent — this is **Path B** of `agent_skeleton`. You don't rewrite your code; you add one small adapter, run it locally to confirm it works, and hand it over to be wrapped and ingested.

**The 30-second version:**
1. You do **not** rewrite your code. You add one small **adapter** file (conventionally `handler.py`) that exposes your existing code through a fixed shape the system understands.
2. That shape is: a class that extends `AgentHandler` and implements one method, `handle_structured(...)`, which returns a dict containing an `"answer"`.
3. You answer six questions about your code (§3) — that's the part that makes the adapter correct.
4. You run it locally with `serve-handler` (§9), then hand over your code + adapter; it gets wrapped in a web server and the planner can discover and call it.

---

## 1. The one big idea: an adapter, not a rewrite

The system can run almost *any* code — but only if that code answers the door the same way every time. Think of a **wall socket**: the plug shape is fixed, but a lamp, a laptop charger, and a fridge all plug into it. The system defines the plug shape; your agent is the appliance behind it.

That plug shape is the **`AgentHandler` contract**. Your real logic stays exactly as it is, in whatever files/packages you already have. You just add a thin adapter that says "when a request comes in, here's how to feed it to my code, and here's how to hand back the result."

```
  planner  ──►  [ the system generates: web server + A2A wiring + your Agent Card ]
                                    │
                                    ▼
                        your handler.py  (the adapter — ~15-40 lines)
                                    │  calls
                                    ▼
                        your real code   (unchanged)
```

Everything in the brackets is generated for you. You are responsible for the adapter and your code.

---

## 2. The contract (copy this and fill it in)

Your adapter must define a class that:
1. **subclasses `AgentHandler`** (imported from `agent_skeleton`), and
2. **implements** an async method **`handle_structured`** that **returns a dict containing an `"answer"` key**.

Minimal template:

```python
from agent_skeleton import AgentHandler, FileInput


class MyAgentHandler(AgentHandler):
    async def handle_structured(
        self,
        user_input: str,                       # the text the caller sent
        files: list[FileInput] = [],           # any files the caller attached
        context: dict | None = None,           # optional: per-user credentials (see §7)
    ) -> dict:
        # ... call your real code here ...
        return {"answer": "the human-readable reply"}   # "answer" is REQUIRED
```

What each piece means:

| Piece | What it is | Notes |
|---|---|---|
| `class X(AgentHandler)` | Your adapter class. | The name is up to you, but it must match the **Class name** field. |
| `user_input` | The text of the request. | Always a string (may be empty). |
| `files` | Attached files, as `FileInput` objects. | Each has `.name`, `.mime_type`, `.bytes`, and `.as_tempfile()` (writes the bytes to a temp file path and cleans up). |
| `context` | Per-user secrets + identity. | **Only** delivered if you declare this parameter. See §7. |
| return value | A `dict`. | **Must** contain `"answer"` (the human text). Any *other* keys are passed along as structured data. |

Two things the framework does for you automatically: it sends a heartbeat every ~20s so long-running work doesn't time out, and it enforces a max runtime (up to ~1 hour). You don't manage either.

---

## 3. The 6 questions to answer about YOUR code

This is the part that actually takes thought — and it's the part only *you* can answer, because it requires understanding what your code does. Answer these six before you write the adapter and the whole thing becomes fill-in-the-blanks. (Boilerplate like the class shape and file handling is the same for everyone; these six are what make *your* adapter correct.)

For each, we show the question, why it matters, and how the paper-reviewer example answered it.

### Q1. What is the entry point?
**Which single function or method in your code "does the thing"?** A project often has many callables (a library function, a class method, a command-line `main`, helper tools). Pick the one that represents the whole task.
- *Why it matters:* the adapter calls exactly this. Pick the wrong one and the agent does the wrong thing (or nothing).
- *Example:* refbot exposed `review_paper(source, focus=...)`, a `Reviewer.review()` method, and a CLI. We chose `review_paper` — it's the documented "one-call entry point."

### Q2. How do the inputs map?
**How do the incoming `user_input` (text) and `files` translate into your entry point's arguments?** Does your function want a file *path*? a URL? raw text? Which argument gets what?
- *Why it matters:* this is the #1 source of "it uploaded fine but behaves wrong." Signatures don't tell you that argument `source` wants a *path to a PDF* while the typed text should go to `focus`.
- *Example:* refbot's `review_paper(source, focus)` wants `source` as a path/URL. So: an attached PDF → written to a temp file, its **path** passed as `source`; the typed text → `focus`; a message that's just a URL → used directly as `source`.

### Q3. What is the "answer"?
**What does your entry point return, and which part of it is the human-readable reply?** An object with many fields? A string? Which field/method produces the text a person should read?
- *Why it matters:* the `"answer"` key is required and is what the user sees. Extra keys become machine-readable structured output.
- *Example:* `review_paper` returns a `Review` object; the readable form is `review.markdown()`. So `return {"answer": review.markdown()}`.

### Q4. Is your code blocking (sync) or async?
**Does your entry point block (normal functions, network calls, file parsing) or is it already `async`?**
- *Why it matters:* `handle_structured` is async. If you call blocking code directly, you freeze the agent (including its heartbeat). Wrap blocking calls in `await asyncio.to_thread(your_func, ...)`. If your function is already `async`, just `await` it.
- *Example:* `review_paper` is blocking, so: `await asyncio.to_thread(review_paper, source, focus=focus)`.

### Q5. Does it need secrets (API keys)?
**Does your code need an API key or other credential? Which one, and how do you pass it in?**
- *Why it matters:* the system can inject per-user keys, but only if you (a) declare which credential your agent needs on the form, and (b) read it from `context` (see §7). You also need to know *where in your code* the key goes.
- *Example:* refbot needs an OpenAI key, threaded through a frozen `Settings` object. So the adapter reads the injected key from `context` and builds `Settings` with it.

### Q6. What does it depend on?
**Python packages? System binaries?** List every pip package. Then ask: does anything need a *system* tool that pip can't install (e.g. `tesseract` for OCR, `ffmpeg`, `poppler`)?
- *Why it matters:* pip packages are easy (see §6). System binaries are **not expressible in pip** and must be declared separately as **System packages**, or that feature silently breaks. This is the one requirement that can't be discovered from your code at all — only you know it.
- *Example:* refbot's base features need `openai, pypdf, requests, python-dotenv` (pip). Its optional OCR path *also* needs the `tesseract` + `poppler` system binaries — if you skip those, scanned PDFs fail with "OCR is unavailable."

---

## 4. Package it: single file or zip

**Single file:** if your entire agent is one `.py` file with no imports of your own, you can paste/upload just that. The **Entry file** is `handler.py`.

**Zip (most projects):** zip your project so that, at the **top level of the archive**:
- your **entry file** sits at the root (e.g. `handler.py`),
- your importable code sits alongside it (e.g. a `refbot/` package folder),
- optionally a `pyproject.toml` or `setup.py` at the root (this lets the builder auto-install your package and its dependencies — see §6).

Rules and gotchas:
- **The entry file must be at the archive root**, not nested in a subfolder. The classic mistake: zipping a *folder* (so everything lands under `my-project/…`) instead of zipping its *contents*. Check with `unzip -l yourfile.zip` — you should see `handler.py` on its own line, not `my-project/handler.py`.
- **Reserved root names** you cannot use at the top level: `agent_skeleton/`, `Dockerfile`, and any `*.card.json` — the system generates those.
- **Exclude junk:** `.venv/`, `__pycache__/`, `.DS_Store`, `*.egg-info/`, and anything with secrets (`.env`).
- **Size/safety limits:** archives that are too large (default caps around ~2000 files / ~25 MB uncompressed), contain symlinks, or try to escape the folder are rejected before anything is written.

---

## 5. What to hand over (the details we need)

These are the details whoever wraps your agent needs from you — they map onto a handler plus its config.

| Field | What to put | Why / notes |
|---|---|---|
| **Handler type** | `Custom (Python)` | This is the uploaded-code path. Requires admin approval. |
| **Name** | A clear, unique agent name | Drives the directory entry and image name; must be unique. |
| **Description** | One or two sentences on what it does | Helps the planner and users understand it. |
| **Class name** | The exact class name in your entry file | Must match a class that `extends AgentHandler` (from Q1/§2). |
| **Python version** | The version your code needs (e.g. `3.12`) | ⚠️ If your `pyproject.toml` says `requires-python = ">=3.12"`, you **must** pick 3.12 or install fails. |
| **Requirements** | Comma-separated pip packages | Optional if you ship a `pyproject.toml` (see §6). e.g. `openai, pypdf`. |
| **System packages** | Comma-separated apt packages | For system binaries pip can't install (from Q6), e.g. `tesseract-ocr, poppler-utils`. Cluster build only; flagged for admin review. |
| **Code upload** | Your single file or `.zip` | The entry file must sit at the archive root. |
| **Entry file** | The filename holding your class | Usually `handler.py`. Must exist at the zip root. |
| **Required credentials** | The credential types your agent needs | e.g. `openai_api_key`. Users supply the value in Settings and grant it per-agent; it arrives in `context` (§7). |
| **Extra config (JSON)** | Optional JSON | Passed to your handler's `__init__` as `self.config` — for non-secret settings. |
| **OASF Skills** | At least one skill describing what it does | Used so the planner can *find* your agent by capability (§8). |

---

## 6. Dependencies, three layers

1. **Pip packages (easy).** Either list them in the **Requirements** field, *or* — better — include a `pyproject.toml`/`setup.py` at your zip root. If build metadata is present, the system runs `pip install .`, which installs your package **and** its declared dependencies automatically.
2. **System packages (apt).** Things pip cannot install — `tesseract`, `poppler`, `ffmpeg`, image/codec libraries. Put them in **System packages**. Without them, any code path that shells out to those tools will fail at runtime even though the upload "succeeded."
3. **The trap:** if a dependency is *optional* in your code (imported lazily inside a function) and needs a system binary, nothing can detect it automatically. Only you know it's needed. Declare it, or document that the feature is off.

---

## 7. Credentials (API keys)

The system can hand your agent per-user secrets safely, but it's **opt-in**:

1. On the form, add the credential type under **Required credentials** (e.g. `openai_api_key`).
2. In your adapter, **declare the `context` parameter** and read the key from it:

```python
async def handle_structured(self, user_input, files=[], context=None) -> dict:
    creds = (context or {}).get("credentials", {}) or {}
    api_key = (creds.get("openai_api_key") or {}).get("api_key")
    # ... pass api_key into your code ...
```

If you don't declare `context`, no credentials are injected. `context` also carries `user_id`. Never hard-code secrets in your uploaded code.

---

## 8. OASF Skills (so you can be found)

The planner discovers agents **by capability**, not by name. The OASF skills you pick are how it knows "this agent can review papers / answer questions / summarize text." Pick at least one that honestly describes what your agent does. This is a judgement call about *behavior* — no tool can infer it from your code, which is why the form asks you.

---

## 9. Run it locally, then hand it over

Test your handler locally **before** handing it over — this catches the Q2/Q3/Q4/Q6 mistakes that otherwise only surface at runtime:

```bash
python -m agent_skeleton.serve serve-handler --file handler.py --class MyAgentHandler --port 9110
```

That wraps your handler in the same A2A server the deployment uses (heartbeat, runtime cap, file decoding, credentials) and serves it locally. Send it a test request and confirm it returns a dict with an `"answer"`. Then hand over your code + adapter to whoever operates the deployment; because custom code runs real Python, expect a human review before it goes live.

---

## 10. Troubleshooting (exact errors → fixes)

| Message | Cause | Fix |
|---|---|---|
| `Class 'X' not found in file` | Class name field doesn't match a class in the entry file | Make them match exactly. |
| `Class 'X' must extend AgentHandler` | Your class doesn't (directly) subclass `AgentHandler` | Write `class X(AgentHandler):` — inherit it directly, not via an intermediate class. |
| `Class 'X' must define handle_structured()` | No such method | Add `async def handle_structured(self, user_input, files=[], context=None)`. |
| `Entry file 'handler.py' not found at the archive root` | Your file is nested (you zipped a folder), or named differently | Re-zip the folder *contents*, or set Entry file to the real name/path. |
| `File is not valid UTF-8 text` | Uploaded a binary as a single file | Upload a `.py` or a proper `.zip`. |
| Upload OK, but the agent errors/behaves wrong at runtime | Usually Q2 (input mapping), Q4 (blocking call), or Q6 (missing system package) | Re-check those three. |
| A feature silently doesn't work (e.g. OCR) | Missing **System packages** | Add the apt package(s) and re-register. |
| `pip` refuses to install your project | **Python version** doesn't meet your `requires-python` | Set the Python version field to match. |

Note on the structural check: it verifies your class *by name* — it does not run your code or check that `handle_structured` returns the right shape. Those are enforced when the agent actually runs, so test your `handle_structured` returns `{"answer": ...}` locally first.

---

## 11. Final checklist

- [ ] Wrote an adapter class extending `AgentHandler` with `async handle_structured(...) -> {"answer": ...}`.
- [ ] Answered the 6 questions (entry point, input mapping, output→answer, sync/async, credentials, dependencies).
- [ ] Entry file is at the **root** of the zip, next to your importable code.
- [ ] Excluded `.venv/`, caches, `.DS_Store`, secrets.
- [ ] Requirements listed (or `pyproject.toml` shipped); **System packages** declared for any non-pip tools.
- [ ] Python version matches your code's `requires-python`.
- [ ] Declared any credentials on the form **and** read them from `context`.
- [ ] Picked at least one OASF skill.

---

## Appendix — A complete worked example (paper reviewer)

Existing code: a Python package `refbot` with a one-call entry point `review_paper(source, focus=None) -> Review`, where `Review.markdown()` is the readable output, and it needs an OpenAI key.

**The adapter (`handler.py`, at the zip root):**

```python
from __future__ import annotations

import asyncio
from dataclasses import replace

from agent_skeleton import AgentHandler, FileInput
from refbot import Settings, review_paper


class PaperReviewerHandler(AgentHandler):
    async def handle_structured(self, user_input, files=[], context=None) -> dict:
        focus = (user_input or "").strip() or "general review"
        settings = self._settings(context)                       # Q5: credentials
        if files:                                                # Q2: file -> temp path as `source`
            with files[0].as_tempfile(suffix=".pdf") as path:
                review = await asyncio.to_thread(                # Q4: blocking -> thread
                    review_paper, str(path), focus=focus, settings=settings, narrate=False)
        elif user_input.strip().startswith(("http://", "https://")):
            review = await asyncio.to_thread(
                review_paper, user_input.strip(), settings=settings, narrate=False)
        else:
            return {"answer": "Attach a PDF or send a paper link to review."}
        return {"answer": review.markdown()}                     # Q3: markdown() is the answer

    @staticmethod
    def _settings(context):
        settings = Settings.from_env()
        api_key = ((context or {}).get("credentials", {}).get("openai_api_key") or {}).get("api_key")
        return replace(settings, api_key=api_key) if api_key else settings
```

**Zip contents (all at root):** `handler.py`, `pyproject.toml`, `refbot/`.

**Form values:**

| Field | Value |
|---|---|
| Handler type | Custom (Python) |
| Name | Paper Reviewer Agent |
| Description | Reads a PDF academic paper (or a link) and returns a structured review. |
| Class name | `PaperReviewerHandler` |
| Python version | `3.12` (refbot requires ≥3.12) |
| Requirements | *(empty — the shipped `pyproject.toml` installs `openai, pypdf, requests, python-dotenv`)* |
| System packages | *(empty for text PDFs; `tesseract-ocr, poppler-utils` if you want OCR of scanned PDFs)* |
| Entry file | `handler.py` |
| Required credentials | `openai_api_key` |
| OASF Skills | pick relevant `nlp/*` skills (summarization, question answering, …) |

Notice how short the adapter is: the class shape, `as_tempfile`, `asyncio.to_thread`, and the `{"answer": ...}` envelope are the same for everyone (boilerplate). The only lines that required understanding *refbot* are the six labeled decisions. That's the whole job.
