"""Elevation/terrain skill — point elevation + estimated slope (USGS EPQS).

Adapted from the a2a-sean branch to the shared skill contract. Elevation from
the USGS Elevation Point Query Service (3DEP); slope is a finite-difference
estimate from four ~30 m N/S/E/W samples (EPQS has no slope endpoint).

Honesty (preserved): slope is a rough "flat vs. steep" estimate, not a precise
engineering figure; EPQS returns a large-magnitude sentinel where it has no
coverage, which we treat as "no data" rather than a real elevation.

Data source (keyless): https://epqs.nationalmap.gov/v1/json
Stdlib only; synchronous.
"""
from __future__ import annotations

import math
import urllib.error
from typing import Any

from ._common import EPQS_URL, as_float, http_get_json, offset_latlon, validated_coords

SKILL_NAME = "elevation"
SOURCE_LABEL = "USGS Elevation Point Query Service (The National Map / 3DEP)"
_SLOPE_SAMPLE_OFFSET_M = 30.0
_EPQS_NODATA_THRESHOLD = 1.0e5


def _epqs_elevation_meters(latitude: float, longitude: float, timeout: float) -> float | None:
    data = http_get_json(
        EPQS_URL, {"x": longitude, "y": latitude, "units": "Meters", "wkid": 4326}, timeout=timeout
    )
    value = as_float((data or {}).get("value"))
    if value is None or abs(value) >= _EPQS_NODATA_THRESHOLD:
        return None
    return value


def find_elevation_terrain(latitude: float, longitude: float, *, timeout: float = 25.0) -> dict[str, Any]:
    """Ground elevation + estimated local slope at a point. Shared contract."""
    try:
        latitude, longitude = validated_coords(latitude, longitude)
    except ValueError as exc:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": str(exc)}

    try:
        center = _epqs_elevation_meters(latitude, longitude, timeout)
        if center is None:
            return {"ok": True, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                    "latitude": latitude, "longitude": longitude, "elevation_meters": None,
                    "note": "USGS EPQS has no elevation data at this point (outside 3DEP coverage)."}
        n = _epqs_elevation_meters(*offset_latlon(latitude, longitude, _SLOPE_SAMPLE_OFFSET_M, 0), timeout)
        s = _epqs_elevation_meters(*offset_latlon(latitude, longitude, -_SLOPE_SAMPLE_OFFSET_M, 0), timeout)
        e = _epqs_elevation_meters(*offset_latlon(latitude, longitude, 0, _SLOPE_SAMPLE_OFFSET_M), timeout)
        w = _epqs_elevation_meters(*offset_latlon(latitude, longitude, 0, -_SLOPE_SAMPLE_OFFSET_M), timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "error": f"USGS EPQS request failed: {exc}"}

    slope_percent = slope_degrees = None
    if None not in (n, s, e, w):
        dz_dy = (n - s) / (2 * _SLOPE_SAMPLE_OFFSET_M)
        dz_dx = (e - w) / (2 * _SLOPE_SAMPLE_OFFSET_M)
        grade = math.hypot(dz_dx, dz_dy)
        slope_percent = round(grade * 100, 1)
        slope_degrees = round(math.degrees(math.atan(grade)), 1)

    return {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "latitude": latitude,
        "longitude": longitude,
        "elevation_meters": round(center, 1),
        "elevation_feet": round(center * 3.28084, 1),
        "slope_percent": slope_percent,
        "slope_degrees": slope_degrees,
        "note": (
            "Slope is a rough finite-difference estimate (~30 m samples), not a precise value."
            if slope_percent is not None
            else "Could not estimate slope — EPQS had no data at one or more nearby sample points."
        ),
    }


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import json
    import sys

    if len(sys.argv) >= 3:
        la, lo = float(sys.argv[1]), float(sys.argv[2])
    else:
        la, lo = 44.4237, -110.5885
    print(json.dumps(find_elevation_terrain(la, lo), indent=2))
