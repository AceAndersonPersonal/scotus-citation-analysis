"""Check citation concentration, cutoff ties, and source-case denominators."""

import unittest

from start import citation_concentration, ranked_precedents


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.graph = {
            "S1": ["A", "B", "C"],
            "S2": ["A", "B", "C"],
            "S3": ["A"],
            "S0": [],
            "A": [],
            "B": [],
            "C": [],
            "outside": ["A"],
        }
        self.sources = ["S1", "S2", "S3", "S0"]
        self.names = {"A": "Alpha", "B": "Beta", "C": "Charlie"}

    def test_cutoff_includes_ties_and_percentages_use_all_selected_sources(self):
        rows = ranked_precedents(self.graph, self.sources, self.names, top_n=2)
        self.assertEqual([row["case_id"] for row in rows], ["A", "B", "C"])
        self.assertEqual([row["rank"] for row in rows], [1, 2, 2])
        self.assertEqual([row["citing_source_cases"] for row in rows], [3, 2, 2])
        self.assertEqual([row["source_case_share"] for row in rows], [0.75, 0.5, 0.5])

    def test_order_is_stable_and_each_source_counts_once(self):
        expected = ranked_precedents(self.graph, self.sources, self.names, top_n=2)
        self.graph["S1"] = ["C", "A", "B", "A"]
        actual = ranked_precedents(self.graph, list(reversed(self.sources)), self.names, top_n=2)
        self.assertEqual(actual, expected)

    def test_empty_and_small_rankings_do_not_include_uncited_nodes(self):
        self.assertEqual(ranked_precedents(self.graph, [], self.names), [])
        self.assertEqual(ranked_precedents(self.graph, ["S0"], self.names), [])
        rows = ranked_precedents(self.graph, self.sources, self.names, top_n=10)
        self.assertEqual(len(rows), 3)

    def test_concentration_uses_exactly_n_cases_even_when_the_table_expands(self):
        graph = {"S1": ["A", "B", "C"], "S2": ["A"], "A": [], "B": [], "C": []}
        self.assertEqual(citation_concentration(graph, top_n=2), 0.75)
        rows = ranked_precedents(graph, ["S1", "S2"], self.names, top_n=2)
        self.assertEqual(len(rows), 3)
        self.assertEqual(citation_concentration(graph, top_n=10), 1.0)
        self.assertIsNone(citation_concentration({}))
        self.assertIsNone(citation_concentration({"A": []}))

    def test_nonpositive_cutoffs_are_rejected(self):
        for top_n in (0, -1):
            with self.subTest(top_n=top_n):
                with self.assertRaises(ValueError):
                    citation_concentration(self.graph, top_n)
                with self.assertRaises(ValueError):
                    ranked_precedents(self.graph, self.sources, self.names, top_n)


if __name__ == "__main__":
    unittest.main()
