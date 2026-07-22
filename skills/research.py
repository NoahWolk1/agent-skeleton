"""Research skill — web / government-document search via the Brave Search API.

The orchestrator uses this skill to ground answers in real, citable web sources
(agency pages, government documents, literature) instead of the model's memory.
Every returned item carries its real ``url``, so downstream synthesis can cite
sources and never has to fabricate one.

Design notes:
  * Stdlib only (``urllib``) — no extra dependency, and the pure parsing step
    (``extract_results``) is unit-testable without a network or an API key.
  * Synchronous/blocking by design; the async orchestrator wraps the call in
    ``asyncio.to_thread(...)`` so the A2A heartbeat keeps flowing.
  * The API key is a per-user credential. It is read from the explicit argument
    first, then the ``BRAVE_API_KEY`` env var. It is sent only in the
    ``X-Subscription-Token`` header (never in the URL) and never echoed back in
    a result or error message.

Brave Web Search API (verified 2026-07):
  GET https://api.search.brave.com/res/v1/web/search
  header:  X-Subscription-Token: <key>
  params:  q, count (<=20), country, search_lang, freshness (pd|pw|pm|py)
  response: {"web": {"results": [{"title", "url", "description", "age", ...}]}}
"""
from __future__ import annotations

import gzip
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

SKILL_NAME = "research"
SOURCE_LABEL = "Brave Search API"
ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

# Brave's documented limits.
MAX_QUERY_CHARS = 400
MAX_COUNT = 20
_ALLOWED_FRESHNESS = {"pd", "pw", "pm", "py"}


def resolve_api_key(explicit: str | None = None) -> str | None:
    """The Brave key from the explicit arg, else the ``BRAVE_API_KEY`` env var.

    The orchestrator passes the per-user credential (from ``context``) as the
    explicit arg; the env var is only a local-development fallback.
    """
    key = (explicit or os.getenv("BRAVE_API_KEY") or "").strip()
    return key or None


def _error(msg: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "skill": SKILL_NAME, "source": SOURCE_LABEL, "error": msg, **extra}


def extract_results(payload: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Pure transform: Brave's JSON body -> a trimmed list of citable results.

    Kept free of I/O so it can be tested offline against a recorded payload.
    Tolerates a missing/short ``web.results`` (returns what is present).
    """
    web = payload.get("web") if isinstance(payload, dict) else None
    raw = (web or {}).get("results") if isinstance(web, dict) else None
    if not isinstance(raw, list):
        return []
    results: list[dict[str, Any]] = []
    for item in raw[: max(0, limit)]:
        if not isinstance(item, dict):
            continue
        results.append(
            {
                "title": (item.get("title") or "").strip(),
                "url": (item.get("url") or "").strip(),
                "description": (item.get("description") or "").strip(),
                "age": (item.get("age") or item.get("page_age") or "").strip(),
            }
        )
    return results


def _build_query(query: str, sites: list[str] | None) -> str:
    """Optionally scope the query to specific domains via ``site:`` operators.

    Passing ``sites=["epa.gov", "usgs.gov"]`` restricts results to government/
    agency sources — useful for the orchestrator's document-search role.
    """
    q = (query or "").strip()
    clean_sites = [s.strip() for s in (sites or []) if s and s.strip()]
    if clean_sites:
        scope = " OR ".join(f"site:{s}" for s in clean_sites)
        q = f"{q} ({scope})"
    return q[:MAX_QUERY_CHARS]


def brave_search(
    query: str,
    *,
    api_key: str | None = None,
    count: int = 5,
    country: str | None = None,
    search_lang: str | None = None,
    freshness: str | None = None,
    sites: list[str] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Search the web with Brave and return structured, citable results.

    Returns the shared skill-result contract. On any failure — missing key, bad
    input, network error, non-200 status, unparseable body — returns
    ``ok=False`` with a specific ``error`` (so the orchestrator can report the
    limitation honestly instead of guessing). An empty-but-successful search
    returns ``ok=True`` with ``results=[]`` and a ``note``.
    """
    q = (query or "").strip()
    if not q:
        return _error("empty query: nothing to search for")

    key = resolve_api_key(api_key)
    if not key:
        return _error(
            "missing Brave API credential; set BRAVE_API_KEY or supply it via the "
            "agent's credential context",
            credential_required="brave_api_key",
        )

    count = max(1, min(int(count or 5), MAX_COUNT))
    params: dict[str, str] = {"q": _build_query(q, sites), "count": str(count)}
    if country:
        params["country"] = country
    if search_lang:
        params["search_lang"] = search_lang
    if freshness:
        if freshness not in _ALLOWED_FRESHNESS:
            return _error(
                f"invalid freshness {freshness!r}; allowed: {sorted(_ALLOWED_FRESHNESS)}"
            )
        params["freshness"] = freshness

    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": key,
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
    except urllib.error.HTTPError as exc:
        # Map the common Brave statuses to actionable messages. Never include the key.
        status = exc.code
        hints = {
            401: "unauthorized — the Brave API key is missing or invalid",
            403: "forbidden — the Brave API key lacks access to this endpoint/plan",
            422: "unprocessable query — check the query text and parameters",
            429: "rate limited — too many requests to the Brave API; retry later",
        }
        return _error(hints.get(status, f"Brave API returned HTTP {status}"), status=status)
    except urllib.error.URLError as exc:
        return _error(f"network error contacting the Brave API: {exc.reason}")
    except Exception as exc:  # defensive: never crash the orchestrator
        return _error(f"unexpected error calling the Brave API: {type(exc).__name__}: {exc}")

    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return _error(f"could not parse the Brave API response: {exc}")

    results = extract_results(payload, count)
    out: dict[str, Any] = {
        "ok": True,
        "skill": SKILL_NAME,
        "source": SOURCE_LABEL,
        "query": q,
        "results": results,
        "result_count": len(results),
    }
    if not results:
        out["note"] = "the Brave API returned no results for this query"
    return out


if __name__ == "__main__":  # pragma: no cover — manual live smoke test
    import sys

    argq = " ".join(sys.argv[1:]) or "EPA Superfund sites St. Louis Missouri"
    result = brave_search(argq, count=5)
    print(json.dumps(result, indent=2))
