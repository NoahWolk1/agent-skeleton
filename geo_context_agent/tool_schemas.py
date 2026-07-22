"""ZONE 1 — Tool schemas.  ★ WRITE THIS ★

The list of tools your LLM may call, in OpenAI **Chat Completions** shape:

    {"type": "function",
     "function": {"name": ..., "description": ..., "parameters": <JSON Schema>}}

Two rules the startup check enforces (tools.validate_tool_registry):
  1. Every `name` here has a matching function in the tools/ package's TOOL_REGISTRY.
  2. The `parameters` here match that function's signature — each schema
     property is a keyword arg of the function; required properties may or may
     not have a default; OPTIONAL properties must have a default.
"""
from __future__ import annotations

from typing import Any

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "geocode_address",
            "description": (
                "Look up the latitude/longitude for a place name or address via "
                "OpenStreetMap Nominatim. Call this first if the user gave a place "
                "instead of raw coordinates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Free-form place name or address, e.g. '5700 Arsenal St, St. Louis, MO'.",
                    },
                },
                "required": ["address"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_contamination_sources",
            "description": (
                "Look up EPA-regulated facilities near a point using the EPA ECHO "
                "database - possible contamination sources under the Clean Air Act, "
                "Clean Water Act, RCRA hazardous waste, or TRI toxics programs. "
                "Returns program-level counts plus the nearest facilities with their "
                "compliance/violation status. Needs latitude/longitude, so geocode "
                "first if you only have a place name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude of the point of interest."},
                    "longitude": {"type": "number", "description": "Longitude of the point of interest."},
                    "radius_miles": {
                        "type": "number",
                        "description": "Search radius in miles around the point (default 1.0, max 50).",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of nearest facilities to return in detail (default 25, max 100).",
                    },
                },
                "required": ["latitude", "longitude"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_nearby_features",
            "description": (
                "Find what's mapped near a point in OpenStreetMap: land use "
                "(residential, industrial, farmland, forest, quarry, landfill...), "
                "natural features (water, wetland, wood, grassland...), amenities "
                "(hospitals, schools, waste facilities), parks/nature reserves, and "
                "industrial infrastructure (works, pipelines, wastewater plants). "
                "Good for 'what's nearby' or zoning-type questions, or as a rough "
                "habitat-suitability signal (near water/green space or not). Needs "
                "latitude/longitude, so geocode first if you only have a place name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude of the point of interest."},
                    "longitude": {"type": "number", "description": "Longitude of the point of interest."},
                    "radius_meters": {
                        "type": "number",
                        "description": "Search radius in meters around the point (default 500, max 5000).",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of nearest features to return in detail (default 30, max 100).",
                    },
                },
                "required": ["latitude", "longitude"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_elevation_terrain",
            "description": (
                "Look up ground elevation at a point via USGS EPQS (3DEP), plus an "
                "estimated local slope (roughly flat vs. steep). Useful for habitat/"
                "watershed context - e.g. ridge vs. valley vs. floodplain-flat "
                "terrain. Needs latitude/longitude, so geocode first if you only "
                "have a place name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude of the point of interest."},
                    "longitude": {"type": "number", "description": "Longitude of the point of interest."},
                },
                "required": ["latitude", "longitude"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_flood_zone",
            "description": (
                "Look up the FEMA-mapped flood zone at a point via the National "
                "Flood Hazard Layer - the zone code (e.g. 'X' minimal hazard, 'AE'/"
                "'A'/'VE' mapped high-risk Special Flood Hazard Area) and base "
                "flood elevation where available. Needs latitude/longitude, so "
                "geocode first if you only have a place name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {"type": "number", "description": "Latitude of the point of interest."},
                    "longitude": {"type": "number", "description": "Longitude of the point of interest."},
                },
                "required": ["latitude", "longitude"],
                "additionalProperties": False,
            },
        },
    },
]
