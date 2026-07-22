"""Offline tests for the orchestrator's pure logic + no-network control paths.

Skill-running paths hit the network and are covered by manual/live checks; here
we test planning, location parsing, confidence, and the decline / input-required
branches, none of which touch the network.
"""
from __future__ import annotations

import asyncio
import unittest

import handler as H


class CoordAndPlaceTests(unittest.TestCase):
    def test_coords_from_text(self):
        self.assertEqual(H._coords_from_text("at 44.4237, -110.5885 now"), (44.4237, -110.5885))
        self.assertEqual(H._coords_from_text("16.26887 2.37307"), (16.26887, 2.37307))
        self.assertIsNone(H._coords_from_text("no coordinates in this sentence"))

    def test_place_from_text(self):
        self.assertEqual(H._place_from_text("contamination near Forest Park, St. Louis"),
                         "Forest Park, St. Louis")
        self.assertEqual(H._place_from_text("soil in Ames, Iowa?"), "Ames, Iowa")
        self.assertIsNone(H._place_from_text("just tell me things"))


class HeuristicPlanTests(unittest.TestCase):
    def test_selects_skills_by_keyword(self):
        p = H._heuristic_plan("what is the habitat and species here at 44.42, -110.59")
        self.assertTrue(p["is_geospatial"])
        self.assertEqual(p["latitude"], 44.42)
        self.assertIn("satellite", p["skills"])
        self.assertIn("species_habitat", p["skills"])

    def test_non_geospatial(self):
        p = H._heuristic_plan("write me a poem about my cat")
        self.assertFalse(p["is_geospatial"])

    def test_place_query_when_no_coords(self):
        p = H._heuristic_plan("contamination near Forest Park, St. Louis")
        self.assertTrue(p["is_geospatial"])
        self.assertEqual(p["location_query"], "Forest Park, St. Louis")
        self.assertIn("contamination", p["skills"])


class HasDataAndConfidenceTests(unittest.TestCase):
    def test_has_data(self):
        self.assertTrue(H._has_data({"ok": True, "species": [{"x": 1}]}))
        self.assertTrue(H._has_data({"ok": True, "is_wetland": True}))
        self.assertFalse(H._has_data({"ok": True, "note": "none", "species": []}))
        self.assertFalse(H._has_data({"ok": False, "error": "x"}))

    def test_confidence_levels(self):
        good = {"a": {"ok": True, "x": [1]}, "b": {"ok": True, "y": [1]}, "c": {"ok": True, "z": [1]}}
        lvl, _ = H._confidence(good, None, llm_used=True)
        self.assertEqual(lvl, "high")
        # no LLM caps high -> medium
        lvl2, _ = H._confidence(good, None, llm_used=False)
        self.assertEqual(lvl2, "medium")
        # validator failure -> low
        lvl3, _ = H._confidence(good, False, llm_used=True)
        self.assertEqual(lvl3, "low")

    def test_collect_sources(self):
        facts = {"satellite": {"ok": True, "source": "NLCD", "source_url": "http://x"},
                 "bad": {"ok": False, "error": "e"}}
        srcs = H._collect_sources(facts)
        self.assertEqual(len(srcs), 1)
        self.assertEqual(srcs[0]["skill"], "satellite")


class ControlPathTests(unittest.TestCase):
    """Empty and non-geospatial inputs return WITHOUT touching the network."""

    def _run(self, text):
        return asyncio.run(GeoRun(text))

    def test_empty_input(self):
        r = asyncio.run(H.GeoOrchestratorHandler({}).handle_structured(""))
        self.assertEqual(r["status"], "input_required")
        self.assertIn("answer", r)

    def test_non_geospatial_declined(self):
        r = asyncio.run(H.GeoOrchestratorHandler({}).handle_structured("write a poem about my cat"))
        self.assertEqual(r["status"], "declined")
        self.assertIn("answer", r)


async def GeoRun(text):  # helper kept for symmetry / future use
    return await H.GeoOrchestratorHandler({}).handle_structured(text)


if __name__ == "__main__":
    unittest.main()
