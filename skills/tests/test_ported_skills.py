"""Offline tests for the skills ported from the a2a-sean branch — no network.

Covers input validation (must not hit network) and the pure helpers.
"""
from __future__ import annotations

import unittest

from skills._common import as_bool_flag, as_float, haversine_meters, validated_coords
from skills.contamination import find_contamination_sources
from skills.elevation import find_elevation_terrain
from skills.flood_zone import find_flood_zone
from skills.geocode import geocode_address
from skills.proximity import build_overpass_query, find_nearby_features


class CommonHelperTests(unittest.TestCase):
    def test_as_float(self):
        self.assertEqual(as_float("3.5"), 3.5)
        self.assertIsNone(as_float(""))
        self.assertIsNone(as_float(None))
        self.assertIsNone(as_float("abc"))

    def test_as_bool_flag(self):
        self.assertTrue(as_bool_flag("Y"))
        self.assertFalse(as_bool_flag("N"))
        self.assertFalse(as_bool_flag(None))

    def test_haversine(self):
        self.assertAlmostEqual(haversine_meters(38, -90, 39, -90), 111195, delta=500)

    def test_validated_coords(self):
        self.assertEqual(validated_coords("38.6", "-90.2"), (38.6, -90.2))
        with self.assertRaises(ValueError):
            validated_coords("x", 0)
        with self.assertRaises(ValueError):
            validated_coords(200, 0)


class InputValidationTests(unittest.TestCase):
    """Point skills must return ok=False WITHOUT touching the network."""

    def test_contamination(self):
        out = find_contamination_sources("x", 0)
        self.assertFalse(out["ok"])
        self.assertEqual(out["skill"], "contamination")

    def test_elevation_out_of_range(self):
        out = find_elevation_terrain(200, 0)
        self.assertFalse(out["ok"])
        self.assertIn("out of range", out["error"])

    def test_flood_zone(self):
        out = find_flood_zone("bad", "coords")
        self.assertFalse(out["ok"])

    def test_proximity(self):
        out = find_nearby_features(999, 0)
        self.assertFalse(out["ok"])

    def test_geocode_empty_address(self):
        out = geocode_address("   ")
        self.assertFalse(out["ok"])
        self.assertEqual(out["skill"], "geocode")


class OverpassQueryTests(unittest.TestCase):
    def test_query_contains_categories_and_point(self):
        q = build_overpass_query(38.6, -90.2, 500)
        self.assertIn("landuse", q)
        self.assertIn("around:500,38.6,-90.2", q)
        self.assertIn("out center tags;", q)


if __name__ == "__main__":
    unittest.main()
