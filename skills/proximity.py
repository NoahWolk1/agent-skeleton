"""Proximity skill — nearby OSM land-use/natural/amenity features (Overpass).

Adapted from the a2a-sean branch to the shared skill contract. Answers "what's
around here — near an industrial zone? water/green space? a school or waste
facility?" from OpenStreetMap features within a radius.

Honesty (preserved): only as good as OSM coverage (thin outside cities); an
empty result means nothing is MAPPED there, not that nothing exists.

Data source (keyless): Overpass API. A descriptive User-Agent is required
(Overpass 406s fake-browser agents). Stdlib only; synchronous.
"""
from __future__ import annotations

import urllib.error
from typing import Any

from ._common import OVERPASS_URL, as_float, haversine_meters, http_post_json, validated_coords

SKILL_NAME = "proximity"
SOURCE_LABEL = "OpenStreetMap via Overpass API"

# Tag values worth surfacing; deliberately excludes any-value tags (e.g.
# natural=tree) that would bury useful results in dense cities.
_TAG_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("landuse", ("residential", "industrial", "commercial", "retail", "farmland",
                 "forest", "quarry", "landfill", "brownfield", "cemetery")),
    ("natural", ("water", "wetland", "wood", "scrub", "grassland", "beach")),
    ("amenity", ("hospital", "school", "waste_transfer_station", "fuel",
                 "waste_disposal", "recycling", "fire_station")),
    ("leisure", ("park", "nature_reserve")),
    ("man_made", ("works", "wastewater_plant", "water_works", "pipeline", "storage_tank")),
)


def build_overpass_query(latitude: float, longitude: float, radius_meters: float) -> str:
    """Pure: assemble the Overpass QL query string (kept testable offline)."""
    clauses = []
    for key, values in _TAG_CATEGORIES:
        value_regex = "^(" + "|".join(values) + ")$"
        for element in ("node", "way"):
            clauses.append(f'{element}(around:{radius_meters},{latitude},{longitude})["{key}"~"{value_regex}"];')
    return "[out:json][timeout:25];\n(\n  " + "\n  ".join(clauses) + "\n);\nout center tags;"


def find_nearby_features(
    latitude: float,
    longitude: float,
    *,
    radius_meters: float = 500.0,
    max_results: int = 30,
    timeout: float = 25.0,
) -> dict[str, Any]:
    """Nearby OSM land-use/natural/amenity/leisure/man-made features. Shared contract."""
    try:
        latitude, longitude = validated_coords(latitude, longitude)
    except ValueError as exc:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": str(exc)}
    radius_meters = max(10.0, min(float(radius_meters), 5000.0))
    max_results = max(1, min(int(max_results), 100))

    query = build_overpass_query(latitude, longitude, radius_meters)
    try:
        data = http_post_json(OVERPASS_URL, {"data": query}, timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "error": f"Overpass API request failed: {exc}"}

    if not isinstance(data, dict) or "elements" not in data:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "error": f"unexpected Overpass response: {data!r}"[:300]}

    features: list[dict[str, Any]] = []
    for el in data.get("elements") or []:
        tags = el.get("tags") or {}
        category = tag_value = None
        for key, _values in _TAG_CATEGORIES:
            if key in tags:
                category, tag_value = key, tags[key]
                break
        if category is None:
            continue
        if el.get("type") == "node":
            lat, lon = as_float(el.get("lat")), as_float(el.get("lon"))
        else:
            center = el.get("center") or {}
            lat, lon = as_float(center.get("lat")), as_float(center.get("lon"))
        if lat is None or lon is None:
            continue
        features.append(
            {
                "name": tags.get("name") or f"unnamed {tag_value}",
                "category": category,
                "tag_value": tag_value,
                "distance_meters": round(haversine_meters(latitude, longitude, lat, lon), 1),
                "latitude": lat,
                "longitude": lon,
            }
        )

    # Collapse big polygons that come back as clustered nodes/ways.
    seen: set[tuple] = set()
    deduped: list[dict[str, Any]] = []
    for f in sorted(features, key=lambda f: f["distance_meters"]):
        key = (f["name"], f["category"], round(f["distance_meters"], -1))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)

    counts: dict[str, int] = {}
    for f in deduped:
        counts[f["category"]] = counts.get(f["category"], 0) + 1
    truncated = len(deduped) > max_results
    shown = deduped[:max_results]

    return {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "latitude": latitude,
        "longitude": longitude,
        "radius_meters": radius_meters,
        "features_found": len(deduped),
        "counts_by_category": counts,
        "features": shown,
        "note": (
            f"Showing nearest {len(shown)} of {len(deduped)} features; narrow radius_meters for fewer."
            if truncated
            else ("Nothing mapped here in OpenStreetMap (coverage is thin outside cities)."
                  if not deduped else None)
        ),
    }


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import json
    import sys

    if len(sys.argv) >= 3:
        la, lo = float(sys.argv[1]), float(sys.argv[2])
    else:
        la, lo = 38.627, -90.199
    print(json.dumps(find_nearby_features(la, lo), indent=2))
