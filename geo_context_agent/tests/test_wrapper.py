"""Tests for the spec-driven engine (AgentSpec + the frozen tool loop).

Deliberately dependency-free: stdlib only (no a2a-sdk, no openai, no network). Run:

    python -m pytest agent_skeleton/tests -q
    # or, without pytest:
    python -m agent_skeleton.tests.test_wrapper
"""
from __future__ import annotations

from agent_skeleton import llm_loop
from agent_skeleton.spec import AgentSpec, default_demo_spec


def _noop_spec() -> AgentSpec:
    """A minimal, self-contained spec: one no-arg tool, aligned schema."""
    schema = {
        "type": "function",
        "function": {
            "name": "noop",
            "description": "Does nothing; returns ok.",
            "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        },
    }

    def noop() -> dict:
        return {"ok": True}

    return AgentSpec(name="W", system_prompt="hi", tool_schemas=[schema], tool_registry={"noop": noop})


def test_default_demo_spec_backward_compatible():
    demo = default_demo_spec()
    demo.validate()
    assert demo.dispatch("word_count", {"text": "a b c"})["word_count"] == 3


def test_agent_spec_dispatch_and_validate():
    spec = _noop_spec()
    spec.validate()  # aligned schema <-> signature
    assert spec.dispatch("noop", {})["ok"] is True
    assert spec.dispatch("missing", {})["ok"] is False  # unknown tool is graceful


def test_run_agent_threads_spec_through_frozen_loop():
    seen: dict = {}

    def fake_loop(*, model, system_prompt, user_payload, tool_schemas, dispatch, max_steps):
        seen.update(model=model, names=[s["function"]["name"] for s in tool_schemas], max_steps=max_steps)
        dispatch("noop", {})  # exercise dispatch wiring
        return '{"answer": "done", "tools_used": ["noop"]}', [{"name": "noop"}]

    spec = _noop_spec()
    orig = llm_loop.run_tool_loop
    llm_loop.run_tool_loop = fake_loop
    try:
        result = llm_loop.run_agent({"prompt": "hi"}, spec=spec, model="m1")
    finally:
        llm_loop.run_tool_loop = orig
    assert seen["model"] == "m1" and seen["names"] == ["noop"]
    assert result["answer"] == "done" and result["tools_used"] == ["noop"]
    assert result["response_text"] == "done"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok {fn.__name__}")
    print(f"ALL {len(fns)} PASSED")


if __name__ == "__main__":
    _run_all()
