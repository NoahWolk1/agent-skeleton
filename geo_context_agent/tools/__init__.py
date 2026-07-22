"""ZONE 4 — Tool dispatch + tool bodies.  ★ WRITE THE BODIES ★ (dispatch is copy)

Five tools, each in its own module, all plain `urllib` calls against free
public APIs (no extra pip dependency, no keys):

  * geocode.py           -> geocode_address: Nominatim, place/address -> lat/lon
  * contamination.py     -> find_contamination_sources: EPA ECHO, nearby
    regulated facilities and their compliance/violation status
  * nearby_features.py   -> find_nearby_features: Overpass API, nearby
    land-use/natural/amenity/leisure/man-made features
  * elevation.py          -> find_elevation_terrain: USGS EPQS, elevation +
    an estimated local slope at a point
  * flood_zone.py         -> find_flood_zone: FEMA NFHL, the mapped flood
    zone at a point
  * helpers.py             -> HTTP + numeric helpers used by more than one tool
  * registry.py           -> TOOL_REGISTRY + the schema/function alignment check

Worth remembering: ECHO is a regulatory record (who's permitted/regulated and
their compliance history), not a live contamination sensor; FEMA's flood zone
is a mapped designation, not a live flood forecast; and OpenStreetMap coverage
is only as good as what's been mapped. All three caveats live in prompt.py's
SYSTEM_PROMPT so the agent doesn't overclaim any of them.

This file just re-exports each tool + TOOL_REGISTRY + validate_tool_registry,
so `from .tools import ...` (or `from agent_skeleton.tools import ...`) keeps
working exactly as it did when this was a single tools.py file.
"""
from __future__ import annotations

from .contamination import find_contamination_sources
from .elevation import find_elevation_terrain
from .flood_zone import find_flood_zone
from .geocode import geocode_address
from .nearby_features import find_nearby_features
from .registry import TOOL_REGISTRY, validate_tool_registry

__all__ = [
    "TOOL_REGISTRY",
    "validate_tool_registry",
    "geocode_address",
    "find_contamination_sources",
    "find_nearby_features",
    "find_elevation_terrain",
    "find_flood_zone",
]
