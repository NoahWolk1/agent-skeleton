"""Species & critical-habitat skill — USFWS IPaC Location API.

Answers "what ESA-listed species, critical habitat, and migratory birds may
occur at this location?" — the regulatory/biological context for habitat-
suitability and camera-trap questions. Authoritative federal source.

Data source (verified 2026-07):
  POST https://ipac.ecosphere.fws.gov/location/api/resources
  body: {"location.footprint": "<GeoJSON geometry string>", "locationFormat": "GeoJSON"}
  IPaC accepts POLYGON/MULTIPOLYGON/LINESTRING (no POINT), so a coordinate is
  buffered into a small square polygon.
  response: {"resources": {"populationsBySid": {...ESA species...},
                            "migbirds": [...], "crithabs": [...],
                            "fieldOffices": [...]}, "warning": ...}

Identity / future credential requirement (important):
  IPaC returns a warning that it will SOON REJECT requests lacking identifying
  headers — a ``From`` header (contact email) plus ``X-Organization`` and/or
  ``X-Project``. We send these now (configurable via args or the
  IPAC_CONTACT_EMAIL / IPAC_ORGANIZATION / IPAC_PROJECT env vars) so the skill
  keeps working when that requirement lands. The contact email is identity, not
  a secret; it is read from config, never hard-coded to a real person.

Also note: FWS has said the Location API "will eventually require an API key."
When that happens, the key should be read from the agent credential context.

Stdlib only; synchronous (the async orchestrator wraps it in
``asyncio.to_thread``). Response parsing is split out for offline tests.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SKILL_NAME = "species_habitat"
SOURCE_LABEL = "USFWS IPaC (Information for Planning and Consultation)"
IPAC_URL = "https://ipac.ecosphere.fws.gov/location/api/resources"

# Defaults used to identify the caller to IPaC (see module docstring). These are
# non-secret identity values; override via args or env for real deployments.
DEFAULT_ORGANIZATION = "WashU-DTRC-Research"
DEFAULT_PROJECT = "geo-research-orchestrator"


def _error(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": msg, **extra}


def _footprint_polygon(lat: float, lon: float, d: float) -> str:
    """A small square polygon (GeoJSON string) around a point — IPaC needs an area."""
    ring = [
        [lon - d, lat - d], [lon + d, lat - d],
        [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d],
    ]
    return json.dumps({"type": "Polygon", "coordinates": [ring]})


def _species_profile_url(sp: dict[str, Any]) -> str | None:
    url = sp.get("speciesProfileUrl")
    if url:
        return url
    sid = sp.get("speciesId")
    return f"https://ecos.fws.gov/ecp/species/{sid}" if sid else None


def parse_ipac_resources(resources: dict[str, Any]) -> dict[str, Any]:
    """Pure: reduce IPaC's ``resources`` block to the fields we surface.

    Extracts ESA-listed species (from ``populationsBySid``, whose embedded
    ``population`` holds the detail and ``crithabInFootprint`` the flag),
    critical habitat, migratory birds, and the FWS field office. Missing
    sections yield empty lists — never invented entries.
    """
    out: dict[str, Any] = {
        "esa_species": [],
        "critical_habitat": [],
        "migratory_birds": [],
        "field_office": None,
    }
    if not isinstance(resources, dict):
        return out

    for entry in (resources.get("populationsBySid") or {}).values():
        if not isinstance(entry, dict):
            continue
        sp = entry.get("population") or {}
        common = sp.get("optionalCommonName") or sp.get("shortName")
        crithab_here = bool(entry.get("crithabInFootprint"))
        out["esa_species"].append(
            {
                "common_name": common,
                "scientific_name": sp.get("optionalScientificName"),
                "group": sp.get("groupName"),
                "listing_status": sp.get("listingStatusName"),
                "profile_url": _species_profile_url(sp),
                "critical_habitat_in_area": crithab_here,
            }
        )
        if crithab_here:
            out["critical_habitat"].append({"species": common, "profile_url": _species_profile_url(sp)})

    # Top-level critical-habitat entries (shape varies; extract defensively).
    for ch in resources.get("crithabs") or []:
        if isinstance(ch, dict):
            label = ch.get("commonName") or ch.get("speciesName") or ch.get("name")
            out["critical_habitat"].append({"species": label})

    for mb in resources.get("migbirds") or []:
        if isinstance(mb, dict):
            # The species detail is nested under ``phenologySpecies``.
            ph = mb.get("phenologySpecies") or {}
            name = ph.get("commonName") or mb.get("commonName") or mb.get("name")
            if name:
                out["migratory_birds"].append(name)

    offices = resources.get("fieldOffices") or []
    if offices and isinstance(offices[0], dict):
        fo = offices[0]
        out["field_office"] = {
            "name": fo.get("officeName"),
            "phone": fo.get("formattedPhone"),
            "city": fo.get("formattedPhysicalCity"),
            "state": fo.get("formattedPhysicalState"),
        }
    return out


def _identity_headers(contact_email: str | None, organization: str | None, project: str | None) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Organization": organization or os.getenv("IPAC_ORGANIZATION") or DEFAULT_ORGANIZATION,
        "X-Project": project or os.getenv("IPAC_PROJECT") or DEFAULT_PROJECT,
    }
    email = contact_email or os.getenv("IPAC_CONTACT_EMAIL")
    if email:
        headers["From"] = email
    return headers


def species_at_location(
    lat: float,
    lon: float,
    *,
    radius_deg: float = 0.02,
    contact_email: str | None = None,
    organization: str | None = None,
    project: str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """ESA species / critical habitat / migratory birds at (lat, lon) via IPaC.

    Returns the shared skill contract. A location with no listed species returns
    ``ok=True`` with empty lists and a ``note`` (honest "none found"); bad input,
    network, HTTP, or parse failures return ``ok=False`` with a specific error.
    ``radius_deg`` sets the half-width of the queried box (~0.02° ≈ 2 km).
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return _error(f"latitude/longitude must be numbers, got ({lat!r}, {lon!r})")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return _error(f"coordinates out of range: lat={lat}, lon={lon}")

    body = json.dumps(
        {"location.footprint": _footprint_polygon(lat, lon, radius_deg), "locationFormat": "GeoJSON"}
    ).encode()
    headers = _identity_headers(contact_email, organization, project)
    req = urllib.request.Request(IPAC_URL, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return _error(f"IPaC returned HTTP {exc.code}", status=exc.code)
    except urllib.error.URLError as exc:
        return _error(f"network error contacting IPaC: {exc.reason}")
    except ValueError as exc:
        return _error(f"could not parse IPaC response: {exc}")
    except Exception as exc:  # defensive: never crash the orchestrator
        return _error(f"unexpected error calling IPaC: {type(exc).__name__}: {exc}")

    parsed = parse_ipac_resources(payload.get("resources") or {})
    result = {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "latitude": lat,
        "longitude": lon,
        "query_area_deg": radius_deg,
        **parsed,
        "source_url": "https://ipac.ecosphere.fws.gov/",
    }
    counts = (
        len(parsed["esa_species"]),
        len(parsed["critical_habitat"]),
        len(parsed["migratory_birds"]),
    )
    if counts == (0, 0, 0):
        result["note"] = "IPaC reports no ESA species, critical habitat, or migratory birds for this area."
    # Surface IPaC's own advisory (e.g. the identifying-headers requirement).
    if payload.get("warning"):
        result["service_warning"] = payload["warning"]
    return result


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import sys

    if len(sys.argv) >= 3:
        latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
    else:
        latitude, longitude = 38.20, -90.70  # rural Jefferson County, MO
    print(json.dumps(species_at_location(latitude, longitude), indent=2))
