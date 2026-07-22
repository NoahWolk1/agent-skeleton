"""Flood-zone skill — FEMA-mapped flood zone at a point (FEMA NFHL).

Adapted from the a2a-sean branch to the shared skill contract. Reports the FEMA
flood zone code (X = minimal, A/AE/VE = high-risk Special Flood Hazard Area) and
base flood elevation where available.

Honesty (preserved): this is a regulatory flood-map designation, NOT a live
forecast or a guarantee. No NFHL coverage returns no zone (unstudied, not
necessarily safe); even Zone X is not a guarantee against flooding.

Data source (keyless): FEMA National Flood Hazard Layer ArcGIS REST, layer 28.
Stdlib only; synchronous.
"""
from __future__ import annotations

import urllib.error
from typing import Any

from ._common import FEMA_NFHL_ZONES_URL, as_float, http_get_json, validated_coords

SKILL_NAME = "flood_zone"
SOURCE_LABEL = "FEMA National Flood Hazard Layer"


def find_flood_zone(latitude: float, longitude: float, *, timeout: float = 25.0) -> dict[str, Any]:
    """FEMA-mapped flood zone at a point. Returns the shared contract."""
    try:
        latitude, longitude = validated_coords(latitude, longitude)
    except ValueError as exc:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": str(exc)}

    try:
        data = http_get_json(
            FEMA_NFHL_ZONES_URL,
            {
                "geometry": f"{longitude},{latitude}",
                "geometryType": "esriGeometryPoint",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,V_DATUM",
                "f": "json",
            },
            timeout=timeout,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "error": f"FEMA NFHL request failed: {exc}"}

    if not isinstance(data, dict) or "error" in data:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "error": f"FEMA NFHL error: {(data or {}).get('error')}"}

    features = data.get("features") or []
    if not features:
        return {
            "ok": True, "skill": SKILL_NAME, "source": SOURCE_LABEL,
            "latitude": latitude, "longitude": longitude, "flood_zone": None,
            "in_special_flood_hazard_area": None,
            "note": "No FEMA NFHL flood zone data at this point — the area may be unstudied, not necessarily low-risk.",
        }

    attrs = features[0].get("attributes") or {}
    bfe = as_float(attrs.get("STATIC_BFE"))
    return {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "latitude": latitude,
        "longitude": longitude,
        "flood_zone": attrs.get("FLD_ZONE"),
        "zone_description": attrs.get("ZONE_SUBTY"),
        "in_special_flood_hazard_area": str(attrs.get("SFHA_TF") or "").strip().upper() == "T",
        "base_flood_elevation_ft": bfe if bfe is not None and bfe > -9000 else None,
        "vertical_datum": attrs.get("V_DATUM"),
        "note": "A mapped flood-zone designation, not a live forecast or a guarantee against flooding.",
    }


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import json
    import sys

    if len(sys.argv) >= 3:
        la, lo = float(sys.argv[1]), float(sys.argv[2])
    else:
        la, lo = 29.95, -90.07  # New Orleans (flood-prone)
    print(json.dumps(find_flood_zone(la, lo), indent=2))
