"""Offline tests for the protected-areas (PAD-US) skill — no network."""
from __future__ import annotations

import unittest

from skills.protected_areas import (
    analyze_protected_area,
    decode_feature,
    dedupe_areas,
)


class DecodeTests(unittest.TestCase):
    def test_decodes_known_codes(self):
        a = decode_feature({
            "Unit_Nm": "Yellowstone National Park", "Des_Tp": "NP",
            "Own_Type": "FED", "Own_Name": "NPS", "Mang_Type": "FED", "Mang_Name": "NPS",
            "GAP_Sts": "1", "Pub_Access": "OA", "State_Nm": "WY", "GIS_Acres": 2000000,
        })
        self.assertEqual(a["designation"], "National Park")
        self.assertEqual(a["owner_type"], "Federal")
        self.assertTrue(a["gap_status"].startswith("1 - managed for biodiversity"))
        self.assertEqual(a["public_access"], "Open Access")

    def test_unknown_code_passes_through(self):
        a = decode_feature({"Unit_Nm": "X", "Des_Tp": "ZZZ", "GAP_Sts": "9"})
        self.assertEqual(a["designation"], "ZZZ")       # not invented
        self.assertEqual(a["gap_status"], "9")
        self.assertEqual(a["designation_code"], "ZZZ")

    def test_name_fallback_to_loc_nm(self):
        a = decode_feature({"Loc_Nm": "Some Local Park", "Des_Tp": "LP"})
        self.assertEqual(a["name"], "Some Local Park")


class DedupeTests(unittest.TestCase):
    def test_dedupe_by_name_designation_manager(self):
        rows = [
            {"name": "A", "designation_code": "NP", "manager": "NPS"},
            {"name": "A", "designation_code": "NP", "manager": "NPS"},  # dup
            {"name": "A", "designation_code": "WA", "manager": "NPS"},  # different desig
        ]
        self.assertEqual(len(dedupe_areas(rows)), 2)


class InputValidationTests(unittest.TestCase):
    """Must return ok=False WITHOUT touching the network."""

    def test_non_numeric(self):
        out = analyze_protected_area("x", -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("must be numbers", out["error"])

    def test_out_of_range(self):
        out = analyze_protected_area(100, -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("out of range", out["error"])


if __name__ == "__main__":
    unittest.main()
