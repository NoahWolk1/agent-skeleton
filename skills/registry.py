"""Skill registry — one place that knows every skill, how to call it, and a
short description the orchestrator's planner uses to choose skills.

Each entry: name -> (callable, kind, description). ``kind`` tells the dispatcher
how to invoke it, since skills have different signatures:
  * "point"        -> fn(lat, lon)
  * "point_taxon"  -> fn(lat, lon, taxon=<taxon>)  (taxon optional)
  * "geocode"      -> fn(address)
  * "research"     -> fn(query, api_key=<brave_key>)

``run_skill`` is the single dispatch point the handler calls; it never raises —
a skill error comes back as an {ok: False, ...} dict, matching the contract.
"""
from __future__ import annotations

from typing import Any, Callable

from .air_quality import air_quality_at
from .construction import analyze_land_use
from .contamination import find_contamination_sources
from .elevation import find_elevation_terrain
from .flood_zone import find_flood_zone
from .geocode import geocode_address
from .inaturalist import observations_near
from .occurrences import occurrences_near
from .protected_areas import analyze_protected_area
from .proximity import find_nearby_features
from .research import brave_search
from .satellite import classify_land_cover
from .soil import soil_at_location
from .species_habitat import species_at_location
from .water import water_at_location
from .wetlands import wetlands_at
from .wildfire import fire_history_at

# name -> (function, kind, description)
SKILL_REGISTRY: dict[str, tuple[Callable[..., dict[str, Any]], str, str]] = {
    "satellite": (classify_land_cover, "point",
                  "Land cover / habitat type at the point (NLCD, satellite-derived)."),
    "construction": (analyze_land_use, "point",
                     "Human land use (OpenStreetMap) plus local regulatory zoning where available."),
    "species_habitat": (species_at_location, "point",
                        "ESA-listed species, critical habitat, and migratory birds (USFWS IPaC)."),
    "occurrences": (occurrences_near, "point_taxon",
                    "Species actually recorded nearby, or whether a named species is present (GBIF)."),
    "protected_areas": (analyze_protected_area, "point",
                        "Parks/refuges/wilderness/easements and protection (GAP) status (USGS PAD-US)."),
    "water": (water_at_location, "point",
              "Nearby streamflow gages and water-quality monitoring stations (USGS NWIS + WQP)."),
    "air_quality": (air_quality_at, "point",
                    "Current air quality / US AQI and pollutant levels (Open-Meteo, modeled)."),
    "soil": (soil_at_location, "point",
             "Soil type and properties: drainage, taxonomy, farmland class (USDA SSURGO)."),
    "wildfire": (fire_history_at, "point",
                 "Recorded wildfire history that has burned this point (NIFC perimeters)."),
    "wetlands": (wetlands_at, "point",
                 "Mapped wetland type at the point (USFWS National Wetlands Inventory)."),
    "inaturalist": (observations_near, "point",
                    "Recent research-grade species observations with photos nearby (iNaturalist)."),
    "contamination": (find_contamination_sources, "point",
                      "EPA-regulated facilities and their compliance/violation history nearby (EPA ECHO)."),
    "elevation": (find_elevation_terrain, "point",
                  "Ground elevation and an estimated local slope (USGS 3DEP)."),
    "flood_zone": (find_flood_zone, "point",
                   "FEMA-mapped flood zone at the point (FEMA NFHL)."),
    "proximity": (find_nearby_features, "point",
                  "Nearby OSM features: industrial sites, water, parks, schools, waste facilities."),
    "research": (brave_search, "research",
                 "Web / government-document search for supporting context (Brave Search; needs a key)."),
    "geocode": (geocode_address, "geocode",
                "Resolve a place name or address to coordinates (OpenStreetMap Nominatim)."),
}

# Skills that operate purely on coordinates (what the planner picks for a point).
POINT_SKILLS = [n for n, (_, kind, _) in SKILL_REGISTRY.items() if kind in ("point", "point_taxon")]


def catalog_text() -> str:
    """A compact 'name: description' catalog for the LLM planner prompt."""
    return "\n".join(f"- {name}: {desc}" for name, (_, _, desc) in SKILL_REGISTRY.items())


# Per-skill result caps applied AT THE SOURCE when the orchestrator calls a skill,
# so each skill's own count/note fields stay consistent with the list it returns
# (a few representative records + accurate totals) and the response stays compact.
_ORCH_LIMITS: dict[str, dict[str, Any]] = {
    "contamination": {"max_results": 5},
    "water": {"max_stations": 5},
    "proximity": {"max_results": 5},
    "occurrences": {"top": 5},
    "inaturalist": {"per_page": 5, "top_species": 5},
    "research": {"count": 5},
}


def run_skill(
    name: str,
    *,
    lat: float | None = None,
    lon: float | None = None,
    taxon: str | None = None,
    query: str | None = None,
    brave_key: str | None = None,
) -> dict[str, Any]:
    """Dispatch to a skill by name. Never raises — errors become {ok: False,...}."""
    entry = SKILL_REGISTRY.get(name)
    if entry is None:
        return {"ok": False, "skill": name, "error": f"unknown skill: {name}"}
    fn, kind, _ = entry
    limits = _ORCH_LIMITS.get(name, {})
    try:
        if kind == "geocode":
            return fn(query or "")
        if kind == "research":
            return fn(query or "", api_key=brave_key, **limits)
        if lat is None or lon is None:
            return {"ok": False, "skill": name, "error": "this skill requires coordinates"}
        if kind == "point_taxon" and taxon:
            return fn(lat, lon, taxon=taxon, **limits)
        return fn(lat, lon, **limits)
    except Exception as exc:  # last-resort guard; skills already handle their own errors
        return {"ok": False, "skill": name, "error": f"{type(exc).__name__}: {exc}"}
