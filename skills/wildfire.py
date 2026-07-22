"""Wildfire skill — fire history at a coordinate (NIFC perimeter history).

Answers "has this location burned, and when?" — fire history is a strong driver
of habitat structure and succession, directly relevant to camera-trap and
habitat-suitability questions.

Data source (verified 2026-07, keyless):
  NIFC InterAgency Fire Perimeter History (all years, through 2024) — an
  ArcGIS Online FeatureServer aggregating USFS/BLM/BIA/FWS/NPS/CalFire/WFIGS
  fire perimeters.
    https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/
        InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0
  Query: point-intersects (precise "did THIS point burn"), newest first.

Honesty: a zero result means "no wildfire in this dataset has burned this exact
point," NOT "this area has never burned." The dataset is US-focused and
perimeter-based; we say so rather than implying a definitive negative. NIFC
stores duplicate perimeter records per fire, so results are de-duplicated by
(incident name, year).

Note: this is HISTORICAL perimeters. Real-time active-fire hotspots (NASA FIRMS)
require a free MAP_KEY and could be added later, read from the credential context.

Stdlib only; synchronous (the async orchestrator wraps it in
``asyncio.to_thread``). The pure parser is split out for offline tests.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SKILL_NAME = "wildfire"
SOURCE_LABEL = "NIFC InterAgency Fire Perimeter History"
FIRE_LAYER = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0"
)
_UA = "geo-research-orchestrator/0.1 (WashU environmental research)"


def _error(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": msg, **extra}


def _year(attrs: dict[str, Any]) -> int | None:
    for key in ("FIRE_YEAR_INT", "FIRE_YEAR"):
        v = attrs.get(key)
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return None


def parse_fire_features(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure: fire perimeter features -> de-duplicated fires, newest first.

    De-duplicates by (incident name upper-cased, year) because NIFC stores
    multiple perimeter records for the same fire. Missing values stay None.
    """
    seen: set[tuple] = set()
    fires: list[dict[str, Any]] = []
    for f in features:
        a = f.get("attributes") or {}
        name = a.get("INCIDENT")
        year = _year(a)
        key = (name.strip().upper() if isinstance(name, str) else name, year)
        if key in seen:
            continue
        seen.add(key)
        acres = a.get("GIS_ACRES")
        try:
            acres = round(float(acres), 1)
        except (TypeError, ValueError):
            pass
        fires.append(
            {
                "incident": name,
                "year": year,
                "acres": acres,
                "date_current": a.get("DATE_CUR"),
                "agency": a.get("AGENCY"),
                "source": a.get("SOURCE"),
            }
        )
    fires.sort(key=lambda x: (x["year"] is None, -(x["year"] or 0)))
    return fires


def fire_history_at(lat: float, lon: float, *, max_fires: int = 15, timeout: float = 40.0) -> dict[str, Any]:
    """Recorded wildfires that burned (lat, lon). Returns the shared contract.

    ``burned`` is True iff the point falls inside one or more recorded fire
    perimeters. A zero result is reported honestly (never "never burned"). Bad
    input / network / HTTP / parse errors return ``ok=False``.
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
        "outFields": "INCIDENT,FIRE_YEAR,FIRE_YEAR_INT,GIS_ACRES,DATE_CUR,AGENCY,SOURCE",
        "returnGeometry": "false",
        "resultRecordCount": str(max(1, min(max_fires * 3, 200))),
        "f": "json",
    }
    url = f"{FIRE_LAYER}/query?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return _error(f"NIFC fire service returned HTTP {exc.code}", status=exc.code, source_url=url)
    except urllib.error.URLError as exc:
        return _error(f"network error contacting NIFC fire service: {exc.reason}", source_url=url)
    except ValueError as exc:
        return _error(f"could not parse NIFC fire response: {exc}", source_url=url)
    except Exception as exc:  # defensive: never crash the orchestrator
        return _error(f"unexpected error calling NIFC fire service: {type(exc).__name__}: {exc}", source_url=url)

    if isinstance(payload, dict) and payload.get("error"):
        return _error(f"NIFC fire query error: {payload['error']}", source_url=url)

    fires = parse_fire_features(payload.get("features", []))[:max_fires]
    years = [f["year"] for f in fires if f["year"] is not None]
    result = {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "latitude": lat,
        "longitude": lon,
        "burned": len(fires) > 0,
        "fire_count": len(fires),
        "most_recent_year": max(years) if years else None,
        "fires": fires,
        "source_url": url,
    }
    if not fires:
        result["note"] = (
            "No recorded wildfire perimeter intersects this exact point in the NIFC "
            "history dataset. This is not proof the area never burned — coverage is "
            "US-focused and perimeter-based, and small/old/unmapped fires may be absent."
        )
    return result


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import sys

    if len(sys.argv) >= 3:
        latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
    else:
        latitude, longitude = 39.7596, -121.6219  # Paradise, CA (2018 Camp Fire)
    print(json.dumps(fire_history_at(latitude, longitude), indent=2))
