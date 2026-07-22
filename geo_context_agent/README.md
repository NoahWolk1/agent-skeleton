# GeoContext Agent

A skill agent in a multi-agent A2A research network for WashU environmental/
geospatial research (an orchestrator that also covers construction/zoning permits,
satellite imagery, and literature search). Given a location, it answers four kinds of
question: what EPA-regulated contamination sources are nearby, what's nearby by land
use/zoning (proximity analysis), the ground elevation/slope, and the FEMA-mapped
flood zone — so a researcher can quickly get site context without manually digging
through EPA ECHO's web UI, a map tool, or FEMA's flood map viewer.

Built on [`agent_skeleton`](../README.md)'s **Path B** (custom handler): `handler.py`
defines `GeoContextHandler`, which subclasses `AgentHandler` and implements
`handle_structured()`. Internally it still runs the same system prompt + five tools
(`tool_schemas.py`/`prompt.py` unchanged; the tool bodies live one-per-file under
`tools/` — see `tools/__init__.py` for the map) through the frozen
`llm_loop.run_tool_loop` engine — only the entry point differs from a stock Path-A
agent. Entry point: **file `handler.py`, class `GeoContextHandler`**, served via
`python -m agent_skeleton.serve serve-handler --file handler.py --class
GeoContextHandler --card agent.card.json`. The agent card advertises four skills —
`contamination/find-sources`, `zone/analyze-proximity`, `terrain/elevation-slope`,
and `flood/zone-lookup` — from this one service.

## 1. What research workflow does it improve?

Environmental, ecological, and geography researchers routinely need quick context
about a field site, camera-trap location, or sample site: what regulated pollution
sources sit nearby, what land use/zone/natural features surround it (water,
woodland, industrial, residential), how steep and how high the terrain is, and
whether it sits in a mapped flood zone. Today that means separately querying EPA
ECHO's facility-search tools, inspecting map layers, checking a USGS elevation
service, and pulling up FEMA's flood map viewer. This agent answers all four in one
natural-language request.

## 2. Who at WashU would benefit?

Environmental science / earth & planetary science researchers, ecology and
conservation biology labs (e.g. camera-trap / habitat studies that need to rule out
contamination as a confound or check proximity to water/green space), and
geography/urban-studies researchers needing a quick land-use read for a point.

## 3. What does it do that a general chatbot would not?

It queries **live, structured data** for the exact coordinates given — EPA ECHO's
REST API for regulatory/compliance data, OpenStreetMap (Nominatim + Overpass) for
geocoding and nearby features, USGS's elevation service, and FEMA's flood hazard
map — rather than recalling static, possibly outdated or fabricated facts from
training data. It returns real facility names, registry IDs, compliance/violation
flags, real mapped features with distances, an actual elevation reading, and a real
FEMA flood zone code, none of which a general chatbot can look up live.

## 4. What is it designed to handle well?

- "What are potential sources of contamination near `<address>`?"
- "Are there any EPA violators within `<N>` miles of `<lat, lon>`?"
- "What's near `<place>` — is it near any industrial zones?"
- "Is this area near wetland/water/woodland: `<lat, lon>`?" (a proximity proxy for
  habitat-suitability questions)
- "What's the elevation and slope at `<lat, lon>`? Ridge or valley?"
- "What FEMA flood zone is `<address>` in? Is it a Special Flood Hazard Area?"
- Requests with only a place name (it geocodes first) or with raw coordinates.

It is **not** designed to: measure actual soil/water/air contamination, give a
definitive legal zoning classification, assess species-specific habitat suitability
on its own, give a precise engineering-grade slope figure, forecast actual flood
risk (FEMA zones are a mapped designation, not a live forecast), answer questions
unrelated to a location's contamination/proximity/terrain/flood-zone context, or
cover non-US locations for the EPA ECHO, USGS, or FEMA skills (all US-only;
OpenStreetMap proximity is global).

## 5. Tools, files, APIs, databases used

| Component | Role |
|---|---|
| [EPA ECHO REST API](https://echo.epa.gov/tools/web-services) (`echodata.epa.gov/echo/echo_rest_services`) | Facility search (`get_facilities`) + facility detail paging (`get_qid`) — free, no API key |
| [OpenStreetMap Nominatim](https://nominatim.org/) | Geocoding (place name/address -> lat/lon) — free, no API key |
| [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API) (`overpass-api.de`) | Nearby OSM feature queries by tag (landuse/natural/amenity/leisure/man_made) within a radius — free, no API key |
| [USGS Elevation Point Query Service](https://epqs.nationalmap.gov/v1/docs) (The National Map / 3DEP) | Point elevation, sampled 5x (center + N/S/E/W) to estimate local slope — free, no API key |
| [FEMA National Flood Hazard Layer](https://www.fema.gov/flood-maps/national-flood-hazard-layer) (ArcGIS REST, `hazards.fema.gov`) | Point-in-polygon flood zone lookup (layer 28, "Flood Hazard Zones") — free, no API key |
| OpenAI-compatible Chat Completions endpoint | The LLM tool-calling loop (`OPENAI_API_KEY`, optionally `OPENAI_BASE_URL` for a self-hosted model) |

All external calls use Python's stdlib `urllib` — no extra pip dependency beyond
the template's own (`a2a-sdk`, `openai`, `uvicorn`).

**Input:** a natural-language request (place name, address, or lat/lon, optionally a
radius).
**Output:** a structured dict — `answer` (human-readable synthesis), `tools_used`,
`key_facilities` (notable EPA violator names), `nearby_features` (short feature+
distance mentions), `site_conditions` (short elevation/slope/flood-zone mentions),
`confidence` (`high`/`medium`/`low`), and `caveats`, plus the raw tool call log the
planner can inspect.

**A note on EJScreen:** EPA's Environmental Justice screening tool (pollution +
demographic burden near a location) was considered for this agent, but EPA removed
EJScreen and its API entirely in February 2025 — `ejscreen.epa.gov` no longer
resolves. The community replacements found (`screening-tools.com/epa-ejscreen`,
a Public Environmental Data Partners mirror) are map-viewer-only with no documented
query API, so it wasn't added here. Revisit if a stable, queryable replacement shows
up.

## 6. Uncertainty, privacy, credentials, limitations

- **No secrets required for the data sources** — EPA ECHO, Nominatim, Overpass,
  USGS EPQS, and FEMA NFHL are all public, keyless APIs. Only the LLM call needs
  `OPENAI_API_KEY` (see `.env.example`); no key is ever hard-coded or committed.
- **Scope guard:** the system prompt instructs the model to decline requests outside
  "contamination sources, nearby zoning/features, terrain, or flood zone" rather
  than improvising an answer.
- **Ambiguous/missing input:** if the location can't be geocoded, or is too vague, the
  agent asks for a more specific location instead of guessing coordinates.
- **No fabrication:**
  - EPA ECHO tracks *regulated* facilities and their compliance history, not
    real-time measured contamination — the agent states this distinction explicitly
    and never claims a location "is contaminated." A clean record only means no
    *regulated* violator was found; it does not rule out unregulated/unreported
    sources.
  - OpenStreetMap is community-contributed and coverage is uneven — the agent says
    explicitly when a sparse result means "nothing mapped" rather than "nothing
    there," and frames habitat-suitability questions only in terms of the physical
    proximity signals available, never as a substitute for an ecological survey.
  - The slope from `find_elevation_terrain` is estimated from 4 sample points ~30m
    out in each direction, not a precise engineering figure — the agent is
    instructed to describe it qualitatively (roughly flat / moderately sloped /
    steep) rather than treat the number as exact.
  - FEMA's flood zone is a mapped regulatory designation, not a live flood
    forecast. A point with no NFHL coverage means the area is unstudied, not
    flood-safe, and even Zone X ("minimal hazard") is not a guarantee against
    flooding — the agent is instructed to say this whenever flood zone comes up.
- **Confidence reporting:** every answer includes a `confidence` field, downgraded to
  `low` whenever a tool returns zero/very few results, the geocode is ambiguous, or
  the question needs domain expertise beyond what the data can support.
- Nominatim's usage policy (rate limit + identifying `User-Agent`) is respected in
  `config.py`/`tools/helpers.py`. Individually-mapped street trees/planters
  (`natural=tree`, `leisure=garden`) are deliberately excluded from proximity
  results — they flood dense urban queries and drown out the signal.

## Running it locally

`pip install -e .` is not optional here — `handler.py` and the copied
`handler_executor.py` import `agent_skeleton.*` absolutely (not relatively), so they
only resolve once this directory is actually installed under that name. Running
`python -m geo_context_agent.serve ...` from inside this folder will fail with
`ModuleNotFoundError` — always invoke as `agent_skeleton` after installing:

```bash
cd geo_context_agent
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e .
cp .env.example .env   # then fill in OPENAI_API_KEY
export $(cat .env | xargs)   # or use your process manager's env loading

python -m agent_skeleton.serve check         # schema/function alignment, no network, no LLM
python -m pytest tests -q                    # offline unit tests
python -m agent_skeleton.serve serve-handler --file handler.py --class GeoContextHandler --card agent.card.json
```

## Dependencies

- **Python packages:** see `pyproject.toml` (`a2a-sdk[http-server]==0.3.2`,
  `openai>=1.40`, `uvicorn>=0.30`). No extra packages for EPA ECHO / Nominatim /
  Overpass (stdlib `urllib`).
- **System binaries:** none.
- **Hardware:** none beyond what running the LLM call requires (no local GPU
  needed — this agent does not run a local model).
- **Secrets:** `OPENAI_API_KEY` (env var only, see `.env.example`); no other
  credentials needed.
