"""Air-quality skill — current pollutant levels + US AQI at a coordinate.

Answers "what is the air quality here right now?" — reinforcing the contamination
story with atmospheric exposure context (PM2.5, PM10, ozone, NO2, SO2, CO).

Data source (verified 2026-07, keyless, global):
  Open-Meteo Air Quality API — CAMS-model current concentrations + US AQI.
    GET https://air-quality-api.open-meteo.com/v1/air-quality
        ?latitude=..&longitude=..&current=us_aqi,pm2_5,pm10,ozone,...

  IMPORTANT — these are MODEL ESTIMATES (Copernicus CAMS), not direct station
  measurements. We label them as such so the agent never overstates them as
  measured readings. Station-measured data (OpenAQ v3) is more authoritative but
  now requires an API key; that could be added later, read from the credential
  context. (OpenAQ v1/v2 are retired; v3 returns 401 without X-API-Key.)

The US AQI value returned by the API is mapped to its EPA category (Good …
Hazardous) using the official AQI breakpoints — a standard mapping, not invented.

Stdlib only; synchronous (the async orchestrator wraps it in
``asyncio.to_thread``). Pure logic is split out for offline tests.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SKILL_NAME = "air_quality"
SOURCE_LABEL = "Open-Meteo Air Quality (Copernicus CAMS model estimates)"
ENDPOINT = "https://air-quality-api.open-meteo.com/v1/air-quality"
_UA = "geo-research-orchestrator/0.1 (WashU environmental research)"

_CURRENT_FIELDS = "us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide"

# Human-friendly pollutant labels keyed by the API field name.
_POLLUTANT_LABELS = {
    "pm2_5": "PM2.5", "pm10": "PM10", "ozone": "Ozone",
    "nitrogen_dioxide": "NO₂", "sulphur_dioxide": "SO₂", "carbon_monoxide": "CO",
}

# Official US EPA AQI category breakpoints (on the AQI index value itself).
_AQI_BANDS = [
    (0, 50, "Good"),
    (51, 100, "Moderate"),
    (101, 150, "Unhealthy for Sensitive Groups"),
    (151, 200, "Unhealthy"),
    (201, 300, "Very Unhealthy"),
    (301, 10_000, "Hazardous"),
]


def _error(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": msg, **extra}


def aqi_category(aqi: Any) -> str | None:
    """Pure: EPA category for a US AQI value; None if not a usable number."""
    try:
        v = float(aqi)
    except (TypeError, ValueError):
        return None
    for lo, hi, label in _AQI_BANDS:
        if lo <= v <= hi:
            return label
    return None


def parse_current(payload: dict[str, Any]) -> dict[str, Any]:
    """Pure: Open-Meteo body -> {as_of, us_aqi, aqi_category, pollutants{...}}.

    Missing values are left as None (never invented).
    """
    current = payload.get("current") or {}
    units = payload.get("current_units") or {}
    pollutants: dict[str, Any] = {}
    for field, label in _POLLUTANT_LABELS.items():
        if field in current:
            pollutants[field] = {
                "label": label,
                "value": current.get(field),
                "unit": units.get(field),
            }
    aqi = current.get("us_aqi")
    return {
        "as_of": current.get("time"),
        "us_aqi": aqi,
        "aqi_category": aqi_category(aqi),
        "pollutants": pollutants,
    }


def air_quality_at(lat: float, lon: float, *, timeout: float = 30.0) -> dict[str, Any]:
    """Current air quality at (lat, lon). Returns the shared skill contract.

    Reports US AQI + its EPA category and pollutant concentrations (model
    estimates). Bad input / network / HTTP / parse errors return ``ok=False``;
    a response with no current block returns ``ok=True`` with a ``note``.
    """
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return _error(f"latitude/longitude must be numbers, got ({lat!r}, {lon!r})")
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return _error(f"coordinates out of range: lat={lat}, lon={lon}")

    url = ENDPOINT + "?" + urllib.parse.urlencode(
        {"latitude": f"{lat}", "longitude": f"{lon}", "current": _CURRENT_FIELDS, "timezone": "UTC"}
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return _error(f"Open-Meteo returned HTTP {exc.code}", status=exc.code, source_url=url)
    except urllib.error.URLError as exc:
        return _error(f"network error contacting Open-Meteo: {exc.reason}", source_url=url)
    except ValueError as exc:
        return _error(f"could not parse Open-Meteo response: {exc}", source_url=url)
    except Exception as exc:  # defensive: never crash the orchestrator
        return _error(f"unexpected error calling Open-Meteo: {type(exc).__name__}: {exc}", source_url=url)

    parsed = parse_current(payload)
    result = {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "latitude": lat,
        "longitude": lon,
        "measurement_type": "modeled (CAMS), not station-measured",
        **parsed,
        "source_url": url,
    }
    if parsed["us_aqi"] is None and not parsed["pollutants"]:
        result["note"] = "Open-Meteo returned no current air-quality data for this location."
    return result


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import sys

    if len(sys.argv) >= 3:
        latitude, longitude = float(sys.argv[1]), float(sys.argv[2])
    else:
        latitude, longitude = 38.63, -90.20  # St. Louis
    print(json.dumps(air_quality_at(latitude, longitude), indent=2))
