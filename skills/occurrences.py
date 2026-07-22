"""Species-occurrences skill — GBIF (Global Biodiversity Information Facility).

Answers "what species have actually been recorded near this location?" and
"is species X present here?" from real, citable occurrence records (museum
specimens, eBird, iNaturalist, and other datasets aggregated by GBIF). This
complements the IPaC skill (what *may* occur / is *listed*) with what has been
*observed*.

Data source (verified 2026-07, keyless):
  GET https://api.gbif.org/v1/occurrence/search
      ?geoDistance=<lat>,<lon>,<radius>km & ...
  GET https://api.gbif.org/v1/species/{key}          (resolve a taxon key)
  GET https://api.gbif.org/v1/species/match?name=... (match a name -> key)

Two modes:
  * No ``taxon``  -> a species summary near the point, built from GBIF's
    ``speciesKey`` FACET (an accurate distinct-species tally, not a biased
    sample of individual records), with each key resolved to a name.
  * With ``taxon`` -> match the name to a GBIF key, then count that taxon's
    occurrences near the point ("present near here: yes/no, N records").

Stdlib only; synchronous (the async orchestrator wraps it in
``asyncio.to_thread``). Pure helpers are split out for offline tests.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SKILL_NAME = "occurrences"
SOURCE_LABEL = "GBIF (Global Biodiversity Information Facility)"
API = "https://api.gbif.org/v1"
_UA = "geo-research-orchestrator/0.1 (WashU environmental research)"
MAX_RADIUS_KM = 50.0


def _error(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": msg, **extra}


def build_geo_distance(lat: float, lon: float, radius_km: float) -> str:
    """GBIF ``geoDistance`` value: '<lat>,<lon>,<radius>km'."""
    return f"{lat},{lon},{radius_km:g}km"


def parse_species_facets(payload: dict[str, Any]) -> list[tuple[str, int]]:
    """Pure: (speciesKey, count) pairs from an occurrence-search facet response."""
    facets = payload.get("facets") if isinstance(payload, dict) else None
    if not facets:
        return []
    counts = facets[0].get("counts") or []
    out: list[tuple[str, int]] = []
    for c in counts:
        key = c.get("name")
        if key is not None:
            out.append((str(key), int(c.get("count", 0))))
    return out


def summarize_match(match: dict[str, Any]) -> dict[str, Any] | None:
    """Pure: reduce a /species/match response to key fields, or None if no match."""
    if not isinstance(match, dict):
        return None
    key = match.get("usageKey")
    if not key or match.get("matchType") in (None, "NONE"):
        return None
    return {
        "taxon_key": key,
        "matched_name": match.get("scientificName"),
        "rank": match.get("rank"),
        "match_confidence": match.get("confidence"),
    }


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _resolve_species(key: str, timeout: float) -> dict[str, Any]:
    """Resolve a GBIF species key to name/common-name; tolerant of failure."""
    try:
        sp = _get_json(f"{API}/species/{urllib.parse.quote(key)}", timeout)
    except Exception:
        return {"scientific_name": None, "common_name": None, "taxon_key": key,
                "gbif_url": f"https://www.gbif.org/species/{key}"}
    return {
        "scientific_name": sp.get("scientificName"),
        "common_name": sp.get("vernacularName"),
        "taxon_key": key,
        "gbif_url": f"https://www.gbif.org/species/{key}",
    }


def occurrences_near(
    lat: float,
    lon: float,
    *,
    radius_km: float = 5.0,
    taxon: str | None = None,
    top: int = 10,
    timeout: float = 40.0,
) -> dict[str, Any]:
    """Species occurrences near (lat, lon). Returns the shared skill contract.

    Presence mode (``taxon`` given) reports whether that taxon has records near
    the point and how many. Summary mode lists the top species by record count.
    Empty results are reported honestly (``present=False`` / empty ``species``);
    bad input, network, HTTP, or parse errors return ``ok=False``.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return _error(f"latitude/longitude must be numbers, got ({lat!r}, {lon!r})")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return _error(f"coordinates out of range: lat={lat}, lon={lon}")
    radius_km = max(0.1, min(float(radius_km), MAX_RADIUS_KM))
    geo = build_geo_distance(lat, lon, radius_km)

    try:
        # ---- Presence mode -------------------------------------------------
        if taxon and taxon.strip():
            match = _get_json(f"{API}/species/match?" + urllib.parse.urlencode({"name": taxon.strip()}), timeout)
            matched = summarize_match(match)
            if matched is None:
                return {
                    "ok": True, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                    "latitude": lat, "longitude": lon, "radius_km": radius_km,
                    "queried_taxon": taxon.strip(), "matched": None, "present": None,
                    "note": f"GBIF could not match the name {taxon.strip()!r} to a known taxon.",
                    "source_url": "https://www.gbif.org/",
                }
            params = {"taxonKey": matched["taxon_key"], "geoDistance": geo, "limit": "0"}
            res = _get_json(f"{API}/occurrence/search?" + urllib.parse.urlencode(params), timeout)
            count = int(res.get("count", 0))
            return {
                "ok": True, "skill": SKILL_NAME, "source": SOURCE_LABEL,
                "latitude": lat, "longitude": lon, "radius_km": radius_km,
                "queried_taxon": taxon.strip(), "matched": matched,
                "present": count > 0, "occurrence_count": count,
                "gbif_url": f"https://www.gbif.org/species/{matched['taxon_key']}",
                "source_url": "https://www.gbif.org/occurrence/search?" + urllib.parse.urlencode(
                    {"taxon_key": matched["taxon_key"]}
                ),
                "note": None if count > 0 else "No GBIF records of this taxon within the search radius.",
            }

        # ---- Summary mode --------------------------------------------------
        top = max(1, min(int(top), 20))
        params = {"geoDistance": geo, "limit": "0", "facet": "speciesKey", "facetLimit": str(top)}
        res = _get_json(f"{API}/occurrence/search?" + urllib.parse.urlencode(params), timeout)
        total = int(res.get("count", 0))
        facet_counts = parse_species_facets(res)
        species = []
        for key, cnt in facet_counts:
            info = _resolve_species(key, timeout)
            info["count"] = cnt
            species.append(info)
        out = {
            "ok": True, "skill": SKILL_NAME, "source": SOURCE_LABEL,
            "latitude": lat, "longitude": lon, "radius_km": radius_km,
            "total_occurrences": total, "species": species,
            "source_url": "https://www.gbif.org/occurrence/search",
        }
        if total == 0:
            out["note"] = "GBIF has no occurrence records within the search radius."
        return out

    except urllib.error.HTTPError as exc:
        return _error(f"GBIF returned HTTP {exc.code}", status=exc.code)
    except urllib.error.URLError as exc:
        return _error(f"network error contacting GBIF: {exc.reason}")
    except ValueError as exc:
        return _error(f"could not parse GBIF response: {exc}")
    except Exception as exc:  # defensive: never crash the orchestrator
        return _error(f"unexpected error calling GBIF: {type(exc).__name__}: {exc}")


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import sys

    if len(sys.argv) >= 3:
        latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
        taxon_arg = sys.argv[3] if len(sys.argv) > 3 else None
    else:
        latitude, longitude, taxon_arg = 38.20, -90.70, None
    print(json.dumps(occurrences_near(latitude, longitude, taxon=taxon_arg), indent=2))
