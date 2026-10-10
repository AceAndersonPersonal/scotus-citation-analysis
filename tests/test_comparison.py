"""Check weighting and omission arithmetic with small, hand-calculated graphs."""

import csv
import json
from pathlib import Path
import tempfile
import unittest

from compare_terms import compare_terms, omission_effects, opinion_metrics, summarize_opinions, write_outputs
from start import summarize_term


class OpinionComparisonTests(unittest.TestCase):
    def test_opinions_and_links_receive_different_weights(self):
        graph = {"A": ["P", "Q", "R", "S"], "B": ["T"], "Z": []}
        years = {case: 2000 for case in ("A", "B", "Z", "P", "Q", "R", "S")}
        years["T"] = 1900
        names = {case: case for case in graph}
        rows = opinion_metrics(graph, ["A", "B", "Z"], years, names)
        summary = summarize_opinions(rows)
        self.assertEqual(summary["link_weighted_mean_age"], 20)
        self.assertEqual(summary["equal_opinion_mean_age"], 50)
        self.assertEqual(summary["median_of_opinion_mean_ages"], 50)
        self.assertEqual(summary["sources_with_age_data"], 2)
        self.assertEqual(summary["zero_link_sources"], 1)
        self.assertEqual(summary["median_cited_cases"], 1)
        self.assertAlmostEqual(summary["mean_cited_cases"], 5 / 3)
        self.assertIsNone(rows[2]["mean_citation_age"])

    def test_omissions_start_from_full_data_and_keep_direction(self):
        def row(case, age):
            return {"case_id": case, "case_name": case, "mean_citation_age": age}
        before = [row("A", 10), row("B", 30), row("Zero", None)]
        after = [row("C", 50), row("D", 70)]
        effects = {r["case_id"]: r for r in omission_effects(before, after)}
        self.assertEqual(set(effects), {"A", "B", "C", "D"})
        self.assertEqual(effects["A"]["difference_after_omission"], 30)
        self.assertEqual(effects["B"]["difference_after_omission"], 50)
        self.assertEqual(effects["C"]["difference_after_omission"], 50)
        self.assertEqual(effects["D"]["difference_after_omission"], 30)
        self.assertEqual(effects["C"]["change_from_full_difference"], 10)
        self.assertEqual(effects["D"]["change_from_full_difference"], -10)

    def test_empty_and_singleton_age_sets_do_not_invent_results(self):
        empty = summarize_opinions([])
        self.assertIsNone(empty["mean_cited_cases"])
        self.assertIsNone(empty["equal_opinion_mean_age"])
        rows = opinion_metrics({"Z": []}, ["Z"], {"Z": 2000}, {"Z": "Zero"})
        summary = summarize_opinions(rows)
        self.assertEqual(summary["mean_cited_cases"], 0)
        self.assertIsNone(summary["link_weighted_mean_age"])
        self.assertEqual(omission_effects(rows, rows), [])
        single = [{"case_id": "A", "case_name": "A", "mean_citation_age": 10}]
        self.assertEqual(omission_effects(single, single), [])

    def test_negative_ages_and_reversed_terms_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Negative citation age"):
            opinion_metrics({"A": ["B"]}, ["A"], {"A": 2000, "B": 2001}, {"A": "A"})
        with self.assertRaisesRegex(ValueError, "chronological order"):
            compare_terms(2024, 2004)

    def test_real_data_reconciles_with_existing_analysis_and_exports(self):
        result = compare_terms(2004, 2024)
        for term in result["terms"]:
            existing = summarize_term(term["term"])
            self.assertEqual(term["summary"]["citation_links"], existing["edges"])
            self.assertAlmostEqual(term["summary"]["link_weighted_mean_age"], existing["average_citation_age"])
            self.assertEqual(len(term["opinions"]), existing["source_cases"])
        with tempfile.TemporaryDirectory() as directory:
            write_outputs(result, directory)
            root = Path(directory)
            self.assertEqual(json.loads((root / "opinion_comparison.json").read_text()), result)
            with (root / "opinion_metrics.csv").open() as file:
                rows = list(csv.DictReader(file))
            self.assertEqual(len(rows), sum(t["summary"]["source_cases"] for t in result["terms"]))
            for row in rows:
                if row["cited_cases"] == "0":
                    self.assertEqual(row["mean_citation_age"], "")
            with (root / "opinion_omission_effects.csv").open() as file:
                omissions = list(csv.DictReader(file))
            self.assertEqual(len(omissions), result["one_opinion_sensitivity"]["tested_omissions"])


if __name__ == "__main__":
    unittest.main()
