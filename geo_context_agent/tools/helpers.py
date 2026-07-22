"""Shared HTTP + numeric helpers used by more than one tool in this package.

Not part of the TOOL_REGISTRY contract - just plumbing the individual tool
modules import from.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from typing import Any

from ..config import HTTP_TIMEOUT_S, HTTP_USER_AGENT


def _http_get_json(url: str, params: dict[str, Any]) -> Any:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    full_url = f"{url}?{query}"
    request = urllib.request.Request(full_url, headers={"User-Agent": HTTP_USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_post_json(url: str, data: dict[str, str]) -> Any:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"User-Agent": HTTP_USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))


def _haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_meters = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r_meters * math.asin(math.sqrt(a))


def _as_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool_flag(value: Any) -> bool:
    return str(value or "").strip().upper() == "Y"


def _offset_latlon(lat: float, lon: float, dlat_m: float, dlon_m: float) -> tuple[float, float]:
    """Nudge a lat/lon point by a small offset given in meters (north/east
    positive). Rough WGS84 approximation - fine at the ~30m scale used for
    slope estimation, not meant for anything precision-critical."""
    new_lat = lat + (dlat_m / 111_320.0)
    new_lon = lon + (dlon_m / (111_320.0 * math.cos(math.radians(lat)) or 1e-9))
    return new_lat, new_lon
