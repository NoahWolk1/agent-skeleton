"""Definitional tools — derive an LLM tool's schema from a typed Python function.

Write ONE typed function and decorate it with ``@tool``. The Chat Completions
schema the model sees is DERIVED from the function's signature + type hints +
docstring, so the schema can never drift from the code — there is no separate
JSON schema to hand-write and keep in sync.

Closures / baking configuration:
    Because the schema is built from the function's DECLARED parameters, a tool
    defined inside a factory exposes ONLY those parameters to the model. Anything
    captured in the enclosing scope — an API key, a DB handle, a tenant id — is
    baked in once and is never shown to, or chosen by, the LLM:

        def make_search_tool(api_key: str):
            @tool(name="web_search")
            def web_search(*, query: str, max_results: int = 5) -> dict:
                # `api_key` is baked in via the closure; the model only sets
                # `query` / `max_results`.
                return _search(query, max_results, api_key=api_key)
            return web_search

Type mapping (Python -> JSON Schema): str->string, int->integer, float->number,
bool->boolean, list[...]->array, dict->object; anything else falls back to string.
Use ``Annotated[T, "description"]`` to document a parameter, or
``Annotated[T, {..fragment..}]`` to supply a verbatim JSON-Schema fragment for a
richer shape (enums, nested objects). A parameter without a default is `required`.

Stdlib only — no pydantic, so a copied agent runs without extra dependencies.
"""
from __future__ import annotations

import inspect
import types
import typing
from typing import Annotated, Any, Callable, get_args, get_origin, get_type_hints

# A tool body: keyword args named like its schema properties -> JSON-able dict.
ToolFn = Callable[..., dict[str, Any]]

_TYPE_TO_JSON: dict[Any, str] = {
    str: "string", int: "integer", float: "number", bool: "boolean",
    list: "array", dict: "object",
    # string fallbacks (used only if type hints could not be resolved)
    "str": "string", "int": "integer", "float": "number", "bool": "boolean",
    "list": "array", "dict": "object",
}


def _unwrap_optional(annotation: Any) -> Any:
    """Return ``T`` for ``Optional[T]`` / ``T | None``; otherwise unchanged."""
    origin = get_origin(annotation)
    if origin is typing.Union or (hasattr(types, "UnionType") and origin is types.UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _property_schema(annotation: Any) -> dict[str, Any]:
    """Map one parameter annotation to a JSON-Schema property dict."""
    description: str | None = None
    fragment: dict[str, Any] | None = None
    if get_origin(annotation) is Annotated:
        base, *meta = get_args(annotation)
        for m in meta:
            if isinstance(m, str) and description is None:
                description = m
            elif isinstance(m, dict) and fragment is None:
                fragment = dict(m)
        annotation = base
    if fragment is not None:  # advanced escape hatch: verbatim JSON-Schema fragment
        if description and "description" not in fragment:
            fragment["description"] = description
        return fragment

    annotation = _unwrap_optional(annotation)
    origin = get_origin(annotation)
    prop: dict[str, Any] = {}
    if origin in (list, tuple) or annotation in (list, "list"):
        prop["type"] = "array"
        args = get_args(annotation)
        if args:
            prop["items"] = _property_schema(args[0])
    else:
        prop["type"] = _TYPE_TO_JSON.get(annotation, "string")
    if description:
        prop["description"] = description
    return prop


def derive_tool_schema(
    fn: ToolFn, *, name: str | None = None, description: str | None = None
) -> dict[str, Any]:
    """Build the Chat Completions schema for ``fn`` from its signature.

    Every declared keyword/positional parameter becomes a property; a parameter
    with no default is marked ``required``. ``*args`` / ``**kwargs`` are ignored
    (so a ``**kwargs`` tool exposes no fixed properties). The function name and
    docstring supply the tool name and description unless overridden.
    """
    sig = inspect.signature(fn)
    try:
        hints = get_type_hints(fn, include_extras=True)
    except Exception:
        hints = {}

    properties: dict[str, Any] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue
        annotation = hints.get(pname, param.annotation)
        if annotation is inspect.Parameter.empty:
            annotation = str
        properties[pname] = _property_schema(annotation)
        if param.default is inspect.Parameter.empty:
            required.append(pname)

    tool_name = name or getattr(fn, "__name__", "tool")
    doc = description
    if not doc:
        raw = (inspect.getdoc(fn) or "").strip()
        doc = raw.split("\n", 1)[0] if raw else tool_name

    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": doc,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def tool(
    fn: ToolFn | None = None, *, name: str | None = None, description: str | None = None
) -> Any:
    """Decorator: attach a derived Chat Completions schema to ``fn``.

    Usage: ``@tool`` or ``@tool(name=..., description=...)``. Returns the function
    unchanged (still directly callable) with a ``._tool_schema`` attribute set.
    """
    def wrap(f: ToolFn) -> ToolFn:
        f._tool_schema = derive_tool_schema(f, name=name, description=description)  # type: ignore[attr-defined]
        f._is_tool = True  # type: ignore[attr-defined]
        return f

    return wrap if fn is None else wrap(fn)


def tool_schema(fn: ToolFn) -> dict[str, Any]:
    """Return the schema attached by ``@tool`` (deriving it on the fly if absent)."""
    return getattr(fn, "_tool_schema", None) or derive_tool_schema(fn)


def collect_tools(fns: list[ToolFn]) -> tuple[list[dict[str, Any]], dict[str, ToolFn]]:
    """Turn a list of ``@tool`` functions into ``(TOOL_SCHEMAS, TOOL_REGISTRY)``.

    The schema list and the ``{name: fn}`` registry are exactly what an
    ``AgentSpec`` (and the frozen engine) consume. Raises on a duplicate name.
    """
    schemas: list[dict[str, Any]] = []
    registry: dict[str, ToolFn] = {}
    for f in fns:
        schema = tool_schema(f)
        name = schema["function"]["name"]
        if name in registry:
            raise ValueError(f"duplicate tool name: {name!r}")
        schemas.append(schema)
        registry[name] = f
    return schemas, registry
