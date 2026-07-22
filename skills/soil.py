"""Soil skill — soil type & properties at a coordinate (USDA SSURGO).

Answers "what soil is here?" — map unit, dominant soil component, drainage
class, taxonomic order, hydric rating, and farmland class. Feeds habitat-
suitability and contamination-transport (infiltration/runoff) questions.

Data source (verified 2026-07, keyless):
  USDA Soil Data Access (SDA) tabular POST service, querying the SSURGO
  database by the map unit that intersects the point.
    POST https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest
    body: {"query": "<T-SQL>", "format": "JSON+COLUMNNAME"}
    The point-to-mapunit lookup uses SDA's spatial function
    SDA_Get_Mukey_from_intersection_with_WktWgs84('point(<lon> <lat>)').
  Response: {"Table": [[col names...], [row...], ...]}  (first row = headers).

Coverage: SSURGO is US soil survey data. A point outside surveyed area (or
outside the US) returns no rows — reported honestly as "no soil data", never
filled in. Urban map units legitimately have null natural-soil attributes.

Stdlib only; synchronous (the async orchestrator wraps it in
``asyncio.to_thread``). The pure table parser is split out for offline tests.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

SKILL_NAME = "soil"
SOURCE_LABEL = "USDA SSURGO (Soil Data Access)"
SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/tabular/post.rest"
_UA = "geo-research-orchestrator/0.1 (WashU environmental research)"


def _error(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": msg, **extra}


def _build_sql(lat: float, lon: float) -> str:
    return (
        "SELECT mu.mukey, mu.muname, mu.farmlndcl, c.compname, c.comppct_r, "
        "c.drainagecl, c.taxorder, c.taxsubgrp, c.hydricrating "
        "FROM mapunit mu INNER JOIN component c ON c.mukey = mu.mukey "
        "WHERE mu.mukey IN (SELECT * FROM "
        f"SDA_Get_Mukey_from_intersection_with_WktWgs84('point({lon} {lat})')) "
        "ORDER BY c.comppct_r DESC"
    )


def parse_sda_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure: SDA 'JSON+COLUMNNAME' Table -> list of row dicts.

    The first row is the column-name header. Returns [] when there are no data
    rows (point outside SSURGO coverage). Never invents values.
    """
    table = payload.get("Table") if isinstance(payload, dict) else None
    if not isinstance(table, list) or len(table) < 2:
        return []
    header = table[0]
    return [dict(zip(header, row)) for row in table[1:]]


def _num(v: Any) -> Any:
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def soil_at_location(lat: float, lon: float, *, timeout: float = 60.0) -> dict[str, Any]:
    """Soil map unit & dominant component at (lat, lon). Shared skill contract.

    ``ok=True`` with a ``note`` when the point has no SSURGO data (outside
    surveyed area / outside the US); ``ok=False`` on bad input, network, HTTP,
    or parse failure.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return _error(f"latitude/longitude must be numbers, got ({lat!r}, {lon!r})")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return _error(f"coordinates out of range: lat={lat}, lon={lon}")

    body = json.dumps({"query": _build_sql(lat, lon), "format": "JSON+COLUMNNAME"}).encode()
    req = urllib.request.Request(
        SDA_URL, data=body, headers={"Content-Type": "application/json", "User-Agent": _UA}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return _error(f"USDA Soil Data Access returned HTTP {exc.code}", status=exc.code)
    except urllib.error.URLError as exc:
        return _error(f"network error contacting USDA Soil Data Access: {exc.reason}")
    except ValueError as exc:
        return _error(f"could not parse USDA Soil Data Access response: {exc}")
    except Exception as exc:  # defensive: never crash the orchestrator
        return _error(f"unexpected error calling USDA Soil Data Access: {type(exc).__name__}: {exc}")

    rows = parse_sda_table(payload)
    if not rows:
        return {
            "ok": True, "skill": SKILL_NAME, "source": SOURCE_LABEL,
            "latitude": lat, "longitude": lon, "map_unit": None,
            "dominant_component": None, "components": [],
            "note": "No SSURGO soil data at this point (outside a surveyed area or outside the US).",
            "source_url": SDA_URL,
        }

    components = [
        {
            "name": r.get("compname"),
            "percent": _num(r.get("comppct_r")),
            "drainage_class": r.get("drainagecl"),
            "taxonomic_order": r.get("taxorder"),
            "taxonomic_subgroup": r.get("taxsubgrp"),
            "hydric_rating": r.get("hydricrating"),
        }
        for r in rows
    ]
    first = rows[0]
    return {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "latitude": lat,
        "longitude": lon,
        "map_unit": {
            "mukey": first.get("mukey"),
            "name": first.get("muname"),
            "farmland_class": first.get("farmlndcl"),
        },
        "dominant_component": components[0],
        "components": components,
        "source_url": SDA_URL,
    }


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import sys

    if len(sys.argv) >= 3:
        latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
    else:
        latitude, longitude = 42.0, -93.6  # Iowa farmland
    print(json.dumps(soil_at_location(latitude, longitude), indent=2))
