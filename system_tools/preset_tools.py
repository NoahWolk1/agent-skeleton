"""Preset-tool catalog — built-in tools a creator can arm an LLM wrapper with.

A creator selects tools by name (e.g. ``["calculator", "current_time"]``) via
``spec.llm_wrapper_spec``; the resolver turns those names into the ``(schema, fn)``
pairs the frozen engine runs.

Each tool is defined with ``@tool`` (see ``tool_engine.py``), so its schema is DERIVED from
the typed function — the same explicit, driftless definition pattern the template
recommends for user tools. The starter set is deliberately PURE and dependency-free
(no network, no secrets, no filesystem) so it needs no security review.
"""
from __future__ import annotations

import ast
import copy
import operator
from datetime import datetime, timezone
from typing import Annotated, Any, Callable

from ..tool_engine import tool

ToolFn = Callable[..., dict[str, Any]]


# --- calculator: safe arithmetic (no eval, numbers only) ------------------

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("only numeric constants are allowed")
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) >= 1000:
            raise ValueError("exponent too large")
        return _BIN_OPS[type(node.op)](left, right)
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


@tool
def calculator(
    *,
    expression: Annotated[str, "The arithmetic expression, e.g. '2 * (3 + 4)'."],
) -> dict[str, Any]:
    """Evaluate a basic arithmetic expression (+ - * / % ** // and parentheses, numbers only)."""
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree)
    except Exception as exc:  # malformed / disallowed input -> tool error, not a crash
        return {"ok": False, "error": f"could not evaluate {expression!r}: {exc}"}
    return {"ok": True, "expression": expression, "result": result}


# --- current_time: UTC clock (no args) ------------------------------------

@tool
def current_time() -> dict[str, Any]:
    """Return the current date and time in UTC (ISO-8601 string + Unix timestamp)."""
    now = datetime.now(timezone.utc)
    return {"ok": True, "utc_iso": now.isoformat(), "unix": now.timestamp()}


# --- Catalog + resolver ---------------------------------------------------

# name -> (schema, fn). Schemas are derived by @tool; add new entries here.
PRESET_TOOLS: dict[str, tuple[dict[str, Any], ToolFn]] = {
    "calculator": (calculator._tool_schema, calculator),
    "current_time": (current_time._tool_schema, current_time),
}


def available_preset_tools() -> list[str]:
    """The names a creator may choose from."""
    return sorted(PRESET_TOOLS)


def resolve_preset_tools(
    names: list[str],
) -> tuple[list[dict[str, Any]], dict[str, ToolFn]]:
    """Turn a list of catalog names into (schemas, registry) for an AgentSpec.

    Schemas are deep-copied so callers can't mutate the shared catalog. Raises
    ValueError listing any unknown names (fail fast at spec-build time)."""
    schemas: list[dict[str, Any]] = []
    registry: dict[str, ToolFn] = {}
    unknown: list[str] = []
    for name in names:
        entry = PRESET_TOOLS.get(name)
        if entry is None:
            unknown.append(name)
            continue
        schema, fn = entry
        schemas.append(copy.deepcopy(schema))
        registry[name] = fn
    if unknown:
        raise ValueError(
            f"Unknown preset tool(s): {unknown}. Available: {available_preset_tools()}"
        )
    return schemas, registry
