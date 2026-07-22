"""Shared configuration & constants.

SUPPORT FILE — you normally only edit the DEFAULT_* values below.
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Identity -------------------------------------------------------------
AGENT_NAME = "GeoContext Agent"

# --- Networking -----------------------------------------------------------
DEFAULT_HOST = "0.0.0.0"          # bind address (listen on all interfaces)
DEFAULT_PORT = 9111               # pick a free port

# --- LLM ------------------------------------------------------------------
DEFAULT_MODEL = "gpt-4o-mini"     # hosted model name, or your vLLM --served-model-name
MAX_TOOL_STEPS = 10                # geocode + several data lookups (elevation alone makes 5 EPQS calls internally) - plus room to spare

# --- Paths ----------------------------------------------------------------
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CARD_PATH = PACKAGE_DIR / "agent.card.json"

# --- External data sources --------------------------------------------------
# EPA ECHO (Enforcement and Compliance History Online). get_facilities takes
# p_lat/p_long/p_radius (miles) and hands back a QueryID plus row counts per
# program; get_qid then pages through the actual facility rows for that
# QueryID. Note: qcolumns 1/6/17/18 = FacName/RegistryID/FacLat/FacLong.
ECHO_BASE_URL = "https://echodata.epa.gov/echo/echo_rest_services"

# OpenStreetMap Nominatim - geocoding only (place/address -> lat/lon). No key,
# but their usage policy wants a real User-Agent and asks you to stay under
# ~1 request/sec, which one-shot lookups here easily satisfy.
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org"

# Overpass API - queries OSM features (landuse/natural/amenity/leisure/
# man_made) within a radius of a point. Public instance, no key needed.
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# USGS Elevation Point Query Service (part of The National Map / 3DEP). Point
# elevation only, no key. Takes x=lon, y=lat, units, wkid; the older ned.usgs.gov
# host was retired in 2023 - this is the current one.
EPQS_URL = "https://epqs.nationalmap.gov/v1/json"

# FEMA National Flood Hazard Layer, ArcGIS REST. Layer 28 ("Flood Hazard
# Zones") is the polygon layer with FLD_ZONE/SFHA_TF/STATIC_BFE per area - the
# one to hit for a point-in-polygon flood zone lookup. No key.
FEMA_NFHL_ZONES_URL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"

HTTP_USER_AGENT = "WashU-DTRC-GeoContextAgent/0.1"
HTTP_TIMEOUT_S = 25  # Overpass can be slow to respond; give it more room than a plain geocode


# --- Env readers (so deployment can override without code edits) ----------
def env_model() -> str:
    return os.getenv("AGENT_MODEL", DEFAULT_MODEL)


def env_host() -> str:
    return os.getenv("AGENT_A2A_HOST", DEFAULT_HOST)


def env_port() -> int:
    return int(os.getenv("AGENT_A2A_PORT", str(DEFAULT_PORT)))


def env_advertise_url() -> str | None:
    return os.getenv("AGENT_A2A_URL")
