"""Small checks for the graph logic; run with python3 -m unittest discover -s tests."""

import tempfile
import unittest
from pathlib import Path

from start import (
    average_out_degree,
    bfs,
    citation_ages,
    dfs,
    in_degree,
    in_degrees,
    load_cases,
    load_graph,
    most_cited,
    shortest_path,
)


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.graph = {
            "A": ["B", "C"],
            "B": ["D"],
            "C": ["D"],
            "D": ["A"],
            "E": [],
        }

    def test_traversal_handles_cycles_and_shared_neighbors(self):
        expected = {"A", "B", "C", "D"}
        self.assertEqual(bfs(self.graph, "A"), expected)
        self.assertEqual(dfs(self.graph, "A"), expected)
        self.assertEqual(bfs(self.graph, "E"), {"E"})

    def test_shortest_path_reconstructs_a_directed_path(self):
        self.assertEqual(shortest_path(self.graph, "A", "D"), ["A", "B", "D"])
        self.assertEqual(shortest_path(self.graph, "A", "A"), ["A"])
        self.assertIsNone(shortest_path(self.graph, "A", "E"))
        self.assertIsNone(shortest_path(self.graph, "E", "A"))
        self.assertEqual(shortest_path(self.graph, "A", "C"), ["A", "C"])

    def test_incoming_counts_and_most_cited(self):
        expected = {"A": 1, "B": 1, "C": 1, "D": 2, "E": 0}
        self.assertEqual(in_degrees(self.graph), expected)
        self.assertEqual(in_degree(self.graph, "D"), 2)
        self.assertEqual(most_cited(self.graph), "D")
        self.assertIsNone(most_cited({}))
        self.assertEqual(most_cited({"A": [], "B": []}), "A")

    def test_average_includes_sources_with_no_edges(self):
        self.assertEqual(average_out_degree(self.graph, ["A", "E"]), 1)
        with self.assertRaises(ValueError):
            average_out_degree(self.graph, [])

    def test_ages_count_each_link_and_allow_same_year(self):
        graph = {"A": ["C", "D"], "B": ["C"], "C": [], "D": [], "E": []}
        years = {"A": 2025, "B": 2024, "C": 1995, "D": 2025, "E": 2025}
        self.assertEqual(citation_ages(graph, ["A", "B", "E"], years), [30, 0, 29])

    def test_csv_loading_keeps_isolated_cases_and_deduplicates_edges(self):
        with tempfile.TemporaryDirectory() as directory:
            cases_path = Path(directory) / "cases.csv"
            citations_path = Path(directory) / "citations.csv"
            cases_path.write_text(
                'case_id,case_name,date_filed,is_source\n'
                'A,"Example, Inc.",2025-01-01,True\n'
                'B,Precedent,1995-01-01,False\n'
                'C,Isolated source,2025-02-01,True\n',
                encoding="utf-8",
            )
            citations_path.write_text("citing_case,cited_case\nA,B\nA,B\n", encoding="utf-8")
            names, years, sources = load_cases(cases_path)
            graph = load_graph(citations_path, names)

        self.assertEqual(names["A"], "Example, Inc.")
        self.assertEqual(years["B"], 1995)
        self.assertEqual(sources, ["A", "C"])
        self.assertEqual(graph, {"A": ["B"], "B": [], "C": []})
        self.assertEqual(average_out_degree(graph, sources), 0.5)


if __name__ == "__main__":
    unittest.main()
