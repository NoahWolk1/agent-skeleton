"""Spec builders for endpoint-wrapper agents.

These build ``AgentSpec`` objects whose tools are ``call_endpoint`` (or typed
per-operation tools) bound to an external API — the model only decides *what* to
send, never the URL/auth. They flow through the SAME frozen engine
(``agent_skeleton.llm_loop.run_tool_loop``) as every other agent; only the spec
differs. See this folder's README.md for the full picture.
"""
from __future__ import annotations

from typing import Any

from ..config import MAX_TOOL_STEPS
from ..spec import AgentSpec, ToolFn
from .call_endpoint import (
    EndpointConfig,
    OperationConfig,
    endpoint_tool_name,
    make_call_endpoint,
    make_operation_tool,
)
from .prompts import build_manager_prompt, build_operations_prompt, build_wrapper_prompt


def endpoint_wrapper_spec(
    *,
    name: str,
    endpoint: EndpointConfig,
    description: str = "",
    io_criteria: str = "",
    system_prompt: str | None = None,
    model: str | None = None,
    max_steps: int = MAX_TOOL_STEPS,
    extra_schemas: list[dict[str, Any]] | None = None,
    extra_registry: dict[str, ToolFn] | None = None,
) -> AgentSpec:
    """An LLM loop over a single ``call_endpoint`` tool bound to ``endpoint`` —
    i.e. an agent that wraps one external API. Validated before return."""
    schema, fn = make_call_endpoint(endpoint)
    schemas = [schema, *(extra_schemas or [])]
    registry: dict[str, ToolFn] = {"call_endpoint": fn, **(extra_registry or {})}

    prompt = system_prompt or build_wrapper_prompt(
        name=name,
        description=description,
        endpoint=endpoint,
        io_criteria=io_criteria,
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


def multi_endpoint_wrapper_spec(
    *,
    name: str,
    endpoints: list[EndpointConfig],
    description: str = "",
    system_prompt: str | None = None,
    model: str | None = None,
    max_steps: int = MAX_TOOL_STEPS,
    extra_schemas: list[dict[str, Any]] | None = None,
    extra_registry: dict[str, ToolFn] | None = None,
) -> AgentSpec:
    """A MANAGER spec: one LLM loop fronting several external endpoints, each its
    own ``call_<name>`` tool. Validated before return."""
    if not endpoints:
        raise ValueError("multi_endpoint_wrapper_spec requires at least one endpoint")

    schemas: list[dict[str, Any]] = []
    registry: dict[str, ToolFn] = {}
    tool_meta: list[tuple[str, EndpointConfig]] = []
    seen: set[str] = set()

    for index, endpoint in enumerate(endpoints):
        tool_name = endpoint_tool_name(endpoint.name, index)
        if tool_name in seen:  # disambiguate duplicate/empty labels
            suffix = f"_{index}"  # keep the result within the 64-char tool-name limit
            tool_name = f"{tool_name[: 64 - len(suffix)]}{suffix}"
        seen.add(tool_name)

        label = endpoint.name or tool_name
        parts = [f"Call the '{label}' endpoint."]
        if endpoint.description:
            parts.append(endpoint.description)
        parts.append(
            "Put the user's request as natural language in `request`; add optional "
            "structured fields in `payload`."
        )
        schema, fn = make_call_endpoint(endpoint, tool_name=tool_name, description=" ".join(parts))
        schemas.append(schema)
        registry[tool_name] = fn
        tool_meta.append((tool_name, endpoint))

    schemas = [*schemas, *(extra_schemas or [])]
    registry = {**registry, **(extra_registry or {})}

    prompt = system_prompt or build_manager_prompt(
        name=name, description=description, tools=tool_meta
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


def operation_wrapper_spec(
    *,
    name: str,
    base: EndpointConfig,
    operations: list[OperationConfig],
    description: str = "",
    system_prompt: str | None = None,
    model: str | None = None,
    max_steps: int = MAX_TOOL_STEPS,
    extra_schemas: list[dict[str, Any]] | None = None,
    extra_registry: dict[str, ToolFn] | None = None,
) -> AgentSpec:
    """A TYPED per-operation wrapper spec: one LLM loop over an API whose every
    operation is its own typed tool (structured, validated calls). Validated
    before return."""
    if not operations:
        raise ValueError("operation_wrapper_spec requires at least one operation")

    schemas: list[dict[str, Any]] = []
    registry: dict[str, ToolFn] = {}
    tool_meta: list[tuple[str, OperationConfig]] = []
    seen: set[str] = set()

    for index, operation in enumerate(operations):
        schema, fn = make_operation_tool(base, operation, index=index)
        tool_name = schema["function"]["name"]
        if tool_name in seen:  # disambiguate, staying within the 64-char tool-name limit
            suffix = f"_{index}"
            tool_name = f"{tool_name[: 64 - len(suffix)]}{suffix}"
            schema["function"]["name"] = tool_name
        seen.add(tool_name)
        schemas.append(schema)
        registry[tool_name] = fn
        tool_meta.append((tool_name, operation))

    schemas = [*schemas, *(extra_schemas or [])]
    registry = {**registry, **(extra_registry or {})}

    prompt = system_prompt or build_operations_prompt(
        name=name, description=description, tools=tool_meta
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
