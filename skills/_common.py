"""Shared HTTP + geo helpers for the skills ported from the a2a-sean branch.

These five skills (geocode, contamination, elevation, flood_zone, proximity)
were originally Path-A tools in ``geo_context_agent``; they are adapted here to
the Path-B shared skill contract. This module holds the plumbing they share so
each skill module stays focused on its data source.

Stdlib only. Endpoints are keyless. A descriptive (non-browser) User-Agent is
used — Overpass rejects fake ``Mozilla`` agents (406), and Nominatim's usage
policy requires a real identifying agent.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "geo-research-orchestrator/0.1 (WashU environmental research)"
TIMEOUT_S = 25.0

# --- External data sources (keyless) --------------------------------------
ECHO_BASE_URL = "https://echodata.epa.gov/echo/echo_rest_services"
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
EPQS_URL = "https://epqs.nationalmap.gov/v1/json"
FEMA_NFHL_ZONES_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
)


def http_get_json(url: str, params: dict[str, Any], *, timeout: float = TIMEOUT_S) -> Any:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post_json(url: str, data: dict[str, str], *, timeout: float = TIMEOUT_S) -> Any:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def as_bool_flag(value: Any) -> bool:
    return str(value or "").strip().upper() == "Y"


def offset_latlon(lat: float, lon: float, dlat_m: float, dlon_m: float) -> tuple[float, float]:
    """Nudge a lat/lon by a small offset in meters (north/east positive)."""
    new_lat = lat + (dlat_m / 111_320.0)
    new_lon = lon + (dlon_m / (111_320.0 * math.cos(math.radians(lat)) or 1e-9))
    return new_lat, new_lon


def validated_coords(lat: Any, lon: Any) -> tuple[float, float]:
    """Return (lat, lon) as floats or raise ValueError — shared by the point skills."""
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        raise ValueError(f"latitude/longitude must be numbers, got ({lat!r}, {lon!r})")
    if not (-90.0 <= lat_f <= 90.0) or not (-180.0 <= lon_f <= 180.0):
        raise ValueError(f"coordinates out of range: lat={lat_f}, lon={lon_f}")
    return lat_f, lon_f
