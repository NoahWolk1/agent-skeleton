"""Offline tests for the air-quality skill — no network."""
from __future__ import annotations

import unittest

from skills.air_quality import aqi_category, air_quality_at, parse_current

SAMPLE = {
    "current": {"time": "2026-07-22T03:00", "us_aqi": 56, "pm2_5": 6.2, "pm10": 6.2,
                "ozone": 72.0, "nitrogen_dioxide": 7.0, "sulphur_dioxide": 0.8, "carbon_monoxide": 152.0},
    "current_units": {"us_aqi": "USAQI", "pm2_5": "μg/m³", "ozone": "μg/m³"},
}


class AqiCategoryTests(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(aqi_category(0), "Good")
        self.assertEqual(aqi_category(56), "Moderate")
        self.assertEqual(aqi_category(120), "Unhealthy for Sensitive Groups")
        self.assertEqual(aqi_category(175), "Unhealthy")
        self.assertEqual(aqi_category(250), "Very Unhealthy")
        self.assertEqual(aqi_category(400), "Hazardous")

    def test_bad_value(self):
        self.assertIsNone(aqi_category(None))
        self.assertIsNone(aqi_category("n/a"))


class ParseTests(unittest.TestCase):
    def test_parse(self):
        p = parse_current(SAMPLE)
        self.assertEqual(p["us_aqi"], 56)
        self.assertEqual(p["aqi_category"], "Moderate")
        self.assertEqual(p["pollutants"]["pm2_5"]["value"], 6.2)
        self.assertEqual(p["pollutants"]["pm2_5"]["label"], "PM2.5")
        self.assertIn("g/m", p["pollutants"]["pm2_5"]["unit"])

    def test_empty(self):
        p = parse_current({})
        self.assertIsNone(p["us_aqi"])
        self.assertEqual(p["pollutants"], {})


class InputValidationTests(unittest.TestCase):
    """Must return ok=False WITHOUT touching the network."""

    def test_non_numeric(self):
        out = air_quality_at("x", -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("must be numbers", out["error"])

    def test_out_of_range(self):
        out = air_quality_at(-999, 0)
        self.assertFalse(out["ok"])
        self.assertIn("out of range", out["error"])


if __name__ == "__main__":
    unittest.main()
