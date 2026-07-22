"""Offline tests for the satellite (NLCD land-cover) skill — no network.

Covers the pure legend/parse logic and the input-validation failures that must
NOT hit the network (where the no-fabrication guarantee lives).
"""
from __future__ import annotations

import unittest

from skills.satellite import (
    classify_land_cover,
    describe_code,
    parse_feature_response,
)


class DescribeCodeTests(unittest.TestCase):
    def test_known_codes(self):
        self.assertEqual(describe_code(41)["class"], "Deciduous Forest")
        self.assertEqual(describe_code(41)["habitat_category"], "Forest")
        self.assertEqual(describe_code(90)["habitat_category"], "Wetlands")
        self.assertEqual(describe_code(24)["habitat_category"], "Developed")

    def test_unknown_code_is_not_invented(self):
        out = describe_code(999)
        self.assertIn("Unclassified", out["class"])
        self.assertIsNone(out["habitat_category"])

    def test_none_code(self):
        self.assertEqual(describe_code(None)["class"], "No data")


class ParseFeatureResponseTests(unittest.TestCase):
    def test_palette_index(self):
        payload = {"features": [{"properties": {"PALETTE_INDEX": 41}}]}
        self.assertEqual(parse_feature_response(payload), 41)

    def test_gray_index_fallback(self):
        payload = {"features": [{"properties": {"GRAY_INDEX": 82}}]}
        self.assertEqual(parse_feature_response(payload), 82)

    def test_empty_features_is_none(self):
        self.assertIsNone(parse_feature_response({"features": []}))
        self.assertIsNone(parse_feature_response({}))
        self.assertIsNone(parse_feature_response({"features": [{"properties": {}}]}))


class InputValidationTests(unittest.TestCase):
    """Must return ok=False WITHOUT touching the network."""

    def test_non_numeric(self):
        out = classify_land_cover("abc", -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("must be numbers", out["error"])

    def test_out_of_range(self):
        out = classify_land_cover(200.0, -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("out of range", out["error"])

    def test_bad_year(self):
        out = classify_land_cover(38.6, -90.2, year=1999)
        self.assertFalse(out["ok"])
        self.assertIn("unavailable NLCD year", out["error"])


if __name__ == "__main__":
    unittest.main()
