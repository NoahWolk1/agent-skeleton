"""Offline tests for the construction/land-use skill — no network.

Covers the pure zoning-code classifier and the input-validation failures that
must NOT hit the network.
"""
from __future__ import annotations

import unittest

from skills.construction import analyze_land_use, classify_zoning_code


class ClassifyZoningTests(unittest.TestCase):
    def test_residential(self):
        z = classify_zoning_code("R4")
        self.assertEqual(z["category"], "Residential")
        self.assertFalse(z["is_floodplain"])

    def test_commercial_with_hyphen(self):
        self.assertEqual(classify_zoning_code("C-2")["category"], "Commercial")

    def test_industrial(self):
        self.assertEqual(classify_zoning_code("M2")["category"], "Industrial/Manufacturing")

    def test_non_urban(self):
        self.assertIn("Non-Urban", classify_zoning_code("NU")["category"])

    def test_mixed_use(self):
        self.assertEqual(classify_zoning_code("MXD")["category"], "Mixed-Use Development")

    def test_floodplain_pure(self):
        z = classify_zoning_code("FP")
        self.assertTrue(z["is_floodplain"])
        self.assertEqual(z["category"], "Flood Plain")

    def test_floodplain_with_underlying_use(self):
        z = classify_zoning_code("FPR4")
        self.assertTrue(z["is_floodplain"])
        self.assertEqual(z["category"], "Residential")  # underlying use surfaced
        self.assertIn("Flood Plain overlay", z["label"])

    def test_floodplain_industrial(self):
        z = classify_zoning_code("FPM2")
        self.assertTrue(z["is_floodplain"])
        self.assertEqual(z["category"], "Industrial/Manufacturing")

    def test_specialized_not_invented(self):
        self.assertIn("PS", classify_zoning_code("PS")["category"])
        self.assertIn("KP", classify_zoning_code("KP")["category"])

    def test_blank_code(self):
        z = classify_zoning_code(" ")
        self.assertEqual(z["category"], "Unknown")
        self.assertFalse(z["is_floodplain"])


class InputValidationTests(unittest.TestCase):
    """Must return ok=False WITHOUT touching the network."""

    def test_non_numeric(self):
        out = analyze_land_use("x", -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("must be numbers", out["error"])

    def test_out_of_range(self):
        out = analyze_land_use(999, -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("out of range", out["error"])


if __name__ == "__main__":
    unittest.main()
