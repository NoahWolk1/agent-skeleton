"""System tools — reusable, pre-built tool bones a Path-A agent can be armed with.

Unlike the zone-4 tool BODIES in ``tools.py`` (the agent author's own capabilities),
these are ready-made tools a creator selects by name via ``spec.llm_wrapper_spec``.

Today this package ships the preset catalog (``calculator``, ``current_time``).

Design rules for anything added here:
  * Each tool is a ``(schema, fn)`` pair whose fn's keyword params match the schema
    properties exactly, so ``tools.validate_tool_registry`` still guards it. Do NOT
    use ``**kwargs`` — that opts out of the alignment safety net.
  * Keep dependencies minimal (stdlib where possible).
  * Secrets are read from the environment at call time, never taken from the model.
"""
from __future__ import annotations

from .preset_tools import (
    PRESET_TOOLS,
    available_preset_tools,
    resolve_preset_tools,
)

__all__ = [
    "PRESET_TOOLS",
    "available_preset_tools",
    "resolve_preset_tools",
]
