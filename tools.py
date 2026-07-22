"""ZONE — Your tools.  ★ WRITE THESE ★

Define your agent's tools here. Each tool is an ordinary typed Python function
decorated with ``@tool``.

What ``@tool`` does
-------------------
``@tool`` reads the function's SIGNATURE (parameter names, type hints, defaults)
and its DOCSTRING and DERIVES the JSON schema the LLM sees (the OpenAI "Chat
Completions" tool description). You never hand-write that JSON, and it cannot drift
from the code because it IS the code. For example::

    @tool
    def word_count(*, text: str) -> dict:            # -> tool named "word_count"
        \"\"\"Count the words in a piece of text.\"\"\"      # -> the tool's description
        ...                                          # -> parameters: {text: string, required}

Rules ``@tool`` follows: each parameter becomes a property; a parameter with no
default is ``required``; ``Annotated[T, "..."]`` supplies a parameter description;
``*args`` / ``**kwargs`` are ignored. Your function returns a JSON-able dict.

Baking configuration (auth, connections) — the ``build_tools()`` factory
------------------------------------------------------------------------
Define ALL your tools inside ``build_tools(config)``. Because the tools are created
inside that function they CLOSE OVER ``config`` — any API key, DB handle, or tenant
id in ``config`` is baked into every tool ONCE and is never shown to, or chosen by,
the LLM (it isn't a function parameter, so it never appears in the schema). Put
per-request inputs in the function parameters; put fixed configuration in ``config``.
"""
from __future__ import annotations

import inspect
import os
from typing import Annotated, Any, Callable

from .tool_engine import collect_tools, tool


# Fixed configuration for your agent. Read secrets from the environment — never
# hard-code them. Everything here is baked into your tools by build_tools(), so the
# LLM never sees it. Leave it empty if your tools need no configuration.
CONFIG: dict[str, Any] = {
    "reply_prefix": os.getenv("AGENT_REPLY_PREFIX", "[demo] "),
    # "search_api_key": os.environ["SEARCH_API_KEY"],   # e.g. a real credential
}


def build_tools(config: dict[str, Any]) -> list[Callable[..., dict[str, Any]]]:
    """Define ALL your tools here and return them as a list.

    ``config`` is captured by every tool defined below (a closure), so its values
    are baked in and invisible to the LLM. Replace these demo tools with your own;
    the ones that don't need configuration simply ignore ``config``.
    """
    reply_prefix = config["reply_prefix"]

    @tool
    def word_count(*, text: Annotated[str, "The text to measure."]) -> dict[str, Any]:
        """Count the words and characters in a piece of text."""
        return {"ok": True, "word_count": len(text.split()), "char_count": len(text)}

    @tool
    def reverse_text(
        *,
        text: Annotated[str, "The text to reverse."],
        uppercase: Annotated[bool, "If true, upper-case the reversed text."] = False,
    ) -> dict[str, Any]:
        """Reverse a piece of text, optionally upper-casing the result."""
        out = text[::-1]
        return {"ok": True, "reversed": out.upper() if uppercase else out}

    @tool(name="echo", description="Echo the text back with the agent's preset prefix.")
    def echo(*, text: Annotated[str, "The text to echo."]) -> dict[str, Any]:
        # `reply_prefix` is baked in from config — the LLM only supplies `text`.
        return {"ok": True, "result": f"{reply_prefix}{text}"}

    return [word_count, reverse_text, echo]


# Assemble the schemas + registry the engine consumes, from the tools above.
# One source of truth: the schema for each tool is derived from its function.
TOOL_SCHEMAS, TOOL_REGISTRY = collect_tools(build_tools(CONFIG))


# --- The alignment check (safety net for hand-written schemas) ------------

def validate_tool_registry(
    schemas: list[dict[str, Any]] | None = None,
    registry: dict[str, Callable[..., dict[str, Any]]] | None = None,
) -> None:
    """Fail fast if schemas and functions disagree. Called by serve.create_app.

    For ``@tool`` tools the schema is derived from the signature, so this always
    passes; it still guards any HAND-WRITTEN schema (e.g. the endpoint-wrapper
    tools) or a registry a caller assembles by hand. For every tool it checks:
      * the schema `name` has a function (and every function has a schema);
      * every schema property is a keyword parameter of the function;
      * every OPTIONAL property's parameter carries a default;
      * the function has no required parameter the schema does not declare.
    A function may declare ``**kwargs`` to opt out of the strict parameter checks.

    Raises ValueError listing ALL problems; returns None when everything aligns.
    """
    schemas = TOOL_SCHEMAS if schemas is None else schemas
    registry = TOOL_REGISTRY if registry is None else registry

    problems: list[str] = []
    schema_names: list[str] = []

    for schema in schemas:
        fn_spec = schema.get("function") or {}
        name = str(fn_spec.get("name") or "")
        if not name:
            problems.append("a schema entry is missing function.name")
            continue
        schema_names.append(name)

        params = fn_spec.get("parameters") or {}
        props = set((params.get("properties") or {}).keys())
        required = set(params.get("required") or [])

        fn = registry.get(name)
        if fn is None:
            problems.append(f"[{name}] schema has no function in TOOL_REGISTRY")
            continue

        sig = inspect.signature(fn)
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            continue  # function opts out of strict checks via **kwargs

        fn_params = {
            n: p
            for n, p in sig.parameters.items()
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }
        fn_required = {n for n, p in fn_params.items() if p.default is inspect.Parameter.empty}

        # schema -> function
        for prop in sorted(props):
            if prop not in fn_params:
                problems.append(f"[{name}] schema property '{prop}' is not a parameter of {fn.__name__}()")
        for prop in sorted(props - required):
            if prop in fn_params and fn_params[prop].default is inspect.Parameter.empty:
                problems.append(f"[{name}] optional property '{prop}' must have a default in {fn.__name__}()")
        # function -> schema
        for pname in sorted(fn_params):
            if pname not in props:
                problems.append(f"[{name}] {fn.__name__}() parameter '{pname}' is not declared in the schema")
        for pname in sorted(fn_required):
            if pname not in required:
                problems.append(f"[{name}] {fn.__name__}() requires '{pname}' but the schema does not mark it required")

    for name in registry:
        if name not in schema_names:
            problems.append(f"[{name}] function in TOOL_REGISTRY has no schema in TOOL_SCHEMAS")

    if problems:
        raise ValueError("Tool schema/function alignment failed:\n  - " + "\n  - ".join(problems))
