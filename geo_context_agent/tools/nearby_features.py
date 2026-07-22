"""find_nearby_features -> Overpass API, nearby land-use/natural/amenity/
leisure/man-made features.

OpenStreetMap coverage is only as good as what's been mapped - see
prompt.py's SYSTEM_PROMPT for how the agent is told to frame that.
"""
from __future__ import annotations

import urllib.error
from typing import Any

from ..config import OVERPASS_URL
from .helpers import _as_float, _haversine_meters, _http_post_json

# Tag values worth surfacing for a proximity/zoning read. Deliberately not
# matching any-value tags like natural=tree or leisure=garden - in a dense
# city those show up by the thousand (every street tree, every planter) and
# just bury anything actually useful.
_LANDUSE_VALUES = (
    "residential", "industrial", "commercial", "retail", "farmland", "forest",
    "quarry", "landfill", "brownfield", "cemetery",
)
_NATURAL_VALUES = ("water", "wetland", "wood", "scrub", "grassland", "beach")
_AMENITY_VALUES = (
    "hospital", "school", "waste_transfer_station", "fuel", "waste_disposal",
    "recycling", "fire_station",
)
_LEISURE_VALUES = ("park", "nature_reserve")
_MAN_MADE_VALUES = ("works", "wastewater_plant", "water_works", "pipeline", "storage_tank")

_TAG_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("landuse", _LANDUSE_VALUES),
    ("natural", _NATURAL_VALUES),
    ("amenity", _AMENITY_VALUES),
    ("leisure", _LEISURE_VALUES),
    ("man_made", _MAN_MADE_VALUES),
)


def _build_overpass_query(latitude: float, longitude: float, radius_meters: float) -> str:
    clauses = []
    for key, values in _TAG_CATEGORIES:
        value_regex = "^(" + "|".join(values) + ")$"
        for element in ("node", "way"):
            clauses.append(f'{element}(around:{radius_meters},{latitude},{longitude})["{key}"~"{value_regex}"];')
    return "[out:json][timeout:25];\n(\n  " + "\n  ".join(clauses) + "\n);\nout center tags;"


def find_nearby_features(
    *,
    latitude: float,
    longitude: float,
    radius_meters: float = 500.0,
    max_results: int = 30,
) -> dict[str, Any]:
    """Find OpenStreetMap-mapped land-use, natural, amenity, leisure, and
    man-made features near a point - answers "what's around here", "is this
    near an industrial/residential zone", "is this near water or green space"
    type questions.

    This is only as good as OpenStreetMap's coverage, which is thin outside
    cities. An empty result means nothing is mapped there, not that nothing
    exists."""
    radius_meters = max(10.0, min(float(radius_meters), 5000.0))
    max_results = max(1, min(int(max_results), 100))

    query = _build_overpass_query(latitude, longitude, radius_meters)
    try:
        data = _http_post_json(OVERPASS_URL, {"data": query})
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {"ok": False, "error": f"Overpass API request failed: {exc}"}

    if not isinstance(data, dict) or "elements" not in data:
        return {"ok": False, "error": f"unexpected Overpass response: {data!r}"[:500]}

    features: list[dict[str, Any]] = []
    for el in data.get("elements") or []:
        tags = el.get("tags") or {}
        category, tag_value = None, None
        for key, _values in _TAG_CATEGORIES:
            if key in tags:
                category, tag_value = key, tags[key]
                break
        if category is None:
            continue

        if el.get("type") == "node":
            lat, lon = _as_float(el.get("lat")), _as_float(el.get("lon"))
        else:
            center = el.get("center") or {}
            lat, lon = _as_float(center.get("lat")), _as_float(center.get("lon"))
        if lat is None or lon is None:
            continue

        features.append(
            {
                "name": tags.get("name") or f"unnamed {tag_value}",
                "category": category,
                "tag_value": tag_value,
                "distance_meters": round(_haversine_meters(latitude, longitude, lat, lon), 1),
                "latitude": lat,
                "longitude": lon,
            }
        )

    # Big polygons (a park, a lake) often come back as several nodes/ways
    # clustered at the same spot - collapse those before ranking by distance.
    seen: set[tuple[str, str, float]] = set()
    deduped: list[dict[str, Any]] = []
    for f in sorted(features, key=lambda f: f["distance_meters"]):
        key = (f["name"], f["category"], round(f["distance_meters"], -1))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)

    truncated = len(deduped) > max_results
    shown = deduped[:max_results]

    counts_by_category: dict[str, int] = {}
    for f in deduped:
        counts_by_category[f["category"]] = counts_by_category.get(f["category"], 0) + 1

    return {
        "ok": True,
        "latitude": latitude,
        "longitude": longitude,
        "radius_meters": radius_meters,
        "features_found": len(deduped),
        "counts_by_category": counts_by_category,
        "features": shown,
        "note": (
            f"Showing nearest {len(shown)} of {len(deduped)} deduplicated features; "
            "narrow radius_meters or filter by category for a shorter list."
            if truncated
            else None
        ),
        "source": "OpenStreetMap via Overpass API",
    }
