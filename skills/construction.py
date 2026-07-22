"""Land-use / development skill — nationwide OSM land use + local zoning bonus.

Answers "what is the land use here, and (where available) how is it zoned / is
it in a flood plain?" — the regulatory/development-pressure context an
environmental researcher needs alongside land cover (satellite skill) and
pollution (contamination skill).

PRIMARY source — nationwide (verified 2026-07, keyless):
  OpenStreetMap Overpass API — nearest landuse/natural polygons at the point.
  Works anywhere in the US (and globally), so this skill is NOT limited to any
  one county. (Land COVER anywhere is the satellite/NLCD skill's job; this is
  human land *use* — residential/commercial/industrial/farmland/etc.)

BONUS source — St. Louis County only (verified 2026-07, keyless):
  Where the point falls in UNINCORPORATED St. Louis County, we ALSO attach the
  county's regulatory zoning district + flood-plain flag from its GIS server
  (AGS_Zoning MapServer, layer 3). This is supplemental detail, not the skill's
  coverage — everywhere else it is simply omitted.

  Two real quirks the county query works around (filed-worthy findings):
    1. The server 403s requests without a browser-like User-Agent.
    2. The service MISLABELS its spatial reference: it reports wkid 102696
       (State Plane MO East, feet) but the geometry is actually stored in
       Web Mercator meters (EPSG:3857). So we convert lat/lon -> Web Mercator
       ourselves and send it with inSR=102696, forcing NO server reprojection.
       (Letting the server reproject 4326<->102696 yields points in the Pacific.)

Stdlib only; synchronous (the async orchestrator wraps it in
``asyncio.to_thread``). Pure classification logic is split out for offline tests.
"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SKILL_NAME = "construction"
STL_ZONING_LAYER = (
    "https://maps.stlouisco.com/hosting/rest/services/Maps/AGS_Zoning/MapServer/3"
)
OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
ZONING_ORDINANCE_URL = (
    "https://library.municode.com/mo/st._louis_county/codes/code_of_ordinances"
    "?nodeId=TITXPLZO_CH1003ZOOR"
)
# The two data sources have OPPOSITE User-Agent requirements:
#   * St. Louis County GIS 403s requests WITHOUT a browser-like UA.
#   * Overpass 406s requests WITH a fake-browser (Mozilla) UA; it wants a
#     descriptive one. So we send a different UA to each.
_UA_ARCGIS = "Mozilla/5.0 (compatible; geo-research-orchestrator/0.1)"
_UA_OSM = "geo-research-orchestrator/0.1 (WashU environmental research)"
# The service's mislabeled SR — passing this makes the server skip reprojection.
_NATIVE_SR = "102696"


def _result(**kw: Any) -> dict[str, Any]:
    base = {"ok": True, "skill": SKILL_NAME}
    base.update(kw)
    return base


def _error(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "skill": SKILL_NAME, "error": msg, **extra}


def _to_web_mercator(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 lat/lon -> Web Mercator (EPSG:3857) meters."""
    r = 6378137.0
    x = r * math.radians(lon)
    y = r * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def classify_zoning_code(code: str | None) -> dict[str, Any]:
    """Pure: interpret a St. Louis County zoning code.

    Uses the county's documented prefix convention (Ch. 1003 SLCRO): NU=Non-Urban,
    FP=Flood Plain overlay, R=Residential, C=Commercial, M=Industrial, MXD=Mixed
    Use. The raw code is always preserved; unrecognized codes are labeled
    "Specialized/Other" rather than guessed. ``is_floodplain`` flags the FP
    overlay — an environmentally meaningful signal (mapped flood hazard/floodway).
    """
    raw = (code or "").strip()
    norm = raw.upper().replace("-", "").replace(" ", "")
    if not norm:
        return {"code": raw, "category": "Unknown", "is_floodplain": False,
                "label": "No zoning code recorded"}

    is_fp = norm.startswith("FP")
    base = norm[2:] if is_fp else norm

    if base == "":
        category = "Flood Plain"
    elif base.startswith("NU"):
        category = "Non-Urban (rural/agricultural)"
    elif base == "MXD":
        category = "Mixed-Use Development"
    elif base.startswith("R"):
        category = "Residential"
    elif base.startswith("C"):
        category = "Commercial"
    elif base.startswith("M"):  # M1/M2/M3/MI — industrial/manufacturing
        category = "Industrial/Manufacturing"
    elif base.startswith(("PS", "KP")):
        category = f"Specialized district ({base})"
    else:
        category = "Other/Specialized"

    if is_fp and base:
        label = f"Flood Plain overlay + {category} (code {raw})"
    elif is_fp:
        label = f"Flood Plain District (code {raw})"
    else:
        label = f"{category} (code {raw})"

    return {"code": raw, "category": category, "is_floodplain": is_fp, "label": label}


def _http_json(
    url: str, *, data: bytes | None = None, timeout: float = 30.0, user_agent: str = _UA_ARCGIS
) -> dict[str, Any]:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def query_stl_zoning(lat: float, lon: float, *, timeout: float = 30.0) -> tuple[str | None, str]:
    """Query the county zoning layer at a point. Returns (zoning_code_or_None, url).

    None means the point is outside the unincorporated-county coverage (no
    error). Raises on network/HTTP/parse failure so the caller can decide.
    """
    x, y = _to_web_mercator(lat, lon)
    params = {
        "geometry": f"{x},{y}",
        "geometryType": "esriGeometryPoint",
        "inSR": _NATIVE_SR,  # mislabeled SR -> no server-side reprojection
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "ZONING",
        "returnGeometry": "false",
        "f": "json",
    }
    url = f"{STL_ZONING_LAYER}/query?{urllib.parse.urlencode(params)}"
    payload = _http_json(url, timeout=timeout)
    if "error" in payload:  # ArcGIS reports query errors in the body, HTTP 200
        raise RuntimeError(f"ArcGIS error: {payload['error']}")
    feats = payload.get("features") or []
    if not feats:
        return None, url
    code = (feats[0].get("attributes") or {}).get("ZONING")
    return code, url


def query_osm_landuse(lat: float, lon: float, *, radius: int = 100, timeout: float = 30.0) -> list[dict[str, str]]:
    """Nearest OSM landuse/natural features around a point (keyless fallback).

    Returns a list of ``{"type", "value", "name"}`` dicts; an empty list means
    OSM has no such feature mapped nearby (reported honestly, not filled in).
    """
    ql = (
        f"[out:json][timeout:{int(timeout)}];"
        f'(way(around:{radius},{lat},{lon})["landuse"];'
        f' relation(around:{radius},{lat},{lon})["landuse"];'
        f' way(around:{radius},{lat},{lon})["natural"];);'
        "out tags center 8;"
    )
    data = urllib.parse.urlencode({"data": ql}).encode()
    payload = _http_json(OVERPASS_ENDPOINT, data=data, timeout=timeout, user_agent=_UA_OSM)
    out: list[dict[str, str]] = []
    for el in payload.get("elements", []):
        tags = el.get("tags", {}) or {}
        if "landuse" in tags:
            out.append({"type": "landuse", "value": tags["landuse"], "name": tags.get("name", "")})
        elif "natural" in tags:
            out.append({"type": "natural", "value": tags["natural"], "name": tags.get("name", "")})
    return out


def analyze_land_use(
    lat: float,
    lon: float,
    *,
    include_local_zoning: bool = True,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Land-use analysis at (lat, lon). Returns the shared skill contract.

    Nationwide-first: OpenStreetMap land use is the PRIMARY source (works
    anywhere). Where the point is in unincorporated St. Louis County, the
    county's regulatory zoning + flood-plain flag are ATTACHED as a bonus.
    ``ok=True`` covers the "no data here" case (honestly noted); ``ok=False``
    only when the primary source could not run and no local zoning was obtained.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return _error(f"latitude/longitude must be numbers, got ({lat!r}, {lon!r})")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return _error(f"coordinates out of range: lat={lat}, lon={lon}")

    # ---- PRIMARY (nationwide): OpenStreetMap land use ---------------------
    osm: list[dict[str, str]] = []
    osm_error: str | None = None
    try:
        osm = query_osm_landuse(lat, lon, timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        osm_error = f"network/HTTP error contacting OpenStreetMap Overpass: {exc}"
    except Exception as exc:
        osm_error = f"OpenStreetMap Overpass query failed: {type(exc).__name__}: {exc}"

    # ---- BONUS (St. Louis County only): regulatory zoning -----------------
    zoning: dict[str, Any] | None = None
    county_url: str | None = None
    if include_local_zoning:
        try:
            code, county_url = query_stl_zoning(lat, lon, timeout=timeout)
            if code and code.strip():
                zoning = classify_zoning_code(code)
        except Exception:
            # Supplemental only — a county-server failure never fails the skill.
            zoning, county_url = None, county_url

    # Skill only fails if the primary source errored AND no zoning was obtained.
    if osm_error and zoning is None:
        return _error(osm_error)

    source = "OpenStreetMap land use (nationwide)"
    if zoning is not None:
        source += " + St. Louis County regulatory zoning"

    result = _result(
        source=source,
        latitude=lat,
        longitude=lon,
        land_use=osm,
        osm_attribution="© OpenStreetMap contributors (ODbL)",
        local_zoning=zoning,  # None outside unincorporated St. Louis County
        source_urls={
            "land_use": "https://overpass-api.de/api/interpreter",
            **({"zoning": county_url, "zoning_ordinance": ZONING_ORDINANCE_URL} if zoning else {}),
        },
    )

    notes: list[str] = []
    if osm_error:
        notes.append(f"OpenStreetMap land use unavailable ({osm_error})")
    elif not osm:
        notes.append("OpenStreetMap has no land-use feature mapped near this point")
    if zoning is not None:
        notes.append("St. Louis County regulatory zoning attached (includes flood-plain flag)")
    elif include_local_zoning:
        notes.append(
            "regulatory zoning is only available for unincorporated St. Louis County; "
            "elsewhere this reflects OpenStreetMap land use"
        )
    if notes:
        result["note"] = "; ".join(notes)
    return result


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import sys

    if len(sys.argv) >= 3:
        latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
    else:
        latitude, longitude = 38.5370, -90.3560  # Concord, unincorporated STL County
    print(json.dumps(analyze_land_use(latitude, longitude), indent=2))
