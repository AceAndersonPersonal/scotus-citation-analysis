"""Verify weighting, overlap, and annual export behavior."""

import json
from pathlib import Path
import tempfile
import unittest

from annual_summary import age_shares, collect_annual, precedent_overlap, write_outputs


class AnnualTests(unittest.TestCase):
    def test_age_bands_weight_opinions_equally_and_exclude_zero_link_ages(self):
        graph = {"A": ["old1", "old2", "new"], "B": ["new"], "zero": []}
        years = {"A": 2020, "B": 2020, "zero": 2020, "old1": 1900, "old2": 1970, "new": 2010}
        shares = age_shares(graph, ["A", "B", "zero"], years)
        self.assertAlmostEqual(shares["mean_share_0_to_10_years"], 2 / 3)
        self.assertAlmostEqual(shares["mean_share_50_plus_years"], 1 / 3)
        self.assertIsNone(age_shares(graph, ["zero"], years)["mean_share_0_to_10_years"])
        with self.assertRaises(ValueError):
            age_shares({"A": ["future"]}, ["A"], {"A": 2020, "future": 2021})

    def test_overlap_is_shared_divided_by_union(self):
        result = precedent_overlap({"A", "B", "C"}, {"B", "C", "D"})
        self.assertEqual(result, {"shared_precedents": 2, "union_precedents": 4, "jaccard_share": 0.5})
        self.assertIsNone(precedent_overlap(set(), set())["jaccard_share"])

    def test_real_data_exports_and_consecutive_term_pairs(self):
        result = collect_annual()
        terms = [r["term"] for r in result["terms"]]
        self.assertTrue({2004, 2020, 2021, 2022, 2023, 2024}.issubset(terms))
        self.assertEqual([(r["earlier_term"], r["later_term"]) for r in result["consecutive_term_overlap"]],
                         [(a, b) for a, b in zip(terms, terms[1:]) if b == a + 1])
        self.assertEqual(len(result["opinions"]), sum(r["source_cases"] for r in result["terms"]))
        with tempfile.TemporaryDirectory() as directory:
            write_outputs(result, directory)
            self.assertEqual(json.loads((Path(directory) / "annual_summary.json").read_text()), result)
            self.assertIn("preliminary", (Path(directory) / "annual_summary.html").read_text())
            self.assertTrue((Path(directory) / "annual_opinion_metrics.csv").exists())


if __name__ == "__main__":
    unittest.main()
