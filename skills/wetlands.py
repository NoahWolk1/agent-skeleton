"""Wetlands skill — wetland type at a coordinate (USFWS NWI).

Answers "is this point a mapped wetland, and what type?" — a detailed, standalone
version of the wetland signal (the species/IPaC skill only flags presence). Core
for aquatic-habitat and hydrology questions.

Data source (verified 2026-07, keyless):
  USFWS National Wetlands Inventory (NWI) Wetlands MapServer, layer 0.
    https://www.fws.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0
  Query: point-intersects. Fields: ATTRIBUTE (NWI classification code, e.g.
  'PEM5Fh'), WETLAND_TYPE (human label, e.g. 'Freshwater Emergent Wetland'),
  ACRES. (The layer joins a codes table, so field names come back table-
  prefixed; we match by suffix to stay robust.)

Honesty: a zero result means "no NWI wetland polygon is mapped at this exact
point," NOT "there is no wetland here" — NWI coverage/precision varies and is
US-focused. We say so rather than asserting a definitive negative.

Stdlib only; synchronous (the async orchestrator wraps it in
``asyncio.to_thread``). The pure parser is split out for offline tests.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SKILL_NAME = "wetlands"
SOURCE_LABEL = "USFWS National Wetlands Inventory (NWI)"
NWI_LAYER = "https://www.fws.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0"
_UA = "geo-research-orchestrator/0.1 (WashU environmental research)"
_OUT_FIELDS = "Wetlands.ATTRIBUTE,Wetlands.WETLAND_TYPE,Wetlands.ACRES"


def _error(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": msg, **extra}


def _field(attrs: dict[str, Any], suffix: str) -> Any:
    """Fetch an attribute by (possibly table-prefixed) field name suffix."""
    if suffix in attrs:
        return attrs[suffix]
    for k, v in attrs.items():
        if k.split(".")[-1] == suffix:
            return v
    return None


def parse_wetland_features(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure: NWI features -> list of {code, type, acres}. Never invents values."""
    out: list[dict[str, Any]] = []
    for f in features:
        a = f.get("attributes") or {}
        acres = _field(a, "ACRES")
        try:
            acres = round(float(acres), 2)
        except (TypeError, ValueError):
            pass
        out.append(
            {
                "code": _field(a, "ATTRIBUTE"),
                "type": _field(a, "WETLAND_TYPE"),
                "acres": acres,
            }
        )
    return out


def wetlands_at(lat: float, lon: float, *, timeout: float = 40.0) -> dict[str, Any]:
    """NWI wetland classification at (lat, lon). Returns the shared contract.

    ``is_wetland`` is True iff an NWI wetland polygon intersects the point. A
    zero result is reported honestly (never "no wetland here"). Bad input /
    network / HTTP / parse errors return ``ok=False``.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return _error(f"latitude/longitude must be numbers, got ({lat!r}, {lon!r})")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return _error(f"coordinates out of range: lat={lat}, lon={lon}")

    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": _OUT_FIELDS,
        "returnGeometry": "false",
        "f": "json",
    }
    url = f"{NWI_LAYER}/query?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return _error(f"NWI service returned HTTP {exc.code}", status=exc.code, source_url=url)
    except urllib.error.URLError as exc:
        return _error(f"network error contacting NWI: {exc.reason}", source_url=url)
    except ValueError as exc:
        return _error(f"could not parse NWI response: {exc}", source_url=url)
    except Exception as exc:  # defensive: never crash the orchestrator
        return _error(f"unexpected error calling NWI: {type(exc).__name__}: {exc}", source_url=url)

    if isinstance(payload, dict) and payload.get("error"):
        return _error(f"NWI query error: {payload['error']}", source_url=url)

    wetlands = parse_wetland_features(payload.get("features", []))
    result = {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "latitude": lat,
        "longitude": lon,
        "is_wetland": len(wetlands) > 0,
        "wetlands": wetlands,
        "source_url": url,
    }
    if not wetlands:
        result["note"] = (
            "No NWI wetland polygon is mapped at this exact point. This is not proof "
            "there is no wetland here — NWI coverage and precision vary and are US-focused."
        )
    return result


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import sys

    if len(sys.argv) >= 3:
        latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
    else:
        latitude, longitude = 25.90, -80.75  # Everglades, FL
    print(json.dumps(wetlands_at(latitude, longitude), indent=2))
