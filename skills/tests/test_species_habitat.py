"""Offline tests for the species/critical-habitat (IPaC) skill — no network.

Covers the pure resources parser against a recorded IPaC payload and the
input-validation failures that must NOT hit the network.
"""
from __future__ import annotations

import unittest

from skills.species_habitat import (
    parse_ipac_resources,
    species_at_location,
    _footprint_polygon,
)

# Trimmed real IPaC 'resources' shape (from a live St. Louis-area response).
SAMPLE_RESOURCES = {
    "populationsBySid": {
        "Population$Sid[1]": {
            "crithabInFootprint": False,
            "population": {
                "groupName": "Mammals",
                "listingStatusName": "Endangered",
                "optionalCommonName": "Indiana bat",
                "optionalScientificName": "Myotis sodalis",
                "speciesId": 5949,
                "speciesProfileUrl": "https://ecos.fws.gov/ecp/species/5949",
            },
        },
        "Population$Sid[2]": {
            "crithabInFootprint": True,
            "population": {
                "groupName": "Clams",
                "listingStatusName": "Endangered",
                "optionalCommonName": "Scaleshell mussel",
                "optionalScientificName": "Leptodea leptodon",
                "speciesId": 4133,
            },
        },
    },
    "crithabs": [],
    "migbirds": [
        {"phenologySpecies": {"commonName": "Bald Eagle", "scientificName": "Haliaeetus leucocephalus"}},
        {"phenologySpecies": {"commonName": "Rusty Blackbird", "scientificName": "Euphagus carolinus"}},
    ],
    "fieldOffices": [{"officeName": "Missouri ESFO", "formattedPhone": "555-1234",
                      "formattedPhysicalCity": "Columbia", "formattedPhysicalState": "MO"}],
}


class ParseTests(unittest.TestCase):
    def test_esa_species(self):
        p = parse_ipac_resources(SAMPLE_RESOURCES)
        names = {s["common_name"] for s in p["esa_species"]}
        self.assertEqual(names, {"Indiana bat", "Scaleshell mussel"})
        bat = next(s for s in p["esa_species"] if s["common_name"] == "Indiana bat")
        self.assertEqual(bat["listing_status"], "Endangered")
        self.assertEqual(bat["profile_url"], "https://ecos.fws.gov/ecp/species/5949")

    def test_profile_url_fallback_from_species_id(self):
        p = parse_ipac_resources(SAMPLE_RESOURCES)
        mussel = next(s for s in p["esa_species"] if s["common_name"] == "Scaleshell mussel")
        self.assertEqual(mussel["profile_url"], "https://ecos.fws.gov/ecp/species/4133")

    def test_critical_habitat_flag(self):
        p = parse_ipac_resources(SAMPLE_RESOURCES)
        self.assertEqual([c["species"] for c in p["critical_habitat"]], ["Scaleshell mussel"])

    def test_migbirds_and_office(self):
        p = parse_ipac_resources(SAMPLE_RESOURCES)
        self.assertEqual(p["migratory_birds"], ["Bald Eagle", "Rusty Blackbird"])
        self.assertEqual(p["field_office"]["name"], "Missouri ESFO")

    def test_empty_resources_not_invented(self):
        p = parse_ipac_resources({})
        self.assertEqual(p["esa_species"], [])
        self.assertEqual(p["migratory_birds"], [])
        self.assertIsNone(p["field_office"])


class FootprintTests(unittest.TestCase):
    def test_polygon_is_closed_ring(self):
        import json
        geom = json.loads(_footprint_polygon(38.6, -90.2, 0.02))
        self.assertEqual(geom["type"], "Polygon")
        ring = geom["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])  # closed
        self.assertEqual(len(ring), 5)


class InputValidationTests(unittest.TestCase):
    """Must return ok=False WITHOUT touching the network."""

    def test_non_numeric(self):
        out = species_at_location("x", -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("must be numbers", out["error"])

    def test_out_of_range(self):
        out = species_at_location(95.0, -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("out of range", out["error"])


if __name__ == "__main__":
    unittest.main()
