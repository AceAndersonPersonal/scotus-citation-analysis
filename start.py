"""Load the curated SCOTUS datasets and compare their citation summaries."""

import csv
from pathlib import Path
from collections import deque
from statistics import median

DATA_DIR = Path(__file__).resolve().parent / "data"
TERMS = (2004, 2024)

def load_cases(filename):
    """Return name and year dictionaries, plus a list of source case IDs."""
    case_names = {}
    case_years = {}
    source_ids = []

    with open(filename, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            case_id = row["case_id"]
            case_names[case_id] = row["case_name"]
            case_years[case_id] = int(row["date_filed"][:4])

            if row["is_source"] == "True":
                source_ids.append(case_id)

    return case_names, case_years, source_ids

def load_graph(filename, case_ids=()):
    """Build a binary adjacency list, including supplied cases with no edges."""
    graph = {}
    seen_edges = set()

    for case_id in case_ids:
        graph[case_id] = []

    with open(filename, newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            citing = row["citing_case"]
            cited = row["cited_case"]

            if citing not in graph:
                graph[citing] = []

            if cited not in graph:
                graph[cited] = []

            edge = (citing, cited)
            if edge not in seen_edges:
                graph[citing].append(cited)
                seen_edges.add(edge)

    return graph

def load_term(term, data_dir=DATA_DIR):
    """Load one term without mixing its cases or citations with another term."""
    term_dir = Path(data_dir) / f"term_{term}"
    case_names, case_years, source_ids = load_cases(term_dir / "cases.csv")
    graph = load_graph(term_dir / "citations.csv", case_names)

    for case_id in graph:
        if case_id not in case_names:
            raise ValueError(f"Citation references an unknown case: {case_id}")

    return graph, case_names, case_years, source_ids

def in_degree(graph, case):
    """Count incoming edges for one case."""
    count = 0

    for neighbors in graph.values():
        for cited_id in neighbors:
            if cited_id == case:
                count += 1

    return count

def in_degrees(graph):
    """Count incoming edges for all cases in one pass through the graph."""
    counts = {}

    for case_id in graph:
        counts[case_id] = 0

    for neighbors in graph.values():
        for cited_id in neighbors:
            counts[cited_id] += 1

    return counts

def most_cited(graph):
    """Return a highest-degree case ID, or None if the graph has no nodes.

    Ties keep the first case in the graph's insertion order.
    """
    counts = in_degrees(graph)
    if not counts:
        return None

    return max(counts, key=counts.get)

def dfs(graph, start):
    """Return the cases reachable from start, including start itself."""
    visited = set()

    def visit(node):
        visited.add(node)

        for neighbor in graph[node]:
            if neighbor not in visited:
                visit(neighbor)

    visit(start)
    return visited

def bfs(graph, start):
    """Return reachable cases, adding each case to the queue only once."""
    visited = {start}
    queue = deque([start])

    while queue:
        node = queue.popleft()

        for neighbor in graph[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    return visited

def shortest_path(graph, start, target):
    """Return a shortest directed path as a list, or None if unreachable."""
    parent = {start: None}
    queue = deque([start])

    while queue:
        node = queue.popleft()

        if node == target:
            path = []

            while node is not None:
                path.append(node)
                node = parent[node]

            path.reverse()
            return path

        for neighbor in graph[node]:
            if neighbor not in parent:
                parent[neighbor] = node
                queue.append(neighbor)

    return None

def average_out_degree(graph, source_ids):
    """Average distinct cited cases per source, including zero-edge sources."""
    if not source_ids:
        raise ValueError("An average requires at least one source case.")

    total_citations = 0

    for case_id in source_ids:
        total_citations += len(graph[case_id])

    return total_citations / len(source_ids)

def citation_ages(graph, source_ids, case_years):
    """Return one calendar-year difference per source-to-target citation edge."""
    ages = []

    for case_id in source_ids:
        for cited_id in graph[case_id]:
            age = case_years[case_id] - case_years[cited_id]
            ages.append(age)

    return ages

def summarize_term(term, data_dir=DATA_DIR):
    """Calculate a term's results without printing, so they can be reused."""
    graph, case_names, case_years, source_ids = load_term(term, data_dir)
    ages = citation_ages(graph, source_ids, case_years)
    top_case = most_cited(graph)

    edge_count = 0
    for neighbors in graph.values():
        edge_count += len(neighbors)

    summary = {
        "term": term,
        "nodes": len(graph),
        "edges": edge_count,
        "source_cases": len(source_ids),
        "most_cited_case": case_names[top_case] if top_case is not None else None,
        "average_out_degree": average_out_degree(graph, source_ids) if source_ids else None,
        "citation_links_with_ages": len(ages),
        "average_citation_age": None,
        "youngest_citation_age": None,
        "oldest_citation_age": None,
        "median_citation_age": None,
    }

    if ages:
        summary["average_citation_age"] = sum(ages) / len(ages)
        summary["youngest_citation_age"] = min(ages)
        summary["oldest_citation_age"] = max(ages)
        summary["median_citation_age"] = median(ages)

    return summary

def print_summary(summary):
    """Display the same clearly labeled measurements for either term."""
    print(f"Term {summary['term']}")
    print("Source cases:", summary["source_cases"])
    print("Nodes:", summary["nodes"])
    print("Edges:", summary["edges"])
    print("Most cited case (ties possible):", summary["most_cited_case"])

    if summary["average_out_degree"] is not None:
        print(f"Average distinct cited cases per source: {summary['average_out_degree']:.2f}")
    else:
        print("No source cases to calculate an average for.")

    if summary["average_citation_age"] is not None:
        print(f"Average citation age: {summary['average_citation_age']:.2f} years")
        print(f"Median citation age: {summary['median_citation_age']:.2f} years")
        print("Citation links with ages:", summary["citation_links_with_ages"])
        print("Youngest citation age:", summary["youngest_citation_age"])
        print("Oldest citation age:", summary["oldest_citation_age"])
    else:
        print("No citation links to calculate ages for.")

def main():
    for term in TERMS:
        print_summary(summarize_term(term))
        print()

if __name__ == "__main__":
    main()
