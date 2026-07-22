"""Offline tests for the wildfire (NIFC fire history) skill — no network."""
from __future__ import annotations

import unittest

from skills.wildfire import fire_history_at, parse_fire_features


class ParseTests(unittest.TestCase):
    def test_dedup_and_sort(self):
        feats = [
            {"attributes": {"INCIDENT": "CAMP", "FIRE_YEAR_INT": 2018, "GIS_ACRES": 153335.6}},
            {"attributes": {"INCIDENT": "Camp", "FIRE_YEAR_INT": 2018, "GIS_ACRES": 153335}},  # dup
            {"attributes": {"INCIDENT": "Old Fire", "FIRE_YEAR_INT": 1999, "GIS_ACRES": 10}},
        ]
        fires = parse_fire_features(feats)
        self.assertEqual(len(fires), 2)          # CAMP deduped
        self.assertEqual(fires[0]["year"], 2018)  # newest first
        self.assertEqual(fires[1]["year"], 1999)

    def test_year_fallback_and_none(self):
        feats = [
            {"attributes": {"INCIDENT": "A", "FIRE_YEAR": "2005"}},   # string year
            {"attributes": {"INCIDENT": "B"}},                        # no year
        ]
        fires = parse_fire_features(feats)
        years = [f["year"] for f in fires]
        self.assertIn(2005, years)
        self.assertIn(None, years)
        self.assertIsNone(fires[-1]["year"])  # None sorts last

    def test_empty(self):
        self.assertEqual(parse_fire_features([]), [])


class InputValidationTests(unittest.TestCase):
    """Must return ok=False WITHOUT touching the network."""

    def test_non_numeric(self):
        out = fire_history_at("x", -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("must be numbers", out["error"])

    def test_out_of_range(self):
        out = fire_history_at(0, 200)
        self.assertFalse(out["ok"])
        self.assertIn("out of range", out["error"])


if __name__ == "__main__":
    unittest.main()
