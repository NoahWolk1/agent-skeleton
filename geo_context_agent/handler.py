"""Path B entry point.

GeoContextHandler wraps the same five tools (geocode_address,
find_contamination_sources, find_nearby_features, find_elevation_terrain,
find_flood_zone) and the same system prompt that used to be wired up through
Path A's tool_schemas.py/prompt.py/serve.py flow — only the entry point
changed. tool_schemas.py, prompt.py, and the tools/ package are unchanged;
they're just consumed directly here instead of through serve.create_app()'s
Path-A wiring.

Run locally with:
    pip install -e .   # from inside geo_context_agent/, so `agent_skeleton` resolves here
    python -m agent_skeleton.serve serve-handler \\
        --file handler.py --class GeoContextHandler --card agent.card.json

NOTE: this file is loaded standalone via importlib (see serve._load_handler_class),
not as part of the package, so it must use ABSOLUTE imports (agent_skeleton.*),
not relative ones (.base) — a relative import here would fail with "attempted
relative import with no known parent package".
"""
from __future__ import annotations

import asyncio
from typing import Any

from agent_skeleton import AgentHandler, FileInput
from agent_skeleton.llm_loop import run_agent
from agent_skeleton.prompt import SYSTEM_PROMPT, normalize_result
from agent_skeleton.spec import AgentSpec
from agent_skeleton.tool_schemas import TOOL_SCHEMAS
from agent_skeleton.tools import TOOL_REGISTRY


class GeoContextHandler(AgentHandler):
    """Answers location questions about EPA contamination sources, OpenStreetMap
    zone proximity, USGS elevation/terrain, and FEMA flood zone."""

    def __init__(self, config: dict):
        super().__init__(config)
        self._spec = AgentSpec(
            name="GeoContext Agent",
            system_prompt=SYSTEM_PROMPT,
            tool_schemas=TOOL_SCHEMAS,
            tool_registry=TOOL_REGISTRY,
            normalize=normalize_result,
        )
        self._spec.validate()  # fail fast at startup, same check serve check runs

    async def handle_structured(
        self,
        user_input: str,
        files: list[FileInput] = [],
        context: dict | None = None,
    ) -> dict[str, Any]:
        # run_agent makes blocking HTTP calls (OpenAI + the tools' own urllib
        # calls) - push it to a thread so the executor's heartbeat keeps going.
        return await asyncio.to_thread(run_agent, {"prompt": user_input}, spec=self._spec)
