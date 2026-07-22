"""Protected-areas skill — USGS PAD-US (Protected Areas Database of the US).

Answers "is this location in or near a protected area (park, refuge, wilderness,
conservation easement), and how strongly is it protected?" — context for
habitat-suitability and development-impact questions.

Data source (verified 2026-07, keyless):
  ArcGIS Online-hosted PAD-US v3.0 FeatureServer (published by USGS GAP)
  https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/Manager_Name/FeatureServer/0
  /query with a small ENVELOPE buffer around the point (see below), intersects.

Why a buffer, not a bare point: PAD-US polygon geometry is generalized, so an
exact-point intersects MISSES real protected areas (e.g. a point inside
Shenandoah NP returned nothing). A small envelope buffer reliably catches them,
so results are reported as "at or within ~Nm of the point." A zero result means
"no PAD-US protected area near this point" — which can be a TRUE negative (e.g.
private inholdings inside a checkerboard national forest); we never assert an
area is "unprotected," only that PAD-US shows nothing nearby.

Coded-value domains (designation, owner/manager type, GAP status, access) are
embedded verbatim from the service's own metadata — decoded, never invented;
unknown codes pass through raw.

Stdlib only; synchronous (the async orchestrator wraps it in
``asyncio.to_thread``). Decoding/dedup logic is split out for offline tests.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SKILL_NAME = "protected_areas"
SOURCE_LABEL = "USGS PAD-US v3.0 (Protected Areas Database of the United States)"
PADUS_LAYER = (
    "https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/"
    "Manager_Name/FeatureServer/0"
)
_UA = "geo-research-orchestrator/0.1 (WashU environmental research)"
_OUT_FIELDS = "Unit_Nm,Loc_Nm,Des_Tp,Own_Type,Own_Name,Mang_Type,Mang_Name,GAP_Sts,Pub_Access,State_Nm,GIS_Acres"

# --- Coded-value domains (verbatim from the service metadata) --------------
OWN_MANG_TYPE = {
    "FED": "Federal", "TRIB": "American Indian Lands", "STAT": "State",
    "DIST": "Regional Agency Special District", "LOC": "Local Government",
    "NGO": "Non-Governmental Organization", "PVT": "Private", "JNT": "Joint",
    "UNK": "Unknown", "TERR": "Territorial", "DESG": "Designation",
}
PUB_ACCESS = {"OA": "Open Access", "RA": "Restricted Access", "XA": "Closed", "UK": "Unknown"}
GAP_STS = {
    "1": "1 - managed for biodiversity - disturbance events proceed or are mimicked",
    "2": "2 - managed for biodiversity - disturbance events suppressed",
    "3": "3 - managed for multiple uses - subject to extractive (e.g. mining or logging) or OHV use",
    "4": "4 - no known mandate for biodiversity protection",
}
DES_TP = {
    "NP": "National Park", "NM": "National Monument", "NCA": "Conservation Area",
    "NF": "National Forest", "NG": "National Grassland", "PUB": "National Public Lands",
    "NT": "National Scenic or Historic Trail", "NWR": "National Wildlife Refuge",
    "WA": "Wilderness Area", "WSR": "Wild and Scenic River", "WSA": "Wilderness Study Area",
    "MPA": "Marine Protected Area", "NRA": "National Recreation Area",
    "NSBV": "National Scenic, Botanical or Volcanic Area", "NLS": "National Lakeshore or Seashore",
    "IRA": "Inventoried Roadless Area", "ACEC": "Area of Critical Environmental Concern",
    "RNA": "Research Natural Area", "REC": "Recreation Management Area",
    "RMA": "Resource Management Area", "WPA": "Watershed Protection Area",
    "REA": "Research or Educational Area", "HCA": "Historic or Cultural Area",
    "MIT": "Mitigation Land or Bank", "MIL": "Military Land", "ACC": "Access Area",
    "SDA": "Special Designation Area", "PROC": "Approved or Proclamation Boundary",
    "FOTH": "Federal Other or Unknown", "ND": "Not Designated",
    "TRIBL": "Native American Land Area", "SP": "State Park", "SW": "State Wilderness",
    "SCA": "State Conservation Area", "SREC": "State Recreation Area",
    "SHCA": "State Historic or Cultural Area", "SRMA": "State Resource Management Area",
    "SOTH": "State Other or Unknown", "LP": "Local Park", "LCA": "Local Conservation Area",
    "LREC": "Local Recreation Area", "LHCA": "Local Historic or Cultural Area",
    "LRMA": "Local Resource Management Area", "LOTH": "Local Other or Unknown",
    "PCON": "Private Conservation", "PPRK": "Private Park",
    "PREC": "Private Recreation or Education", "PHCA": "Private Historic or Cultural",
    "PAGR": "Private Agricultural", "PRAN": "Private Ranch", "PFOR": "Private Forest Stewardship",
    "POTH": "Private Other or Unknown", "CONE": "Conservation Easement",
    "RECE": "Recreation or Education Easement", "HCAE": "Historic or Cultural Easement",
    "AGRE": "Agricultural Easement", "RANE": "Ranch Easement", "FORE": "Forest Stewardship Easement",
    "OTHE": "Other Easement", "UNKE": "Unknown Easement", "UNK": "Unknown",
    "OCS": "Outer Continental Shelf Area", "FACY": "Facility",
}


def _error(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": msg, **extra}


def _decode(mapping: dict[str, str], code: Any) -> Any:
    """Decode a coded value; pass unknown/blank codes through (never invent)."""
    if code is None:
        return None
    label = mapping.get(str(code))
    return label.strip() if label else code


def decode_feature(attrs: dict[str, Any]) -> dict[str, Any]:
    """Pure: turn a PAD-US feature's attributes into a decoded protected-area dict."""
    return {
        "name": attrs.get("Unit_Nm") or attrs.get("Loc_Nm") or None,
        "designation": _decode(DES_TP, attrs.get("Des_Tp")),
        "designation_code": attrs.get("Des_Tp"),
        "owner": attrs.get("Own_Name"),
        "owner_type": _decode(OWN_MANG_TYPE, attrs.get("Own_Type")),
        "manager": attrs.get("Mang_Name"),
        "manager_type": _decode(OWN_MANG_TYPE, attrs.get("Mang_Type")),
        "gap_status": _decode(GAP_STS, attrs.get("GAP_Sts")),
        "gap_status_code": attrs.get("GAP_Sts"),
        "public_access": _decode(PUB_ACCESS, attrs.get("Pub_Access")),
        "state": attrs.get("State_Nm"),
        "acres": attrs.get("GIS_Acres"),
    }


def dedupe_areas(areas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure: drop duplicate protected areas (PAD-US overlaps fee/designation rows)."""
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for a in areas:
        key = (a.get("name"), a.get("designation_code"), a.get("manager"))
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def analyze_protected_area(
    lat: float,
    lon: float,
    *,
    buffer_deg: float = 0.005,
    timeout: float = 40.0,
) -> dict[str, Any]:
    """Protected areas at/near (lat, lon) via PAD-US. Returns the shared contract.

    ``protected`` is True iff PAD-US shows one or more areas within the buffer.
    A zero result is reported honestly ("none within ~Nm") and never claims the
    location is unprotected. Bad input / network / HTTP / parse errors return
    ``ok=False``.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return _error(f"latitude/longitude must be numbers, got ({lat!r}, {lon!r})")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return _error(f"coordinates out of range: lat={lat}, lon={lon}")

    envelope = {
        "xmin": lon - buffer_deg, "ymin": lat - buffer_deg,
        "xmax": lon + buffer_deg, "ymax": lat + buffer_deg,
        "spatialReference": {"wkid": 4326},
    }
    params = {
        "geometry": json.dumps(envelope),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": _OUT_FIELDS,
        "returnGeometry": "false",
        "f": "json",
    }
    url = f"{PADUS_LAYER}/query?{urllib.parse.urlencode(params)}"
    approx_m = round(buffer_deg * 111320)  # deg latitude -> meters (approx)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return _error(f"PAD-US service returned HTTP {exc.code}", status=exc.code, source_url=url)
    except urllib.error.URLError as exc:
        return _error(f"network error contacting PAD-US: {exc.reason}", source_url=url)
    except ValueError as exc:
        return _error(f"could not parse PAD-US response: {exc}", source_url=url)
    except Exception as exc:  # defensive: never crash the orchestrator
        return _error(f"unexpected error calling PAD-US: {type(exc).__name__}: {exc}", source_url=url)

    if isinstance(payload, dict) and payload.get("error"):
        return _error(f"PAD-US query error: {payload['error']}", source_url=url)

    areas = dedupe_areas([decode_feature(f.get("attributes") or {}) for f in payload.get("features", [])])
    out = {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "latitude": lat,
        "longitude": lon,
        "search_buffer_m": approx_m,
        "protected": len(areas) > 0,
        "areas": areas,
        "source_url": url,
    }
    if not areas:
        out["note"] = (
            f"No PAD-US protected area within ~{approx_m} m of this point. This does "
            "not necessarily mean the location is unprotected — it may be private "
            "land (including inholdings within a larger unit) or not yet in PAD-US."
        )
    return out


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import sys

    if len(sys.argv) >= 3:
        latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
    else:
        latitude, longitude = 44.60, -110.50  # Yellowstone NP
    print(json.dumps(analyze_protected_area(latitude, longitude), indent=2))
