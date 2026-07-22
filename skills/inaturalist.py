"""iNaturalist skill — recent, photo-backed species observations at a location.

Complements the GBIF occurrences skill: GBIF gives aggregate historical counts,
while iNaturalist returns RECENT, research-grade observations WITH PHOTOS and
links to each observation — useful for visually verifying a camera-trap ID
against what people have recently photographed nearby.

Data source (verified 2026-07, keyless):
  iNaturalist API v1.
    GET https://api.inaturalist.org/v1/observations
        ?lat=..&lng=..&radius=<km>&quality_grade=research&photos=true&order_by=observed_on
    GET https://api.inaturalist.org/v1/observations/species_counts?lat=..&lng=..&radius=<km>
  Returns observations (taxon, date, photo URL, observation URL, place) and a
  distinct-species tally.

Not redundant with GBIF: the value here is photos + recency + human-verified
research grade. Empty results are reported honestly.

Stdlib only; synchronous (the async orchestrator wraps it in
``asyncio.to_thread``). Pure parsers are split out for offline tests.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SKILL_NAME = "inaturalist"
SOURCE_LABEL = "iNaturalist"
API = "https://api.inaturalist.org/v1"
_UA = "geo-research-orchestrator/0.1 (WashU environmental research)"
MAX_RADIUS_KM = 50.0


def _error(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": msg, **extra}


def _taxon_name(taxon: dict[str, Any]) -> str | None:
    return (taxon or {}).get("preferred_common_name") or (taxon or {}).get("name")


def parse_observations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure: iNat observations -> list with photo + observation links."""
    out: list[dict[str, Any]] = []
    for o in (payload.get("results") or []):
        taxon = o.get("taxon") or {}
        photos = o.get("photos") or []
        photo_url = None
        if photos and photos[0].get("url"):
            # square thumbnail -> medium for a more useful image
            photo_url = photos[0]["url"].replace("/square.", "/medium.")
        out.append(
            {
                "common_name": taxon.get("preferred_common_name"),
                "scientific_name": taxon.get("name"),
                "observed_on": o.get("observed_on"),
                "quality_grade": o.get("quality_grade"),
                "place_guess": o.get("place_guess"),
                "photo_url": photo_url,
                "observation_url": o.get("uri"),
            }
        )
    return out


def parse_species_counts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure: iNat species_counts -> list of {name, scientific_name, count, url}."""
    out: list[dict[str, Any]] = []
    for s in (payload.get("results") or []):
        taxon = s.get("taxon") or {}
        tid = taxon.get("id")
        out.append(
            {
                "common_name": taxon.get("preferred_common_name"),
                "scientific_name": taxon.get("name"),
                "observation_count": s.get("count"),
                "taxon_url": f"https://www.inaturalist.org/taxa/{tid}" if tid else None,
            }
        )
    return out


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def observations_near(
    lat: float,
    lon: float,
    *,
    radius_km: float = 10.0,
    quality_grade: str = "research",
    per_page: int = 10,
    top_species: int = 8,
    timeout: float = 40.0,
) -> dict[str, Any]:
    """Recent photo observations + top species near (lat, lon). Shared contract.

    Returns recent research-grade observations (with photos/links) and a
    distinct-species summary. The two sub-queries fail independently (partial
    success); ``ok=False`` only if both fail or input is invalid. Empty results
    are reported honestly.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return _error(f"latitude/longitude must be numbers, got ({lat!r}, {lon!r})")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return _error(f"coordinates out of range: lat={lat}, lon={lon}")
    radius_km = max(0.1, min(float(radius_km), MAX_RADIUS_KM))

    obs_params = {
        "lat": f"{lat}", "lng": f"{lon}", "radius": f"{radius_km:g}",
        "quality_grade": quality_grade, "photos": "true",
        "order": "desc", "order_by": "observed_on", "per_page": str(max(1, min(per_page, 50))),
    }
    obs_url = f"{API}/observations?" + urllib.parse.urlencode(obs_params)
    sc_url = f"{API}/observations/species_counts?" + urllib.parse.urlencode(
        {"lat": f"{lat}", "lng": f"{lon}", "radius": f"{radius_km:g}", "per_page": str(max(1, min(top_species, 20)))}
    )

    observations: list[dict[str, Any]] = []
    total_obs = 0
    obs_error: str | None = None
    try:
        p = _get_json(obs_url, timeout)
        total_obs = int(p.get("total_results", 0))
        observations = parse_observations(p)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
        obs_error = f"iNaturalist observations error: {exc}"
    except Exception as exc:
        obs_error = f"iNaturalist observations unexpected error: {type(exc).__name__}: {exc}"

    species: list[dict[str, Any]] = []
    total_species = 0
    sc_error: str | None = None
    try:
        p = _get_json(sc_url, timeout)
        total_species = int(p.get("total_results", 0))
        species = parse_species_counts(p)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
        sc_error = f"iNaturalist species_counts error: {exc}"
    except Exception as exc:
        sc_error = f"iNaturalist species_counts unexpected error: {type(exc).__name__}: {exc}"

    if obs_error and sc_error:
        return _error(f"both iNaturalist queries failed: {obs_error}; {sc_error}")

    result = {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "latitude": lat,
        "longitude": lon,
        "radius_km": radius_km,
        "total_observations": total_obs,
        "distinct_species": total_species,
        "top_species": species,
        "recent_observations": observations,
        "source_urls": {"observations": obs_url, "species_counts": sc_url},
    }
    notes = []
    if obs_error:
        notes.append(f"recent observations unavailable ({obs_error})")
    elif not observations:
        notes.append("no research-grade photo observations within the radius")
    if sc_error:
        notes.append(f"species summary unavailable ({sc_error})")
    if notes:
        result["note"] = "; ".join(notes)
    return result


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import sys

    if len(sys.argv) >= 3:
        latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
    else:
        latitude, longitude = 44.4237, -110.5885  # Yellowstone
    print(json.dumps(observations_near(latitude, longitude), indent=2))
