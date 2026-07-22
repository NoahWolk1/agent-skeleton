"""Offline tests for the iNaturalist skill — no network."""
from __future__ import annotations

import unittest

from skills.inaturalist import (
    observations_near,
    parse_observations,
    parse_species_counts,
)


class ParseObservationsTests(unittest.TestCase):
    def test_parses_and_upgrades_photo(self):
        payload = {"results": [{
            "taxon": {"preferred_common_name": "Bald Eagle", "name": "Haliaeetus leucocephalus"},
            "observed_on": "2026-07-20", "quality_grade": "research", "place_guess": "WY",
            "photos": [{"url": "https://x/photos/1/square.jpg"}],
            "uri": "https://www.inaturalist.org/observations/1",
        }]}
        obs = parse_observations(payload)
        self.assertEqual(obs[0]["common_name"], "Bald Eagle")
        self.assertEqual(obs[0]["photo_url"], "https://x/photos/1/medium.jpg")  # square->medium
        self.assertEqual(obs[0]["observation_url"], "https://www.inaturalist.org/observations/1")

    def test_no_photo(self):
        obs = parse_observations({"results": [{"taxon": {"name": "X"}, "photos": []}]})
        self.assertIsNone(obs[0]["photo_url"])

    def test_empty(self):
        self.assertEqual(parse_observations({}), [])


class ParseSpeciesCountsTests(unittest.TestCase):
    def test_parses(self):
        payload = {"results": [{"count": 849, "taxon": {"preferred_common_name": "Wapiti", "name": "Cervus canadensis", "id": 123}}]}
        s = parse_species_counts(payload)
        self.assertEqual(s[0]["observation_count"], 849)
        self.assertEqual(s[0]["taxon_url"], "https://www.inaturalist.org/taxa/123")

    def test_empty(self):
        self.assertEqual(parse_species_counts({}), [])


class InputValidationTests(unittest.TestCase):
    """Must return ok=False WITHOUT touching the network."""

    def test_non_numeric(self):
        out = observations_near("x", -90.0)
        self.assertFalse(out["ok"])
        self.assertIn("must be numbers", out["error"])

    def test_out_of_range(self):
        out = observations_near(0, 999)
        self.assertFalse(out["ok"])
        self.assertIn("out of range", out["error"])


if __name__ == "__main__":
    unittest.main()
