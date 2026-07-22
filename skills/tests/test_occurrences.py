"""Offline tests for the GBIF occurrences skill — no network."""
from __future__ import annotations

import unittest

from skills.occurrences import (
    build_geo_distance,
    occurrences_near,
    parse_species_facets,
    summarize_match,
)


class PureHelperTests(unittest.TestCase):
    def test_geo_distance(self):
        self.assertEqual(build_geo_distance(38.2, -90.7, 5), "38.2,-90.7,5km")

    def test_parse_facets(self):
        payload = {"facets": [{"field": "SPECIES_KEY", "counts": [
            {"name": "2490384", "count": 373}, {"name": "2495347", "count": 356}]}]}
        self.assertEqual(parse_species_facets(payload), [("2490384", 373), ("2495347", 356)])

    def test_parse_facets_empty(self):
        self.assertEqual(parse_species_facets({}), [])
        self.assertEqual(parse_species_facets({"facets": []}), [])

    def test_summarize_match_ok(self):
        m = summarize_match({"usageKey": 8877412, "scientificName": "Terrapene triunguis",
                             "matchType": "EXACT", "confidence": 99, "rank": "SPECIES"})
        self.assertEqual(m["taxon_key"], 8877412)
        self.assertEqual(m["match_confidence"], 99)

    def test_summarize_match_none(self):
        self.assertIsNone(summarize_match({"matchType": "NONE"}))
        self.assertIsNone(summarize_match({}))


class InputValidationTests(unittest.TestCase):
    """Must return ok=False WITHOUT touching the network."""

    def test_non_numeric(self):
        out = occurrences_near("x", -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("must be numbers", out["error"])

    def test_out_of_range(self):
        out = occurrences_near(200, -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("out of range", out["error"])


if __name__ == "__main__":
    unittest.main()
