"""Offline tests for the research (Brave) skill — no network, no API key.

Covers the pure parsing transform and the failure paths that must NOT hit the
network (missing key, empty query, bad params), which is where the
no-fabrication guarantee lives.
"""
from __future__ import annotations

import os
import unittest

from skills.research import brave_search, extract_results, resolve_api_key


class ExtractResultsTests(unittest.TestCase):
    SAMPLE = {
        "web": {
            "results": [
                {
                    "title": "Superfund Site: Example",
                    "url": "https://www.epa.gov/superfund/example",
                    "description": "A contaminated site record.",
                    "age": "2 weeks ago",
                },
                {"title": "Second", "url": "https://usgs.gov/x", "description": "desc"},
            ]
        }
    }

    def test_extracts_and_trims(self):
        out = extract_results(self.SAMPLE, limit=5)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["url"], "https://www.epa.gov/superfund/example")
        self.assertEqual(out[0]["age"], "2 weeks ago")
        # missing age tolerated -> empty string, keys always present
        self.assertEqual(out[1]["age"], "")
        self.assertEqual(set(out[0]), {"title", "url", "description", "age"})

    def test_limit_truncates(self):
        self.assertEqual(len(extract_results(self.SAMPLE, limit=1)), 1)

    def test_missing_web_block_is_empty(self):
        self.assertEqual(extract_results({}, limit=5), [])
        self.assertEqual(extract_results({"web": {}}, limit=5), [])
        self.assertEqual(extract_results({"web": {"results": None}}, limit=5), [])


class FailurePathTests(unittest.TestCase):
    """These must return ok=False WITHOUT touching the network."""

    def setUp(self):
        self._saved = os.environ.pop("BRAVE_API_KEY", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["BRAVE_API_KEY"] = self._saved

    def test_empty_query(self):
        out = brave_search("   ", api_key="dummy")
        self.assertFalse(out["ok"])
        self.assertIn("empty query", out["error"])

    def test_missing_credential(self):
        out = brave_search("anything")
        self.assertFalse(out["ok"])
        self.assertEqual(out["credential_required"], "brave_api_key")

    def test_invalid_freshness(self):
        out = brave_search("x", api_key="dummy", freshness="lastweek")
        self.assertFalse(out["ok"])
        self.assertIn("invalid freshness", out["error"])

    def test_resolve_api_key_prefers_explicit(self):
        os.environ["BRAVE_API_KEY"] = "from-env"
        self.assertEqual(resolve_api_key("explicit"), "explicit")
        self.assertEqual(resolve_api_key(None), "from-env")
        del os.environ["BRAVE_API_KEY"]
        self.assertIsNone(resolve_api_key(None))


if __name__ == "__main__":
    unittest.main()
