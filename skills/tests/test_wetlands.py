"""Offline tests for the wetlands (NWI) skill — no network."""
from __future__ import annotations

import unittest

from skills.wetlands import parse_wetland_features, wetlands_at


class ParseTests(unittest.TestCase):
    def test_prefixed_fields(self):
        feats = [{"attributes": {
            "Wetlands.ATTRIBUTE": "PEM5Fh",
            "Wetlands.WETLAND_TYPE": "Freshwater Emergent Wetland",
            "Wetlands.ACRES": 76934.056,
        }}]
        w = parse_wetland_features(feats)
        self.assertEqual(w[0]["code"], "PEM5Fh")
        self.assertEqual(w[0]["type"], "Freshwater Emergent Wetland")
        self.assertEqual(w[0]["acres"], 76934.06)

    def test_unprefixed_fields(self):
        feats = [{"attributes": {"ATTRIBUTE": "R2UBH", "WETLAND_TYPE": "Riverine", "ACRES": 5}}]
        w = parse_wetland_features(feats)
        self.assertEqual(w[0]["code"], "R2UBH")
        self.assertEqual(w[0]["type"], "Riverine")

    def test_empty(self):
        self.assertEqual(parse_wetland_features([]), [])


class InputValidationTests(unittest.TestCase):
    """Must return ok=False WITHOUT touching the network."""

    def test_non_numeric(self):
        out = wetlands_at("x", -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("must be numbers", out["error"])

    def test_out_of_range(self):
        out = wetlands_at(0, -400)
        self.assertFalse(out["ok"])
        self.assertIn("out of range", out["error"])


if __name__ == "__main__":
    unittest.main()
