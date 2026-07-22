"""geocode_address -> OpenStreetMap Nominatim, place name/address -> lat/lon."""
from __future__ import annotations

import urllib.error
from typing import Any

from ..config import NOMINATIM_BASE_URL
from .helpers import _as_float, _http_get_json


def geocode_address(*, address: str) -> dict[str, Any]:
    """Turn a place name or address into lat/lon via OpenStreetMap Nominatim.
    Both of the other tools need coordinates, so this usually runs first."""
    if not address or not address.strip():
        return {"ok": False, "error": "address must be a non-empty string"}
    try:
        data = _http_get_json(
            f"{NOMINATIM_BASE_URL}/search",
            {"q": address, "format": "jsonv2", "limit": 1, "addressdetails": 1},
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {"ok": False, "error": f"geocoding request failed: {exc}"}

    if not data:
        return {"ok": False, "error": f"no geocoding results for {address!r}"}

    top = data[0]
    lat, lon = _as_float(top.get("lat")), _as_float(top.get("lon"))
    if lat is None or lon is None:
        return {"ok": False, "error": "geocoder returned no usable coordinates"}
    return {
        "ok": True,
        "query": address,
        "latitude": lat,
        "longitude": lon,
        "display_name": top.get("display_name"),
        "source": "OpenStreetMap Nominatim",
    }
