"""agent_skeleton.endpoint_wrapper — OPTIONAL "wrap an external API" feature.

This is a THIRD way to build an agent, separate from the two main template paths
(A: hand-authored LLM tool loop; B: custom-upload handler). Instead of writing
tool bodies or handler code, you point an LLM loop at an existing HTTP/JSON (or
A2A) endpoint: the model translates each request into a call and reads the reply.

Everything about this feature — code, tests, and docs — lives in this folder. The
rest of the skeleton only references it in one line. See README.md here for the
full walkthrough. Serve one with:

    python -m agent_skeleton.endpoint_wrapper --card my.card.json \
        --endpoint-url https://api.example.com/run
"""
from __future__ import annotations

from .call_endpoint import (
    CALL_ENDPOINT_SCHEMA_TEMPLATE,
    EndpointConfig,
    OperationConfig,
    endpoint_tool_name,
    make_call_endpoint,
    make_operation_tool,
    operation_tool_name,
)
from .prompts import build_manager_prompt, build_operations_prompt, build_wrapper_prompt
from .specs import endpoint_wrapper_spec, multi_endpoint_wrapper_spec, operation_wrapper_spec

__all__ = [
    "EndpointConfig",
    "OperationConfig",
    "make_call_endpoint",
    "make_operation_tool",
    "endpoint_tool_name",
    "operation_tool_name",
    "CALL_ENDPOINT_SCHEMA_TEMPLATE",
    "endpoint_wrapper_spec",
    "multi_endpoint_wrapper_spec",
    "operation_wrapper_spec",
    "build_wrapper_prompt",
    "build_operations_prompt",
    "build_manager_prompt",
]
