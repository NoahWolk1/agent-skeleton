"""Skill modules for the geospatial research orchestrator.

Each skill is a plain, synchronous Python function that takes structured inputs
and returns a JSON-able dict following the shared skill-result contract:

    {
      "ok": bool,               # did the skill run without error?
      "skill": str,             # the skill's stable name
      "source": str,            # human-readable data-source label (for citations)
      "results": list | dict,   # the payload the orchestrator/synthesis reads
      "error": str,             # present only when ok is False
      ...                       # skill-specific extras
    }

Skills never fabricate: on a missing credential, a network failure, or an empty
result set they say so explicitly (ok=False with an error, or ok=True with an
empty result set and a note) rather than inventing data. The async orchestrator
calls each blocking skill via ``asyncio.to_thread(...)``.
"""
