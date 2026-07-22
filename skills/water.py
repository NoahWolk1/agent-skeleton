"""Water skill — streamflow (USGS NWIS) + water-quality monitoring (WQP).

Answers "what surface water is near this location, how much is flowing, and
where is water quality monitored?" — core context for contamination pathways
and aquatic-habitat questions.

Two keyless data sources (verified 2026-07):
  * USGS NWIS Instantaneous Values — latest streamflow (param 00060, ft³/s) and
    gage height (00065, ft) for gages in a bounding box.
      GET https://waterservices.usgs.gov/nwis/iv/?format=json&bBox=...&parameterCd=00060,00065&siteStatus=active
  * Water Quality Portal (EPA/USGS) — monitoring stations within a radius.
      GET https://www.waterqualitydata.us/data/Station/search?lat=..&long=..&within=<mi>&mimeType=geojson

The two calls are independent: if one fails, the other's result is still
returned (partial success). Distances are computed locally (haversine) so the
nearest gages/stations come first. Empty results are reported honestly.

Stdlib only; synchronous (the async orchestrator wraps it in
``asyncio.to_thread``). Pure parsers are split out for offline tests.
"""
from __future__ import annotations

import html
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SKILL_NAME = "water"
SOURCE_LABEL = "USGS NWIS (streamflow) + Water Quality Portal (EPA/USGS)"
NWIS_IV = "https://waterservices.usgs.gov/nwis/iv/"
WQP_STATION = "https://www.waterqualitydata.us/data/Station/search"
_UA = "geo-research-orchestrator/0.1 (WashU environmental research)"
_KM_PER_MILE = 1.609344


def _error(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": msg, **extra}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _get_json(url: str, timeout: float) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_nwis_iv(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure: NWIS IV JSON -> one dict per gage with latest streamflow/gage height.

    Combines the 00060 (streamflow) and 00065 (gage height) time series that
    share a site code. Missing values are left as None (never invented).
    """
    by_site: dict[str, dict[str, Any]] = {}
    series = (payload.get("value") or {}).get("timeSeries") or []
    for t in series:
        try:
            si = t["sourceInfo"]
            code = si["siteCode"][0]["value"]
            geo = si["geoLocation"]["geogLocation"]
            param = t["variable"]["variableCode"][0]["value"]
            vals = t["values"][0]["value"]
        except (KeyError, IndexError, TypeError):
            continue
        rec = by_site.setdefault(
            code,
            {
                "site_code": code,
                "site_name": html.unescape(si.get("siteName", "")),
                "latitude": geo.get("latitude"),
                "longitude": geo.get("longitude"),
                "streamflow_cfs": None,
                "gage_height_ft": None,
                "as_of": None,
            },
        )
        latest = vals[-1] if vals else None
        if not latest:
            continue
        value = latest.get("value")
        try:
            value = float(value)
        except (TypeError, ValueError):
            pass
        if param == "00060":
            rec["streamflow_cfs"] = value
        elif param == "00065":
            rec["gage_height_ft"] = value
        rec["as_of"] = latest.get("dateTime") or rec["as_of"]
    return list(by_site.values())


def parse_wqp_stations(geojson: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure: WQP station geojson -> list of monitoring stations with locations."""
    out: list[dict[str, Any]] = []
    for f in (geojson.get("features") or []):
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates") or [None, None]
        out.append(
            {
                "name": props.get("MonitoringLocationName"),
                "type": props.get("MonitoringLocationTypeName"),
                "organization": props.get("OrganizationFormalName"),
                "id": props.get("MonitoringLocationIdentifier"),
                "longitude": coords[0],
                "latitude": coords[1],
            }
        )
    return out


def _attach_distance_and_sort(items: list[dict[str, Any]], lat: float, lon: float) -> list[dict[str, Any]]:
    for it in items:
        try:
            it["distance_km"] = round(haversine_km(lat, lon, float(it["latitude"]), float(it["longitude"])), 2)
        except (TypeError, ValueError):
            it["distance_km"] = None
    items.sort(key=lambda x: (x["distance_km"] is None, x["distance_km"] or 0.0))
    return items


def water_at_location(
    lat: float,
    lon: float,
    *,
    radius_km: float = 8.0,
    max_gages: int = 3,
    max_stations: int = 10,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Nearby streamflow gages + water-quality stations at (lat, lon).

    Returns the shared skill contract. The two sub-queries fail independently
    (partial success); ``ok=False`` only if both fail or the input is invalid.
    Empty results are reported honestly.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return _error(f"latitude/longitude must be numbers, got ({lat!r}, {lon!r})")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return _error(f"coordinates out of range: lat={lat}, lon={lon}")

    # ---- USGS NWIS streamflow (bounding box) ------------------------------
    ddeg = radius_km / 111.0
    bbox = f"{lon - ddeg:.4f},{lat - ddeg:.4f},{lon + ddeg:.4f},{lat + ddeg:.4f}"
    nwis_url = NWIS_IV + "?" + urllib.parse.urlencode(
        {"format": "json", "bBox": bbox, "parameterCd": "00060,00065", "siteStatus": "active"}
    )
    gages: list[dict[str, Any]] = []
    nwis_error: str | None = None
    try:
        gages = _attach_distance_and_sort(parse_nwis_iv(_get_json(nwis_url, timeout)), lat, lon)[:max_gages]
    except urllib.error.HTTPError as exc:
        nwis_error = f"USGS NWIS HTTP {exc.code}"
    except (urllib.error.URLError, ValueError) as exc:
        nwis_error = f"USGS NWIS error: {exc}"
    except Exception as exc:
        nwis_error = f"USGS NWIS unexpected error: {type(exc).__name__}: {exc}"

    # ---- Water Quality Portal stations (radius) ---------------------------
    wqp_url = WQP_STATION + "?" + urllib.parse.urlencode(
        {"lat": f"{lat}", "long": f"{lon}", "within": f"{radius_km / _KM_PER_MILE:.2f}",
         "mimeType": "geojson", "zip": "no"}
    )
    stations: list[dict[str, Any]] = []
    station_total = 0
    wqp_error: str | None = None
    try:
        parsed = parse_wqp_stations(_get_json(wqp_url, timeout))
        station_total = len(parsed)
        stations = _attach_distance_and_sort(parsed, lat, lon)[:max_stations]
    except urllib.error.HTTPError as exc:
        wqp_error = f"Water Quality Portal HTTP {exc.code}"
    except (urllib.error.URLError, ValueError) as exc:
        wqp_error = f"Water Quality Portal error: {exc}"
    except Exception as exc:
        wqp_error = f"Water Quality Portal unexpected error: {type(exc).__name__}: {exc}"

    if nwis_error and wqp_error:
        return _error(f"both water services failed: {nwis_error}; {wqp_error}")

    result: dict[str, Any] = {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "latitude": lat,
        "longitude": lon,
        "radius_km": radius_km,
        "streamflow_gages": gages,
        "water_quality_stations": {"total_within_radius": station_total, "nearest": stations},
        "source_urls": {"streamflow": nwis_url, "water_quality": wqp_url},
    }
    notes = []
    if nwis_error:
        notes.append(f"streamflow unavailable ({nwis_error})")
    elif not gages:
        notes.append("no active USGS streamflow gages within the radius")
    if wqp_error:
        notes.append(f"water-quality stations unavailable ({wqp_error})")
    elif station_total == 0:
        notes.append("no water-quality monitoring stations within the radius")
    if notes:
        result["note"] = "; ".join(notes)
    return result


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import sys

    if len(sys.argv) >= 3:
        latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
    else:
        latitude, longitude = 38.63, -90.20  # St. Louis riverfront
    print(json.dumps(water_at_location(latitude, longitude), indent=2))
