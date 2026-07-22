"""Contamination skill — EPA-regulated facilities & compliance (EPA ECHO).

Adapted from the a2a-sean branch to the shared skill contract. Reports EPA-
regulated facilities near a point and their compliance/violation history.

IMPORTANT framing (preserved from the original): ECHO is a REGULATORY RECORD —
who is permitted/regulated and their compliance history — NOT a live
contamination measurement. It tells you what is regulated nearby, not whether
the soil/water/air is actually contaminated.

Data source (keyless): EPA ECHO REST services (echodata.epa.gov). get_facilities
returns a QueryID + per-program row counts; get_qid pages the facility rows.

Stdlib only; synchronous. Empty results and errors are reported honestly.
"""
from __future__ import annotations

import urllib.error
from typing import Any

from ._common import ECHO_BASE_URL, as_bool_flag, as_float, haversine_meters, http_get_json, validated_coords

SKILL_NAME = "contamination"
SOURCE_LABEL = "EPA ECHO (echodata.epa.gov)"
_METERS_PER_MILE = 1609.344


def find_contamination_sources(
    latitude: float,
    longitude: float,
    *,
    radius_miles: float = 1.0,
    max_results: int = 25,
    timeout: float = 25.0,
) -> dict[str, Any]:
    """EPA-regulated facilities + compliance status near a point. Shared contract."""
    try:
        latitude, longitude = validated_coords(latitude, longitude)
    except ValueError as exc:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": str(exc)}
    radius_miles = max(0.1, min(float(radius_miles), 50.0))
    max_results = max(1, min(int(max_results), 100))

    try:
        search = http_get_json(
            f"{ECHO_BASE_URL}.get_facilities",
            {"output": "JSON", "p_lat": latitude, "p_long": longitude, "p_radius": radius_miles},
            timeout=timeout,
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "error": f"EPA ECHO facility search failed: {exc}"}

    results = (search or {}).get("Results") or {}
    if results.get("Error"):
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "error": f"EPA ECHO error: {results['Error'].get('ErrorMessage')}"}

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

    base = {
        "ok": True, "skill": SKILL_NAME, "source": SOURCE_LABEL,
        "latitude": latitude, "longitude": longitude, "radius_miles": radius_miles,
        "summary": summary,
    }
    if not query_id or total_rows == 0:
        return {**base, "facilities": [], "note": "No EPA-regulated facilities found in this radius."}

    try:
        detail = http_get_json(f"{ECHO_BASE_URL}.get_qid", {"output": "JSON", "qid": query_id}, timeout=timeout)
        coords = http_get_json(
            f"{ECHO_BASE_URL}.get_qid", {"output": "JSON", "qid": query_id, "qcolumns": "1,6,17,18"}, timeout=timeout
        )
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
        return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "error": f"EPA ECHO facility detail lookup failed: {exc}"}

    facilities = ((detail or {}).get("Results") or {}).get("Facilities") or []
    coord_rows = ((coords or {}).get("Results") or {}).get("Facilities") or []
    lon_by_registry = {r.get("RegistryID"): as_float(r.get("FacLong")) for r in coord_rows if r.get("RegistryID")}

    enriched: list[dict[str, Any]] = []
    for fac in facilities:
        fac_lat = as_float(fac.get("FacLat"))
        fac_lon = lon_by_registry.get(fac.get("RegistryID"))
        distance = (
            round(haversine_meters(latitude, longitude, fac_lat, fac_lon) / _METERS_PER_MILE, 2)
            if fac_lat is not None and fac_lon is not None else None
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
                "significant_violator": as_bool_flag(fac.get("FacSNCFlg")),
                "quarters_in_noncompliance": fac.get("FacQtrsWithNC"),
                "high_priority_air_violator": as_bool_flag(fac.get("CAAHpvFlag")),
                "clean_air_act_status": fac.get("CAAComplianceStatus"),
                "clean_water_act_status": fac.get("CWAComplianceStatus"),
                "rcra_hazardous_waste_status": fac.get("RCRAComplianceStatus"),
                "drinking_water_status": fac.get("SDWAComplianceStatus"),
                "toxics_release_inventory_reporter": as_bool_flag(fac.get("TRIFlag")),
                "inspection_count": fac.get("FacInspectionCount"),
            }
        )

    enriched.sort(key=lambda f: (f["distance_miles"] is None, f["distance_miles"]))
    truncated = len(enriched) > max_results
    shown = enriched[:max_results]
    return {
        **base,
        "facilities_returned": len(shown),
        "facilities": shown,
        "note": (
            f"Showing nearest {len(shown)} of {len(enriched)} facilities (ECHO reported {total_rows} "
            "total rows across all programs); narrow radius_miles for a shorter list. "
            "ECHO is a regulatory/compliance record, not a contamination measurement."
            if truncated
            else "ECHO is a regulatory/compliance record, not a contamination measurement."
        ),
    }


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import json
    import sys

    if len(sys.argv) >= 3:
        la, lo = float(sys.argv[1]), float(sys.argv[2])
    else:
        la, lo = 38.63, -90.20
    print(json.dumps(find_contamination_sources(la, lo), indent=2))
