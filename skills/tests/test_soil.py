"""Offline tests for the soil (SSURGO) skill — no network."""
from __future__ import annotations

import unittest

from skills.soil import parse_sda_table, soil_at_location

SAMPLE = {
    "Table": [
        ["mukey", "muname", "farmlndcl", "compname", "comppct_r", "drainagecl", "taxorder", "taxsubgrp", "hydricrating"],
        ["411278", "Hanlon-Spillville complex", "Farmland of statewide importance", "Hanlon", "60",
         "Moderately well drained", "Mollisols", "Cumulic Hapludolls", "No"],
        ["411278", "Hanlon-Spillville complex", "Farmland of statewide importance", "Spillville", "35",
         "Somewhat poorly drained", "Mollisols", "Cumulic Hapludolls", "No"],
    ]
}


class ParseTests(unittest.TestCase):
    def test_parses_rows(self):
        rows = parse_sda_table(SAMPLE)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["compname"], "Hanlon")
        self.assertEqual(rows[0]["taxorder"], "Mollisols")

    def test_empty_variants(self):
        self.assertEqual(parse_sda_table({}), [])
        self.assertEqual(parse_sda_table({"Table": None}), [])
        self.assertEqual(parse_sda_table({"Table": [["hdr"]]}), [])  # header only, no data


class InputValidationTests(unittest.TestCase):
    """Must return ok=False WITHOUT touching the network."""

    def test_non_numeric(self):
        out = soil_at_location("x", -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("must be numbers", out["error"])

    def test_out_of_range(self):
        out = soil_at_location(91, 0)
        self.assertFalse(out["ok"])
        self.assertIn("out of range", out["error"])


if __name__ == "__main__":
    unittest.main()
