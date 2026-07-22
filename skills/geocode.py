"""Geocode skill — place name / address -> coordinates (OSM Nominatim).

Adapted from the a2a-sean branch to the shared skill contract. This is the
utility that lets a researcher give "Forest Park, St. Louis" instead of raw
coordinates; the orchestrator runs it first, then feeds lat/lon to the other
skills.

Data source (keyless): OpenStreetMap Nominatim /search. Nominatim's usage
policy requires a real User-Agent and ~1 req/sec (one-shot lookups satisfy it).

Stdlib only; synchronous. Never fabricates a location — an unmatched query
returns ok=False with a clear message.
"""
from __future__ import annotations

import urllib.error
from typing import Any

from ._common import NOMINATIM_BASE_URL, as_float, http_get_json

SKILL_NAME = "geocode"
SOURCE_LABEL = "OpenStreetMap Nominatim"


def geocode_address(address: str, *, timeout: float = 25.0) -> dict[str, Any]:
    """Turn a place name / address into lat/lon. Returns the shared contract."""
    if not address or not str(address).strip():
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "error": "address must be a non-empty string"}
    try:
        data = http_get_json(
            f"{NOMINATIM_BASE_URL}/search",
            {"q": str(address).strip(), "format": "jsonv2", "limit": 1, "addressdetails": 1},
            timeout=timeout,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "error": f"geocoding request failed: {exc}"}

    if not data:
        return {"ok": True, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "query": str(address).strip(), "match": None,
                "note": f"no geocoding results for {str(address).strip()!r}"}

    top = data[0]
    lat, lon = as_float(top.get("lat")), as_float(top.get("lon"))
    if lat is None or lon is None:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "error": "geocoder returned no usable coordinates"}
    return {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "query": str(address).strip(),
        "latitude": lat,
        "longitude": lon,
        "display_name": top.get("display_name"),
        "source_url": f"{NOMINATIM_BASE_URL}/search",
    }


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import json
    import sys

    q = " ".join(sys.argv[1:]) or "Forest Park, St. Louis, Missouri"
    print(json.dumps(geocode_address(q), indent=2))
