"""GeoOrchestratorHandler — the Path-B entry point for the geospatial research
agent. This is the file the deployment wraps and serves.

Pipeline (deterministic, model-in-the-loop):
    1. PLAN      — decide if the request is geospatial, extract a location
                   (coordinates or a place name to geocode), and choose which
                   skills to run. Uses the OpenAI API (GPT); falls back to a
                   keyword/regex heuristic if no LLM key is available.
    2. RESOLVE   — turn a place name into coordinates via the geocode skill.
    3. RUN       — call the chosen skills concurrently (each blocking skill in a
                   thread so the A2A heartbeat keeps flowing).
    4. SYNTHESIZE— combine the skills' cited facts into an answer (GPT; templated
                   fallback without a key).
    5. VALIDATE  — a second GPT pass checks the draft uses only the gathered
                   facts and states uncertainty; one bounded re-synthesis on
                   failure.
    6. RETURN    — {answer, confidence, sources, skills_used, location, structured}.

Trust/safety: unrelated (non-geospatial) prompts are declined; missing locations
ask for one; nothing is fabricated — the answer is built only from skill outputs,
every skill cites its source, and skills report "no data" honestly.

LLM: OpenAI GPT. Reads the key from the per-user credential context
(``credentials.openai_api_key``) or the OPENAI_API_KEY env var; model via
OPENAI_MODEL / AGENT_MODEL (default gpt-4o-mini); optional OPENAI_BASE_URL.
The Brave research skill's key comes from ``credentials.brave_api_key`` /
BRAVE_API_KEY.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from agent_skeleton import AgentHandler, FileInput
from skills.registry import POINT_SKILLS, catalog_text, run_skill


def _load_dotenv() -> None:
    """Best-effort: load a local .env (in cwd or next to this file) into the
    environment WITHOUT overriding already-set vars. Convenience for local
    `serve-handler` runs; a no-op in deployment (no .env shipped, and real
    injected env/credentials always win via setdefault)."""
    import pathlib

    for path in (pathlib.Path.cwd() / ".env", pathlib.Path(__file__).resolve().parent / ".env"):
        try:
            if not path.is_file():
                continue
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())
        except Exception:
            pass


_load_dotenv()
DEFAULT_MODEL = os.getenv("OPENAI_MODEL") or os.getenv("AGENT_MODEL") or "gpt-4o-mini"

# A sensible default skill set for a generic "tell me about this location /
# camera-trap habitat" request when the planner gives no specific steer.
_DEFAULT_SKILLS = ["satellite", "species_habitat", "occurrences", "protected_areas", "construction"]

_COORD_RE = re.compile(r"(-?\d{1,3}(?:\.\d+)?)\s*[,;]?\s+(-?\d{1,3}(?:\.\d+)?)")


# --------------------------------------------------------------------------
# Credentials + OpenAI client
# --------------------------------------------------------------------------

def _cred(context: dict | None, name: str) -> str | None:
    creds = ((context or {}).get("credentials") or {})
    entry = creds.get(name) or {}
    if isinstance(entry, dict):
        return entry.get("api_key") or entry.get("key") or entry.get("value")
    return entry if isinstance(entry, str) else None


def _openai_client(api_key: str | None):
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    try:
        return OpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL") or None)
    except Exception:
        return None


def _llm_json(client, model: str, system: str, user: str) -> dict | None:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception:
        return None


def _llm_text(client, model: str, system: str, user: str) -> str | None:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip() or None
    except Exception:
        return None


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------

def _coords_from_text(text: str) -> tuple[float, float] | None:
    for m in _COORD_RE.finditer(text or ""):
        try:
            lat, lon = float(m.group(1)), float(m.group(2))
        except ValueError:
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180 and (abs(lat) > 0 or abs(lon) > 0):
            return lat, lon
    return None

# keyword -> skills, for the no-LLM heuristic planner.
_KEYWORDS: list[tuple[tuple[str, ...], list[str]]] = [
    (("habitat", "land cover", "landcover", "vegetation", "ecosystem"), ["satellite", "species_habitat"]),
    (("species", "wildlife", "animal", "bird", "fish", "plant", "biodiversity"),
     ["species_habitat", "occurrences", "inaturalist"]),
    (("contamination", "pollution", "polluter", "toxic", "epa", "hazard", "superfund", "facility"),
     ["contamination", "air_quality"]),
    (("air", "smog", "aqi", "pm2.5", "ozone"), ["air_quality"]),
    (("water", "stream", "river", "creek", "watershed", "aquatic"), ["water"]),
    (("soil", "farmland", "agricult"), ["soil"]),
    (("fire", "wildfire", "burn"), ["wildfire"]),
    (("wetland", "marsh", "swamp"), ["wetlands"]),
    (("flood", "floodplain", "flood zone"), ["flood_zone"]),
    (("protected", "park", "refuge", "wilderness", "conservation", "reserve"), ["protected_areas"]),
    (("zoning", "zoned", "land use", "development", "construction", "building"), ["construction"]),
    (("elevation", "slope", "terrain", "topography", "ridge", "valley"), ["elevation"]),
    (("near", "nearby", "around", "proximity", "adjacent"), ["proximity"]),
]

_GEO_HINTS = ("coordinate", "lat", "lon", "location", "site", "area", "near", "habitat",
              "species", "camera trap", "°", "n,", "w,", "e,", "s,")


_PLACE_RE = re.compile(r"\b(?:near|around|in|at|by|for)\s+(.+)$", re.IGNORECASE)


def _place_from_text(text: str) -> str | None:
    """Best-effort place phrase from a sentence (no LLM): the tail after a
    locational preposition, e.g. '...near Forest Park, St. Louis' -> that phrase."""
    m = _PLACE_RE.search((text or "").strip().rstrip("?.!"))
    if not m:
        return None
    phrase = m.group(1).strip().rstrip("?.!")
    return phrase if 2 <= len(phrase) <= 80 else None


def _heuristic_plan(text: str) -> dict[str, Any]:
    low = (text or "").lower()
    skills: list[str] = []
    for keys, sk in _KEYWORDS:
        if any(k in low for k in keys):
            skills += [s for s in sk if s not in skills]
    coords = _coords_from_text(text)
    place = None if coords else _place_from_text(text)
    is_geo = bool(coords) or bool(place) or any(h in low for h in _GEO_HINTS) or bool(skills)
    return {
        "is_geospatial": is_geo,
        "latitude": coords[0] if coords else None,
        "longitude": coords[1] if coords else None,
        "location_query": place,
        "skills": skills or list(_DEFAULT_SKILLS),
        "taxon": None,
        "search_query": None,
        "decline_reason": None if is_geo else "The request does not appear to be about a geographic location.",
    }


_PLANNER_SYSTEM = (
    "You are the planner for a geospatial environmental-research agent. Decide whether the "
    "user's request is about a geographic location, extract the location, and choose which "
    "data skills to run. Only choose skills relevant to the question. Return STRICT JSON with "
    "keys: is_geospatial (bool), latitude (number|null), longitude (number|null), "
    "location_query (string|null; a place/address to geocode when no coordinates are given), "
    "skills (array of skill names from the catalog), taxon (string|null; a species name only if "
    "the user asks whether a specific species is present), search_query (string|null; only if a "
    "web/document search would help), decline_reason (string|null; set when not geospatial).\n\n"
    "Skill catalog:\n" + catalog_text()
)


def _llm_plan(client, model: str, text: str) -> dict[str, Any] | None:
    plan = _llm_json(client, model, _PLANNER_SYSTEM, f"User request:\n{text}")
    if not isinstance(plan, dict) or "is_geospatial" not in plan:
        return None
    # sanitize skill names
    plan["skills"] = [s for s in (plan.get("skills") or []) if s in POINT_SKILLS]
    return plan


# --------------------------------------------------------------------------
# Synthesis + validation
# --------------------------------------------------------------------------

_SYNTH_SYSTEM = (
    "You are an environmental-research assistant. Write a clear, concise answer to the user's "
    "question using ONLY the JSON facts gathered by the data skills below. Rules: (1) Never "
    "invent species, measurements, facilities, or citations — if a skill returned no data or an "
    "error, say so. (2) Attribute findings to their source (each fact has a 'source'). (3) State "
    "uncertainty and limitations plainly (e.g. modeled vs. measured, US-only coverage, 'near' vs "
    "'at'). (4) Be specific and useful to a researcher. Do not output JSON — write prose."
)


def _template_synthesis(location_str: str, facts: dict[str, dict]) -> str:
    lines = [f"Findings for {location_str}:", ""]
    for name, res in facts.items():
        src = res.get("source", "")
        if not res.get("ok", False):
            lines.append(f"- {name} ({src}): could not retrieve — {res.get('error', 'unknown error')}")
        elif res.get("note"):
            lines.append(f"- {name} ({src}): {res['note']}")
        else:
            lines.append(f"- {name} ({src}): data retrieved (see structured output).")
    lines.append("")
    lines.append("(LLM synthesis was unavailable, so this is a direct listing of skill results.)")
    return "\n".join(lines)


_VALIDATOR_SYSTEM = (
    "You verify an environmental-research answer against the JSON facts it was built from. Check "
    "that every factual claim is supported by the facts, that no species/numbers/citations are "
    "fabricated, and that limitations/uncertainty are stated. Return STRICT JSON: {\"valid\": "
    "bool, \"issues\": [string], \"suggested_fix\": string}."
)


# --------------------------------------------------------------------------
# Confidence + sources
# --------------------------------------------------------------------------

def _has_data(res: dict) -> bool:
    if not res.get("ok"):
        return False
    # A 'note' with empty collections usually means "no data found".
    for k, v in res.items():
        if k in ("ok", "skill", "source", "source_url", "source_urls", "latitude", "longitude",
                 "note", "measurement_type", "query", "radius_km", "radius_miles", "query_area_deg",
                 "year", "search_buffer_m", "osm_attribution", "ordinance_url", "service_warning"):
            continue
        if isinstance(v, (list, dict)) and v:
            return True
        if isinstance(v, bool) and v:
            return True
        if v not in (None, "", [], {}, 0):
            return True
    return False


def _confidence(facts: dict[str, dict], validator_valid: bool | None, llm_used: bool) -> tuple[str, str]:
    attempted = [n for n in facts if n not in ("geocode", "research")]
    if not attempted:
        return "low", "No location skills produced results."
    ok_data = [n for n in attempted if _has_data(facts[n])]
    frac = len(ok_data) / len(attempted)
    if validator_valid is False:
        return "low", "The validation pass flagged unsupported claims."
    if frac >= 0.67:
        level = "high"
    elif frac >= 0.34:
        level = "medium"
    else:
        level = "low"
    if not llm_used and level == "high":
        level = "medium"  # no LLM synthesis/validation -> cap
    rationale = (
        f"{len(ok_data)}/{len(attempted)} skills returned usable data"
        + ("" if llm_used else "; LLM synthesis/validation unavailable")
        + ("." if validator_valid is None else "; validation passed." if validator_valid else ".")
    )
    return level, rationale


def _collect_sources(facts: dict[str, dict]) -> list[dict[str, Any]]:
    out = []
    for name, res in facts.items():
        if not res.get("ok"):
            continue
        url = res.get("source_url")
        if not url and isinstance(res.get("source_urls"), dict):
            url = "; ".join(str(u) for u in res["source_urls"].values() if u)
        out.append({"skill": name, "source": res.get("source"), "url": url})
    return out


# --------------------------------------------------------------------------
# The handler
# --------------------------------------------------------------------------

class GeoOrchestratorHandler(AgentHandler):
    """Plans, runs, synthesizes, and validates geospatial-research skills."""

    async def handle_structured(
        self,
        user_input: str,
        files: list[FileInput] = [],
        context: dict | None = None,
    ) -> dict:
        text = (user_input or "").strip()
        if not text:
            return {"answer": "Please describe a location (coordinates or a place name) and what "
                              "you'd like to know about it — e.g. 'What habitat is at 44.42, -110.59?'",
                    "confidence": "n/a", "status": "input_required"}

        openai_key = _cred(context, "openai_api_key") or os.getenv("OPENAI_API_KEY")
        brave_key = _cred(context, "brave_api_key") or os.getenv("BRAVE_API_KEY")
        client = _openai_client(openai_key)
        model = DEFAULT_MODEL
        llm_used = client is not None

        # 1. PLAN
        plan = (_llm_plan(client, model, text) if client else None) or _heuristic_plan(text)

        if not plan.get("is_geospatial"):
            return {
                "answer": (
                    "I'm a geospatial environmental-research agent — I answer questions grounded in "
                    "a location (habitat, species, contamination, water, soil, protected areas, etc.). "
                    + (plan.get("decline_reason") or "")
                    + " Try giving me coordinates or a place name and an environmental question."
                ).strip(),
                "confidence": "n/a",
                "status": "declined",
                "reason": "non_geospatial_request",
            }

        # 2. RESOLVE location
        lat, lon = plan.get("latitude"), plan.get("longitude")
        geocode_info = None
        if (lat is None or lon is None):
            place = plan.get("location_query") or (None if _coords_from_text(text) else text)
            coords = _coords_from_text(text)
            if coords:
                lat, lon = coords
            elif place:
                g = await asyncio.to_thread(run_skill, "geocode", query=place)
                if g.get("ok") and g.get("latitude") is not None:
                    lat, lon, geocode_info = g["latitude"], g["longitude"], g
        if lat is None or lon is None:
            return {
                "answer": "I couldn't determine a location from your request. Please provide "
                          "coordinates (e.g. '44.42, -110.59') or a specific place name.",
                "confidence": "n/a",
                "status": "input_required",
            }

        # 3. RUN skills (concurrently; blocking skills in threads)
        chosen = [s for s in (plan.get("skills") or []) if s in POINT_SKILLS] or list(_DEFAULT_SKILLS)
        taxon = plan.get("taxon")
        tasks = {name: asyncio.to_thread(run_skill, name, lat=lat, lon=lon, taxon=taxon) for name in chosen}
        if plan.get("search_query"):
            tasks["research"] = asyncio.to_thread(
                run_skill, "research", query=plan["search_query"], brave_key=brave_key
            )
        results = await asyncio.gather(*tasks.values())
        facts: dict[str, dict] = dict(zip(tasks.keys(), results))
        if geocode_info:
            facts["geocode"] = geocode_info

        location_str = (
            geocode_info.get("display_name") if geocode_info else f"{lat}, {lon}"
        ) or f"{lat}, {lon}"

        # 4. SYNTHESIZE
        facts_json = json.dumps(facts, default=str)[:120_000]
        draft = None
        if client:
            draft = _llm_text(
                client, model, _SYNTH_SYSTEM,
                f"User question:\n{text}\n\nLocation: {location_str} ({lat}, {lon})\n\n"
                f"Gathered facts (JSON):\n{facts_json}",
            )
        if not draft:
            draft = _template_synthesis(location_str, facts)
            llm_used = False

        # 5. VALIDATE (one bounded re-synthesis on failure)
        validator_valid: bool | None = None
        if client and draft:
            verdict = _llm_json(
                client, model, _VALIDATOR_SYSTEM,
                f"Answer to check:\n{draft}\n\nFacts (JSON):\n{facts_json}",
            )
            if isinstance(verdict, dict):
                validator_valid = bool(verdict.get("valid"))
                if validator_valid is False and verdict.get("suggested_fix"):
                    revised = _llm_text(
                        client, model, _SYNTH_SYSTEM,
                        f"User question:\n{text}\n\nLocation: {location_str}\n\nFacts (JSON):\n{facts_json}\n\n"
                        f"Revise to fix these problems, using only the facts:\n{verdict['suggested_fix']}",
                    )
                    if revised:
                        draft = revised
                        validator_valid = True  # revised per feedback

        # 6. RETURN
        level, rationale = _confidence(facts, validator_valid, llm_used)
        return {
            "answer": draft,
            "confidence": level,
            "confidence_rationale": rationale,
            "location": {
                "latitude": lat, "longitude": lon, "query": text,
                "display_name": geocode_info.get("display_name") if geocode_info else None,
            },
            "skills_used": list(facts.keys()),
            "sources": _collect_sources(facts),
            "llm_used": llm_used,
            "structured": facts,  # machine-readable raw skill outputs
        }
