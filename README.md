# GeoContext — a geospatial environmental-research agent

**Give it a location and an environmental question; it gathers evidence from 17
authoritative geospatial data sources, synthesizes a cited answer, checks itself
for fabrication, and returns both a human-readable answer and structured data.**

> Example: *"What habitat is at these camera-trap coordinates 44.4237, −110.5885,
> and what protected/listed species might be there?"* →
> Evergreen Forest (NLCD) inside **Yellowstone National Park** (PAD-US, GAP‑1);
> Canada Lynx, Grizzly bear, wolverine may occur (USFWS IPaC); 28k nearby species
> records incl. bison & elk (GBIF/iNaturalist) — each claim linked to its source.

---

## The 6 questions

**1. What research workflow does it improve?**
Location-grounded environmental fieldwork and site assessment. A researcher with a
coordinate (a camera-trap, a study plot, a neighborhood, a proposed site) normally
opens a dozen separate portals — EPA ECHO, USFWS IPaC, GBIF, USGS, FEMA, NLCD,
PAD-US — copies the coordinate into each, and hand-assembles the picture. This
agent does all of that in one request and returns a synthesized, **cited** brief
plus reusable structured data.

**2. Who at WashU would benefit?**
Environmental & ecology researchers, field biologists (camera-trap / habitat
studies), the Living Earth Collaborative, environmental-health and public-health
researchers, urban-ecology and civil/environmental engineering groups, GIS/
data-science staff, and grad students doing site or literature scoping. It is
grounded in St. Louis (bonus county zoning) but works **nationwide** (US) and, for
several sources, globally.

**3. What does it do that a general chatbot would not?**
It **retrieves live data from primary sources** instead of recalling from memory,
and it **cites every fact** (or says "no data"). A general chatbot will happily
invent species lists, facility names, or flood zones; this agent only reports what
the APIs return, attributes each finding to its source URL, runs a **validation
pass** against the gathered facts, and reports a **confidence** level.

**4. What is it designed to handle well?**
Location-anchored environmental questions such as:
- "What habitat / land cover is at these camera-trap coordinates?"
- "What ESA-listed species or critical habitat are near this site?"
- "What contamination sources / regulated facilities are near this neighborhood?"
- "Is this area in a flood zone / wetland / protected area?"
- "What species have actually been observed near here?" (with photos)
- "What's the terrain, soil, water, and air quality at this point?"
- "Is this area suitable habitat for \<species\>?" (combines several skills)

It accepts **coordinates or a place name** (which it geocodes), plans which of the
17 skills are relevant, runs them, and synthesizes.

**5. What tools, APIs, and data sources does it use?**
See the [skill catalog](#skill-catalog) below — 17 skills over EPA ECHO, USFWS
IPaC & NWI, GBIF, iNaturalist, USGS (NLCD/3DEP/NWIS), EPA/USGS Water Quality
Portal, USGS PAD-US, NIFC, FEMA NFHL, USDA SSURGO, OpenStreetMap (Nominatim &
Overpass), Open-Meteo, and Brave Search. The orchestrator uses the **OpenAI API
(GPT)** to plan, synthesize, and validate.

**6. How does it handle uncertainty, privacy, credentials, and limitations?**
- **Uncertainty:** every response carries a `confidence` level + rationale based on
  how many skills returned usable data; the answer states limitations plainly
  (modeled vs. measured, US-only coverage, "near" vs "at").
- **No fabrication:** the answer is built **only** from skill outputs; a second GPT
  pass validates it against those facts and re-writes once if it finds unsupported
  claims. Skills report "no data" honestly and never guess (e.g. a point outside
  NLCD returns *no cover*, not a made-up class).
- **Privacy/credentials:** no secrets are committed. API keys are read from the
  per-user **credential context** (`credentials.openai_api_key`,
  `credentials.brave_api_key`) or environment variables; see
  [`.env.example`](.env.example). Nothing is logged that contains a key.
- **Scope guard:** non-geospatial requests are politely **declined**; missing
  locations prompt for one.
- **Limitations:** several sources are US-only (flagged per skill); OpenStreetMap
  coverage is thin outside cities; air quality is modeled (CAMS), not measured;
  EPA ECHO is a regulatory/compliance record, not a contamination measurement;
  FEMA/zoning are regulatory designations, not live forecasts.

---

## Input / Output

**Input** (A2A text message): a natural-language request. May include coordinates
(`44.42, -110.59`) or a place name (`Forest Park, St. Louis`). Attached files are
accepted but not required.

**Output** — a dict whose **`answer`** (required) is the human-readable brief; the
rest is machine-readable structured data returned alongside it:

```jsonc
{
  "answer": "…cited, human-readable brief…",
  "confidence": "high | medium | low | n/a",
  "confidence_rationale": "3/4 skills returned usable data; validation passed.",
  "location": {"latitude": 44.42, "longitude": -110.59, "display_name": "…"},
  "skills_used": ["satellite", "species_habitat", "occurrences", "protected_areas"],
  "sources": [{"skill": "...", "source": "...", "url": "https://..."}],
  "llm_used": true,
  "structured": { "<skill>": { …raw skill output… } }
}
```

---

## Deploying it (Option B — custom handler)

| Field | Value |
|---|---|
| Handler type | Custom (Python) |
| **Entry file** | `handler.py` |
| **Class name** | `GeoOrchestratorHandler` |
| Python version | 3.11+ |
| Requirements | see [`requirements.txt`](requirements.txt) (`openai`; `a2a-sdk[http-server]`, `uvicorn` to serve) |
| System packages | **none** |
| Required credentials | `openai_api_key` (LLM pipeline); `brave_api_key` (optional, research skill) |

The importable code (`skills/`) sits at the repo root alongside `handler.py`.

**Run locally:**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .                       # or: pip install -r requirements.txt
cp .env.example .env                   # add your OPENAI_API_KEY (and BRAVE_API_KEY)
python -m agent_skeleton.serve serve-handler --file handler.py --class GeoOrchestratorHandler --port 9110
```

**Configuration (env vars):** the LLM is any **OpenAI-compatible endpoint** — set
`OPENAI_BASE_URL`, `OPENAI_MODEL`, and `OPENAI_API_KEY` (or supply the key via the
credential context). A zero-cost default is **Google Gemini Flash**
(`OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`,
`OPENAI_MODEL=gemini-2.5-flash`, key from [aistudio.google.com](https://aistudio.google.com) — ~1,500 req/day free);
the same code also runs on hosted OpenAI, a self-hosted vLLM, or Claude (see
[`.env.example`](.env.example) for each). `BRAVE_API_KEY` powers the research skill.
**Without any LLM key the agent still runs** via a keyword/heuristic planner +
templated synthesis (degraded, capped at `medium` confidence). `handler.py`
auto-loads a local `.env` for convenience (never overriding real deployment env).

---

## Skill catalog

Each skill is stdlib-only, returns a shared contract (`ok`/`source`/`…`), cites its
source URL, and reports "no data" honestly.

| Skill | Answers | Source | Scope | Key |
|---|---|---|---|---|
| `satellite` | land cover / habitat type | NLCD (USGS/MRLC) | US (CONUS) | — |
| `construction` | land use + local zoning/flood-plain | OpenStreetMap (+ STL County) | 🌍 / STL bonus | — |
| `species_habitat` | ESA species, critical habitat, migratory birds | USFWS IPaC | US | — |
| `occurrences` | species recorded nearby / is species X present | GBIF | 🌍 | — |
| `inaturalist` | recent species observations **with photos** | iNaturalist | 🌍 | — |
| `protected_areas` | parks/refuges/easements + GAP status | USGS PAD-US | US | — |
| `wetlands` | mapped wetland type | USFWS NWI | US | — |
| `wildfire` | recorded fire history at the point | NIFC | US | — |
| `flood_zone` | FEMA flood zone | FEMA NFHL | US | — |
| `contamination` | regulated facilities + compliance | EPA ECHO | US | — |
| `air_quality` | current AQI + pollutants (modeled) | Open-Meteo (CAMS) | 🌍 | — |
| `water` | streamflow gages + water-quality stations | USGS NWIS + WQP | US | — |
| `soil` | soil type/drainage/taxonomy/farmland | USDA SSURGO | US | — |
| `elevation` | elevation + estimated slope | USGS 3DEP | US | — |
| `proximity` | nearby OSM features (industrial, water, parks…) | OSM Overpass | 🌍 | — |
| `geocode` | place name/address → coordinates | OSM Nominatim | 🌍 | — |
| `research` | web / government-document search | Brave Search | 🌍 | ✔ Brave |

---

## How it works

```
request → PLAN (GPT: geospatial? location? which skills?)
        → RESOLVE location (geocode a place name if needed)
        → RUN chosen skills concurrently (blocking calls in threads)
        → SYNTHESIZE (GPT: cited answer from the facts only)
        → VALIDATE (GPT: unsupported claims? → one re-synthesis)
        → RETURN {answer, confidence, sources, structured}
```

`skills/` are the data sources; `skills/registry.py` is the single dispatch point;
`handler.py` is the orchestrator (the A2A entry point). The skills know nothing
about A2A and are unit-testable offline.

## Testing

```bash
python -m unittest discover -s skills/tests -p 'test_*.py'   # 104 offline tests, no network
python -m agent_skeleton.serve serve-handler --file handler.py --class GeoOrchestratorHandler
```

## Starter-repo feedback

Concrete, reproducible issues we hit while building on the starter repo (details
and fixes are documented in the relevant skill modules; being filed as GitHub
issues/PRs):
- `MAX_TOOL_STEPS = 4` in `config.py` is too low for any multi-source agent and
  silently truncates the tool loop.
- The custom-handler credential doc (`INTEGRATION_GUIDE.md` §7) and `base.py`
  docstring differ slightly in the exact `context["credentials"]` shape.
- Two data-source gotchas worth documenting for future cohorts (found the hard
  way): ArcGIS servers that require a browser `User-Agent` vs. Overpass that
  *rejects* one, and an ArcGIS service that mislabels its spatial reference.
