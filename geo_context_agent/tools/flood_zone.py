"""find_flood_zone -> FEMA National Flood Hazard Layer, the mapped flood
zone at a point.

A mapped regulatory designation, not a live flood forecast - see prompt.py's
SYSTEM_PROMPT for how the agent is told to frame that.
"""
from __future__ import annotations

import urllib.error
from typing import Any

from ..config import FEMA_NFHL_ZONES_URL
from .helpers import _as_float, _http_get_json


def find_flood_zone(*, latitude: float, longitude: float) -> dict[str, Any]:
    """Look up the FEMA-mapped flood zone at a point via the National Flood
    Hazard Layer (NFHL). Reports the flood zone code (e.g. 'X' = minimal
    hazard, 'AE'/'A'/'VE' = mapped high-risk Special Flood Hazard Area) and,
    where available, the base flood elevation.

    This is a regulatory flood-map designation, not a live flood forecast or
    guarantee: an area with no NFHL coverage returns no zone at all (unstudied,
    not necessarily safe), and even Zone X ("minimal hazard") is not a
    guarantee against flooding - FEMA's own maps carry that same caveat.
    """
    try:
        data = _http_get_json(
            FEMA_NFHL_ZONES_URL,
            {
                "geometry": f"{longitude},{latitude}",
                "geometryType": "esriGeometryPoint",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,V_DATUM",
                "f": "json",
            },
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {"ok": False, "error": f"FEMA NFHL request failed: {exc}"}

    if not isinstance(data, dict) or "error" in data:
        return {"ok": False, "error": f"FEMA NFHL error: {(data or {}).get('error')}"}

    features = data.get("features") or []
    if not features:
        return {
            "ok": True,
            "latitude": latitude,
            "longitude": longitude,
            "flood_zone": None,
            "note": (
                "No FEMA NFHL flood zone data at this point - the area may be unstudied, "
                "not necessarily low-risk."
            ),
            "source": "FEMA National Flood Hazard Layer",
        }

    attrs = features[0].get("attributes") or {}
    bfe = _as_float(attrs.get("STATIC_BFE"))
    return {
        "ok": True,
        "latitude": latitude,
        "longitude": longitude,
        "flood_zone": attrs.get("FLD_ZONE"),
        "zone_description": attrs.get("ZONE_SUBTY"),
        "in_special_flood_hazard_area": str(attrs.get("SFHA_TF") or "").strip().upper() == "T",
        "base_flood_elevation_ft": bfe if bfe is not None and bfe > -9000 else None,
        "vertical_datum": attrs.get("V_DATUM"),
        "note": "A mapped flood zone designation, not a live flood forecast or a guarantee against flooding.",
        "source": "FEMA National Flood Hazard Layer",
    }
