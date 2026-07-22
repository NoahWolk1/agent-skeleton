"""Offline tests for the water skill — no network."""
from __future__ import annotations

import unittest

from skills.water import (
    haversine_km,
    parse_nwis_iv,
    parse_wqp_stations,
    water_at_location,
)

NWIS_SAMPLE = {
    "value": {
        "timeSeries": [
            {
                "sourceInfo": {
                    "siteName": "CAHOKIA CREEK AT EDWARDSVILLE, IL",
                    "siteCode": [{"value": "05587900"}],
                    "geoLocation": {"geogLocation": {"latitude": 38.8244, "longitude": -89.9747}},
                },
                "variable": {"variableCode": [{"value": "00060"}], "variableName": "Streamflow, ft&#179;/s"},
                "values": [{"value": [{"value": "30.0", "dateTime": "2026-07-21T20:30:00"}]}],
            },
            {
                "sourceInfo": {
                    "siteName": "CAHOKIA CREEK AT EDWARDSVILLE, IL",
                    "siteCode": [{"value": "05587900"}],
                    "geoLocation": {"geogLocation": {"latitude": 38.8244, "longitude": -89.9747}},
                },
                "variable": {"variableCode": [{"value": "00065"}], "variableName": "Gage height, ft"},
                "values": [{"value": [{"value": "3.46", "dateTime": "2026-07-21T20:30:00"}]}],
            },
        ]
    }
}


class ParseNwisTests(unittest.TestCase):
    def test_combines_params_per_site(self):
        gages = parse_nwis_iv(NWIS_SAMPLE)
        self.assertEqual(len(gages), 1)  # two series, one site
        g = gages[0]
        self.assertEqual(g["site_code"], "05587900")
        self.assertEqual(g["streamflow_cfs"], 30.0)
        self.assertEqual(g["gage_height_ft"], 3.46)
        self.assertNotIn("&#179;", g["site_name"])  # html unescaped

    def test_empty(self):
        self.assertEqual(parse_nwis_iv({}), [])
        self.assertEqual(parse_nwis_iv({"value": {"timeSeries": []}}), [])


class ParseWqpTests(unittest.TestCase):
    def test_stations(self):
        gj = {"features": [
            {"properties": {"MonitoringLocationName": "Intake 1", "MonitoringLocationTypeName": "Facility",
                            "OrganizationFormalName": "USGS", "MonitoringLocationIdentifier": "X-1"},
             "geometry": {"coordinates": [-90.19, 38.63]}}]}
        s = parse_wqp_stations(gj)
        self.assertEqual(s[0]["name"], "Intake 1")
        self.assertEqual(s[0]["latitude"], 38.63)

    def test_empty(self):
        self.assertEqual(parse_wqp_stations({}), [])


class HaversineTests(unittest.TestCase):
    def test_known_distance(self):
        # ~1 deg latitude ~= 111 km
        self.assertAlmostEqual(haversine_km(38.0, -90.0, 39.0, -90.0), 111.0, delta=1.0)

    def test_zero(self):
        self.assertEqual(haversine_km(38.0, -90.0, 38.0, -90.0), 0.0)


class InputValidationTests(unittest.TestCase):
    """Must return ok=False WITHOUT touching the network."""

    def test_non_numeric(self):
        out = water_at_location("x", -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("must be numbers", out["error"])

    def test_out_of_range(self):
        out = water_at_location(120, -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("out of range", out["error"])


if __name__ == "__main__":
    unittest.main()
