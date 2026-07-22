"""AgentSpec — the data-driven description of ONE agent's brain.

This is the seam that lets a SINGLE engine (``llm_loop.run_tool_loop``) serve many
agents **without per-agent edits to the loop**. An ``AgentSpec`` bundles the "write"
zones — system prompt, tool schemas, tool bodies, normalize — into one object that
the executor and serve layers pass straight through. The loop core stays frozen and
generic; only the spec changes.

Why this matters: a spec is *config*, so new agents never require editing (or
copying) ``llm_loop.py`` — one engine, many specs.

Presets included here:
  * ``default_demo_spec()`` — reproduces the stock template behavior (the demo
    word_count / reverse_text tools), so anything constructed without a spec keeps
    working unchanged.
  * ``llm_wrapper_spec(...)`` — bring your own system prompt, optionally armed with
    preset tools chosen by name.

(The optional endpoint-wrapper specs — front an external API with an LLM loop —
live in the ``agent_skeleton.endpoint_wrapper`` subpackage.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .config import MAX_TOOL_STEPS

# A tool body: keyword args named exactly like its schema properties -> JSON-able dict.
ToolFn = Callable[..., dict[str, Any]]
# (raw_text, tool_log) -> stable result dict.
NormalizeFn = Callable[[str, list[dict[str, Any]]], dict[str, Any]]


@dataclass
class AgentSpec:
    """Everything the engine needs to run one agent, as data rather than code.

    ``mode`` is informational — it records which "bones" this agent uses so tooling
    can reason about control levels:
      * ``"llm"``    — LLM tool loop (the default).
      * ``"proxy"``  — no LLM; relay straight to an upstream (reserved).
      * ``"custom"`` — a hand-written executor owns the flow (reserved).
    """

    name: str
    system_prompt: str
    tool_schemas: list[dict[str, Any]] = field(default_factory=list)
    tool_registry: dict[str, ToolFn] = field(default_factory=dict)
    normalize: NormalizeFn | None = None
    model: str | None = None
    max_steps: int = MAX_TOOL_STEPS
    mode: str = "llm"

    def dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """The dispatcher handed to ``run_tool_loop`` — a dict lookup over this
        spec's registry (replaces a hand-written if/elif tool chain)."""
        fn = self.tool_registry.get(name)
        if fn is None:
            return {"ok": False, "error": f"Unknown tool: {name}"}
        return fn(**arguments)

    def run_normalize(self, raw_text: str, tool_log: list[dict[str, Any]]) -> dict[str, Any]:
        if self.normalize is not None:
            return self.normalize(raw_text, tool_log)
        from .prompt import normalize_result

        return normalize_result(raw_text, tool_log)

    def validate(self) -> None:
        """Fail fast if this spec's schemas and functions disagree. Reuses the
        same alignment check the template runs at startup."""
        from .tools import validate_tool_registry

        validate_tool_registry(self.tool_schemas, self.tool_registry)


def default_demo_spec() -> AgentSpec:
    """Reproduce the stock template behavior from the module globals.

    Keeps backward compatibility: ``run_agent`` / ``create_app`` with no spec
    behave exactly as the stock template did."""
    from .config import AGENT_NAME
    from .prompt import SYSTEM_PROMPT, normalize_result
    from .tool_schemas import TOOL_SCHEMAS
    from .tools import TOOL_REGISTRY

    return AgentSpec(
        name=AGENT_NAME,
        system_prompt=SYSTEM_PROMPT,
        tool_schemas=list(TOOL_SCHEMAS),
        tool_registry=dict(TOOL_REGISTRY),
        normalize=normalize_result,
        mode="llm",
    )


def llm_wrapper_spec(
    *,
    name: str,
    system_prompt: str,
    preset_tools: list[str] | None = None,
    model: str | None = None,
    max_steps: int = MAX_TOOL_STEPS,
    extra_schemas: list[dict[str, Any]] | None = None,
    extra_registry: dict[str, ToolFn] | None = None,
) -> AgentSpec:
    """Build a plain LLM-wrapper spec: the creator's OWN system prompt, optionally
    armed with PRESET TOOLS chosen by name from the built-in catalog
    (``system_tools/preset_tools``).

    This is the "LLM Agent" option, routed through the same frozen engine as
    everything else. With no tools it is a single LLM turn; with tools the loop lets
    the model call them and then answer. The prompt is free-form (the creator defines
    the persona/task), so ``normalize_result`` falls back to the model's raw text as
    ``answer`` when it doesn't emit JSON — any creator prompt keeps working.
    ``extra_*`` allow adding more (schema, fn) tool pairs alongside the presets.

    Validated before return, so an unknown preset-tool name or a misaligned schema
    fails here rather than at serve time."""
    from .system_tools.preset_tools import resolve_preset_tools

    schemas, registry = resolve_preset_tools(preset_tools or [])
    schemas = [*schemas, *(extra_schemas or [])]
    registry = {**registry, **(extra_registry or {})}

    prompt = system_prompt
    if schemas:
        # Nudge the model to use the tools without hijacking the creator's prompt.
        prompt = (
            f"{system_prompt}\n\n"
            "You have tools available. Call them when they help you answer, then "
            "give your final answer."
        )

    spec = AgentSpec(
        name=name,
        system_prompt=prompt,
        tool_schemas=schemas,
        tool_registry=registry,
        model=model,
        max_steps=max_steps,
        mode="llm",
    )
    spec.validate()
    return spec
