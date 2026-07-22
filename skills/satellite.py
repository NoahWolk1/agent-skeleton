"""Satellite skill — land-cover / habitat classification at coordinates.

Answers "what habitat / land cover is at this point?" using the National Land
Cover Database (NLCD) — a 30 m, Landsat (satellite)-derived land-cover product
from the USGS/MRLC consortium. This is the fast, keyless, honest alternative to
raw satellite-imagery analysis (which would need Earth Engine auth and heavy
processing): NLCD gives an authoritative, citable land-cover class per pixel.

Data source (verified 2026-07, keyless):
  MRLC GeoServer WMS GetFeatureInfo point query
  GET https://www.mrlc.gov/geoserver/mrlc_display/wms
      ?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetFeatureInfo
      &LAYERS=NLCD_2021_Land_Cover_L48&QUERY_LAYERS=NLCD_2021_Land_Cover_L48
      &SRS=EPSG:4326&BBOX=<box>&WIDTH=101&HEIGHT=101&X=50&Y=50
      &INFO_FORMAT=application/json&FEATURE_COUNT=1
  response: {"features": [{"properties": {"PALETTE_INDEX": <nlcd_code>}}]}

Coverage: the ``_L48`` layers are the conterminous US (lower 48). Alaska,
Hawaii, and Puerto Rico have their own NLCD layers; a point outside CONUS
returns an explicit "no coverage" note rather than a made-up class.

Stdlib only; synchronous (the async orchestrator wraps it in
``asyncio.to_thread``). The parsing/legend logic is split out so it is
unit-testable offline without a network.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SKILL_NAME = "satellite"
WMS_BASE = "https://www.mrlc.gov/geoserver/mrlc_display/wms"

# Discrete NLCD Land Cover years published for the lower-48 (from the service's
# GetCapabilities). Default to the most recent.
AVAILABLE_YEARS = (2001, 2004, 2006, 2008, 2011, 2013, 2016, 2019, 2021)
DEFAULT_YEAR = 2021

# Rough CONUS bounding box — used only to give a helpful note when a point is
# clearly outside the _L48 layer's coverage (the server would return no feature).
_CONUS = {"lat_min": 24.0, "lat_max": 50.0, "lon_min": -125.0, "lon_max": -66.0}

# NLCD legend: code -> (class name, description, coarse habitat category).
# Categories group the fine classes for habitat-level reasoning.
NLCD_LEGEND: dict[int, tuple[str, str, str]] = {
    11: ("Open Water", "Areas of open water, generally <25% vegetation/soil cover.", "Water"),
    12: ("Perennial Ice/Snow", "Areas with perennial ice/snow cover.", "Snow/Ice"),
    21: ("Developed, Open Space", "Mostly lawn grasses; parks, large-lot housing, golf courses.", "Developed"),
    22: ("Developed, Low Intensity", "Mix of constructed materials and vegetation; single-family housing.", "Developed"),
    23: ("Developed, Medium Intensity", "Mix of constructed materials and vegetation; denser housing.", "Developed"),
    24: ("Developed, High Intensity", "Highly developed; apartments, commercial/industrial, heavy infrastructure.", "Developed"),
    31: ("Barren Land", "Bedrock, scarps, sand, gravel; little vegetation.", "Barren"),
    41: ("Deciduous Forest", "Trees >5 m, >20% cover; >75% shed leaves seasonally.", "Forest"),
    42: ("Evergreen Forest", "Trees >5 m, >20% cover; >75% keep leaves year-round.", "Forest"),
    43: ("Mixed Forest", "Trees >5 m, >20% cover; neither deciduous nor evergreen >75%.", "Forest"),
    51: ("Dwarf Scrub", "Alaska only: dwarf shrubs <20 cm.", "Shrubland"),
    52: ("Shrub/Scrub", "Shrubs <5 m, >20% cover; young trees or arid shrubland.", "Shrubland"),
    71: ("Grassland/Herbaceous", "Graminoid/herbaceous vegetation, >80% cover; not tilled.", "Herbaceous"),
    72: ("Sedge/Herbaceous", "Alaska only: sedge/forb tundra.", "Herbaceous"),
    73: ("Lichens", "Alaska only: fruticose/foliose lichens.", "Herbaceous"),
    74: ("Moss", "Alaska only: mosses.", "Herbaceous"),
    81: ("Pasture/Hay", "Grasses/legumes/mixtures for grazing or hay; managed.", "Agriculture"),
    82: ("Cultivated Crops", "Row crops, small grains, orchards; actively tilled.", "Agriculture"),
    90: ("Woody Wetlands", "Forest/shrub with periodic soil/water saturation.", "Wetlands"),
    95: ("Emergent Herbaceous Wetlands", "Perennial herbaceous vegetation in saturated soil/water.", "Wetlands"),
}


def _result(**kw: Any) -> dict[str, Any]:
    base = {"ok": True, "skill": SKILL_NAME}
    base.update(kw)
    return base


def _error(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "skill": SKILL_NAME, "error": msg, **extra}


def describe_code(code: int | None) -> dict[str, Any]:
    """Pure: map an NLCD numeric code to a citable classification dict.

    Unknown/absent codes are reported as "Unclassified" — never invented.
    """
    if code is None:
        return {"code": None, "class": "No data", "description": "", "habitat_category": None}
    entry = NLCD_LEGEND.get(int(code))
    if entry is None:
        return {
            "code": int(code),
            "class": f"Unclassified (NLCD code {int(code)})",
            "description": "Code not present in the standard NLCD legend.",
            "habitat_category": None,
        }
    name, desc, category = entry
    return {"code": int(code), "class": name, "description": desc, "habitat_category": category}


def parse_feature_response(payload: dict[str, Any]) -> int | None:
    """Pure: pull the NLCD code out of a GetFeatureInfo JSON body.

    Reads ``PALETTE_INDEX`` (what this service returns), falling back to
    ``GRAY_INDEX``. Returns None when no feature/value is present (e.g. off-CONUS
    or beyond the raster extent) so the caller can say "no data" honestly.
    """
    if not isinstance(payload, dict):
        return None
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        return None
    props = features[0].get("properties") if isinstance(features[0], dict) else None
    if not isinstance(props, dict):
        return None
    value = props.get("PALETTE_INDEX")
    if value is None:
        value = props.get("GRAY_INDEX")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _build_url(lat: float, lon: float, layer: str, box: float) -> str:
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": layer,
        "QUERY_LAYERS": layer,
        "SRS": "EPSG:4326",  # 1.1.1 => axis order is lon,lat (x,y); avoids 1.3.0 pitfalls
        "BBOX": f"{lon - box},{lat - box},{lon + box},{lat + box}",
        "WIDTH": "101",
        "HEIGHT": "101",
        "X": "50",  # center pixel of the 101x101 image == the query point
        "Y": "50",
        "INFO_FORMAT": "application/json",
        "FEATURE_COUNT": "1",
    }
    return f"{WMS_BASE}?{urllib.parse.urlencode(params)}"


def classify_land_cover(
    lat: float,
    lon: float,
    *,
    year: int = DEFAULT_YEAR,
    box: float = 0.0008,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Classify NLCD land cover at (lat, lon). Returns the shared skill contract.

    On success: land-cover class + description + coarse habitat category, plus
    the exact query URL (for citation and reproducibility). Off-CONUS points and
    empty raster locations return ``ok=True`` with a null class and a ``note``;
    bad inputs / network / server errors return ``ok=False`` with a specific
    ``error``. Nothing is ever fabricated.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return _error(f"latitude/longitude must be numbers, got ({lat!r}, {lon!r})")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return _error(f"coordinates out of range: lat={lat}, lon={lon}")
    if year not in AVAILABLE_YEARS:
        return _error(
            f"unavailable NLCD year {year}; choose from {list(AVAILABLE_YEARS)}"
        )

    layer = f"NLCD_{year}_Land_Cover_L48"
    source_label = f"NLCD {year} Land Cover (MRLC/USGS)"
    url = _build_url(lat, lon, layer, box)

    outside_conus = not (
        _CONUS["lat_min"] <= lat <= _CONUS["lat_max"]
        and _CONUS["lon_min"] <= lon <= _CONUS["lon_max"]
    )

    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return _error(f"MRLC WMS returned HTTP {exc.code}", status=exc.code, source_url=url)
    except urllib.error.URLError as exc:
        return _error(f"network error contacting MRLC WMS: {exc.reason}", source_url=url)
    except Exception as exc:  # defensive: never crash the orchestrator
        return _error(f"unexpected error querying MRLC WMS: {type(exc).__name__}: {exc}", source_url=url)

    try:
        payload = json.loads(body)
    except ValueError as exc:
        return _error(f"could not parse MRLC WMS response: {exc}", source_url=url)

    code = parse_feature_response(payload)
    land_cover = describe_code(code)

    out = _result(
        source=source_label,
        latitude=lat,
        longitude=lon,
        year=year,
        land_cover=land_cover,
        source_url=url,
    )
    if code is None:
        out["note"] = (
            "no NLCD land-cover value at this location — "
            + (
                "the point is outside the conterminous-US (L48) coverage; "
                "Alaska/Hawaii/Puerto Rico use separate NLCD layers."
                if outside_conus
                else "it may fall outside the dataset extent (e.g. open ocean)."
            )
        )
    return out


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import sys

    if len(sys.argv) >= 3:
        latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
    else:
        latitude, longitude = 38.6270, -90.1994  # downtown St. Louis
    print(json.dumps(classify_land_cover(latitude, longitude), indent=2))
