"""find_contamination_sources -> EPA ECHO, nearby regulated facilities and
their compliance/violation status.

ECHO is a regulatory record (who's permitted/regulated and their compliance
history), not a live contamination sensor - see prompt.py's SYSTEM_PROMPT for
how the agent is told to frame that.
"""
from __future__ import annotations

import urllib.error
from typing import Any

from ..config import ECHO_BASE_URL
from .helpers import _as_bool_flag, _as_float, _haversine_meters, _http_get_json

_METERS_PER_MILE = 1609.344


def find_contamination_sources(
    *,
    latitude: float,
    longitude: float,
    radius_miles: float = 1.0,
    max_results: int = 25,
) -> dict[str, Any]:
    """Look up EPA-regulated facilities near a point via the EPA ECHO database.
    Returns program-level summary counts (CAA, CWA, RCRA, TRI, inspections,
    penalties) plus the nearest facilities and their compliance/violation
    status.

    Keep in mind this is a regulatory record, not a contamination measurement
    - it tells you what's regulated nearby and its compliance history, not
    whether the soil/water/air is actually contaminated.
    """
    radius_miles = max(0.1, min(float(radius_miles), 50.0))
    max_results = max(1, min(int(max_results), 100))

    try:
        search = _http_get_json(
            f"{ECHO_BASE_URL}.get_facilities",
            {"output": "JSON", "p_lat": latitude, "p_long": longitude, "p_radius": radius_miles},
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {"ok": False, "error": f"EPA ECHO facility search failed: {exc}"}

    results = (search or {}).get("Results") or {}
    if results.get("Error"):
        return {"ok": False, "error": f"EPA ECHO error: {results['Error'].get('ErrorMessage')}"}

    query_id = results.get("QueryID")
    total_rows = int(results.get("QueryRows") or 0)
    summary = {
        "total_facilities": total_rows,
        "clean_air_act_facilities": results.get("CAARows"),
        "clean_water_act_facilities": results.get("CWARows"),
        "rcra_hazardous_waste_facilities": results.get("RCRRows"),
        "toxics_release_inventory_facilities": results.get("TRIRows"),
        "inspections_on_record": results.get("INSPRows"),
        "formal_enforcement_actions": results.get("FEARows"),
        "informal_enforcement_actions": results.get("InfFEARows"),
        "total_penalties": results.get("TotalPenalties"),
    }

    if not query_id or total_rows == 0:
        return {
            "ok": True,
            "latitude": latitude,
            "longitude": longitude,
            "radius_miles": radius_miles,
            "summary": summary,
            "facilities": [],
            "note": "No EPA-regulated facilities found in this radius.",
            "source": "EPA ECHO (echodata.epa.gov)",
        }

    try:
        detail = _http_get_json(f"{ECHO_BASE_URL}.get_qid", {"output": "JSON", "qid": query_id})
        coords = _http_get_json(
            f"{ECHO_BASE_URL}.get_qid", {"output": "JSON", "qid": query_id, "qcolumns": "1,6,17,18"}
        )
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return {"ok": False, "error": f"EPA ECHO facility detail lookup failed: {exc}"}

    facilities = ((detail or {}).get("Results") or {}).get("Facilities") or []
    coord_rows = ((coords or {}).get("Results") or {}).get("Facilities") or []
    longitude_by_registry = {
        row.get("RegistryID"): _as_float(row.get("FacLong")) for row in coord_rows if row.get("RegistryID")
    }

    enriched: list[dict[str, Any]] = []
    for fac in facilities:
        fac_lat = _as_float(fac.get("FacLat"))
        fac_lon = longitude_by_registry.get(fac.get("RegistryID"))
        distance = (
            round(_haversine_meters(latitude, longitude, fac_lat, fac_lon) / _METERS_PER_MILE, 2)
            if fac_lat is not None and fac_lon is not None
            else None
        )
        enriched.append(
            {
                "name": fac.get("FacName"),
                "registry_id": fac.get("RegistryID"),
                "address": ", ".join(
                    p for p in [fac.get("FacStreet"), fac.get("FacCity"), fac.get("FacState"), fac.get("FacZip")] if p
                ),
                "latitude": fac_lat,
                "longitude": fac_lon,
                "distance_miles": distance,
                "significant_violator": _as_bool_flag(fac.get("FacSNCFlg")),
                "quarters_in_noncompliance": fac.get("FacQtrsWithNC"),
                "high_priority_air_violator": _as_bool_flag(fac.get("CAAHpvFlag")),
                "clean_air_act_status": fac.get("CAAComplianceStatus"),
                "clean_water_act_status": fac.get("CWAComplianceStatus"),
                "rcra_hazardous_waste_status": fac.get("RCRAComplianceStatus"),
                "drinking_water_status": fac.get("SDWAComplianceStatus"),
                "toxics_release_inventory_reporter": _as_bool_flag(fac.get("TRIFlag")),
                "inspection_count": fac.get("FacInspectionCount"),
            }
        )

    enriched.sort(key=lambda f: (f["distance_miles"] is None, f["distance_miles"]))
    truncated = len(enriched) > max_results
    shown = enriched[:max_results]

    return {
        "ok": True,
        "latitude": latitude,
        "longitude": longitude,
        "radius_miles": radius_miles,
        "summary": summary,
        "facilities_returned": len(shown),
        "facilities": shown,
        "note": (
            f"Showing nearest {len(shown)} of {len(enriched)} facilities returned by ECHO "
            f"(query reported {total_rows} total rows across all programs); narrow radius_miles for a shorter list."
            if truncated
            else None
        ),
        "source": "EPA ECHO (echodata.epa.gov)",
    }
