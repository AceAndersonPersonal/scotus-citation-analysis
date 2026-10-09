"""Validate the included datasets without API credentials or local raw caches."""

import csv
import json
import unittest
from datetime import date
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TERMS = (2004, 2024)


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


class DatasetTests(unittest.TestCase):
    def test_nodes_and_edges_match_manifests(self):
        for term in TERMS:
            with self.subTest(term=term):
                folder = DATA_DIR / f"term_{term}"
                cases = read_csv(folder / "cases.csv")
                citations = read_csv(folder / "citations.csv")
                manifest = json.loads((folder / "manifest.json").read_text())
                by_id = {row["case_id"]: row for row in cases}
                pairs = {(row["citing_case"], row["cited_case"]) for row in citations}
                sources = [row for row in cases if row["is_source"] == "True"]

                self.assertEqual(len(by_id), len(cases), "Duplicate case IDs")
                self.assertEqual(len(pairs), len(citations), "Duplicate binary edges")
                self.assertEqual(len(cases), manifest["nodes"])
                self.assertEqual(len(citations), manifest["binary_edges"])
                self.assertEqual(len(sources), manifest["included_source_cases"])
                self.assertTrue(all(row["is_source"] in ("True", "False") for row in cases))

                for source, target in pairs:
                    self.assertIn(source, by_id)
                    self.assertIn(target, by_id)
                    self.assertNotEqual(source, target)
                    self.assertEqual(by_id[source]["is_source"], "True")
                    source_date = by_id[source]["date_filed"]
                    target_date = by_id[target]["date_filed"]
                    for value in (source_date, target_date):
                        self.assertRegex(value, r"^\d{4}(-\d{2}){0,2}$")
                        # Validate calendar components; do not change partial archive dates.
                        date.fromisoformat((value + "-01-01")[:10])
                    precision = min(len(source_date), len(target_date))
                    self.assertLessEqual(target_date[:precision], source_date[:precision])

    def test_every_edge_has_recorded_evidence(self):
        for term in TERMS:
            with self.subTest(term=term):
                folder = DATA_DIR / f"term_{term}"
                citations = read_csv(folder / "citations.csv")
                evidence = json.loads((folder / "edge_evidence.json").read_text())
                pairs = {(row["citing_case"], row["cited_case"]) for row in citations}
                recorded = {(row["citing_case"], row["cited_case"]) for row in evidence}
                self.assertEqual(recorded, pairs)

    def test_shared_precedents_keep_the_same_ids(self):
        earlier = read_csv(DATA_DIR / "term_2004/cases.csv")
        later = read_csv(DATA_DIR / "term_2024/cases.csv")
        earlier_ids = {row["us_citation"].replace(" ", ""): row["case_id"] for row in earlier}
        shared = 0
        for row in later:
            citation = row["us_citation"].replace(" ", "")
            if citation in earlier_ids:
                self.assertEqual(row["case_id"], earlier_ids[citation], citation)
                shared += 1
        self.assertGreater(shared, 0, "Expected shared precedents across terms")


if __name__ == "__main__":
    unittest.main()
