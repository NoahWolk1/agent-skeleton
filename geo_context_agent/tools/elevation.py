"""find_elevation_terrain -> USGS EPQS (3DEP), elevation + an estimated
local slope at a point.

EPQS only gives point elevation, no slope endpoint exists - slope here is a
finite-difference estimate from 4 extra sample points ~30m N/S/E/W, not a
precise engineering figure. See prompt.py's SYSTEM_PROMPT for how the agent
is told to frame that.
"""
from __future__ import annotations

import math
import urllib.error
from typing import Any

from ..config import EPQS_URL
from .helpers import _as_float, _http_get_json, _offset_latlon

_SLOPE_SAMPLE_OFFSET_M = 30.0  # distance to the N/S/E/W sample points used to estimate slope
_EPQS_NODATA_THRESHOLD = 1.0e5  # EPQS returns large-magnitude sentinel values (e.g. -1000000) where it has no data


def _epqs_elevation_meters(latitude: float, longitude: float) -> float | None:
    """One EPQS point query -> elevation in meters, or None if EPQS has no
    coverage there (it returns a large-magnitude sentinel value instead of
    raising an error)."""
    data = _http_get_json(EPQS_URL, {"x": longitude, "y": latitude, "units": "Meters", "wkid": 4326})
    value = _as_float((data or {}).get("value"))
    if value is None or abs(value) >= _EPQS_NODATA_THRESHOLD:
        return None
    return value


def find_elevation_terrain(*, latitude: float, longitude: float) -> dict[str, Any]:
    """Look up ground elevation at a point via USGS EPQS (3DEP), and estimate
    the local slope by also sampling points ~30m north/south/east/west and
    taking the finite-difference gradient. Useful for habitat/watershed
    context (e.g. ridge vs. valley vs. floodplain-flat terrain).

    The slope is an estimate from a handful of sample points, not an exact
    analytic value at that pixel - treat it as "roughly flat" / "roughly
    steep", not a precise engineering figure.
    """
    try:
        center = _epqs_elevation_meters(latitude, longitude)
        if center is None:
            return {"ok": False, "error": "USGS EPQS has no elevation data at this point"}

        north_lat, north_lon = _offset_latlon(latitude, longitude, _SLOPE_SAMPLE_OFFSET_M, 0)
        south_lat, south_lon = _offset_latlon(latitude, longitude, -_SLOPE_SAMPLE_OFFSET_M, 0)
        east_lat, east_lon = _offset_latlon(latitude, longitude, 0, _SLOPE_SAMPLE_OFFSET_M)
        west_lat, west_lon = _offset_latlon(latitude, longitude, 0, -_SLOPE_SAMPLE_OFFSET_M)

        north = _epqs_elevation_meters(north_lat, north_lon)
        south = _epqs_elevation_meters(south_lat, south_lon)
        east = _epqs_elevation_meters(east_lat, east_lon)
        west = _epqs_elevation_meters(west_lat, west_lon)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {"ok": False, "error": f"USGS EPQS request failed: {exc}"}

    slope_percent = None
    slope_degrees = None
    if None not in (north, south, east, west):
        dz_dy = (north - south) / (2 * _SLOPE_SAMPLE_OFFSET_M)  # north-south gradient
        dz_dx = (east - west) / (2 * _SLOPE_SAMPLE_OFFSET_M)  # east-west gradient
        grade = math.hypot(dz_dx, dz_dy)  # rise/run
        slope_percent = round(grade * 100, 1)
        slope_degrees = round(math.degrees(math.atan(grade)), 1)

    return {
        "ok": True,
        "latitude": latitude,
        "longitude": longitude,
        "elevation_meters": round(center, 1),
        "elevation_feet": round(center * 3.28084, 1),
        "slope_percent": slope_percent,
        "slope_degrees": slope_degrees,
        "note": (
            None
            if slope_percent is not None
            else "Could not estimate slope - EPQS had no data at one or more sample points near this location."
        ),
        "source": "USGS Elevation Point Query Service (The National Map / 3DEP)",
    }
