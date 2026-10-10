"""Export curated term graphs as a static case explorer; no API calls required."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
from statistics import median
import sys
from urllib.parse import urlsplit

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
from start import load_term


def opinion_url(value):
    """Only export ordinary web links from case metadata."""
    parsed = urlsplit(value)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ValueError(f"Invalid opinion URL: {value}")
    return value


def export_term(folder):
    term = int(folder.name.removeprefix("term_"))
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    graph, names, years, source_ids = load_term(term, folder.parent)
    with (folder / "cases.csv").open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    metadata = {row["case_id"]: row for row in rows}
    if len(metadata) != len(rows):
        raise ValueError(f"Term {term}: duplicate case IDs")
    if manifest["term"] != term or manifest["included_source_cases"] != len(source_ids):
        raise ValueError(f"Term {term}: source count or term differs from manifest")
    if manifest["nodes"] != len(graph) or manifest["binary_edges"] != sum(map(len, graph.values())):
        raise ValueError(f"Term {term}: graph size differs from manifest")
    source_set = set(source_ids)
    if any(graph[case_id] for case_id in graph if case_id not in source_set):
        raise ValueError(f"Term {term}: outgoing edges found for a non-source case")

    def case_details(case_id):
        row = metadata[case_id]
        return {
            "id": case_id, "name": names[case_id], "date": row["date_filed"],
            "year": years[case_id], "citation": row["us_citation"],
            "url": opinion_url(row["url"]),
        }

    sources = []
    for source_id in sorted(source_ids, key=lambda case_id: (names[case_id].casefold(), case_id)):
        source = case_details(source_id)
        citations = []
        for cited_id in graph[source_id]:
            cited = case_details(cited_id)
            cited["age"] = years[source_id] - years[cited_id]
            if cited["age"] < 0:
                raise ValueError(f"Term {term}: negative citation age")
            citations.append(cited)
        citations.sort(key=lambda case: (case["name"].casefold(), case["id"]))
        source["citations"] = citations
        source["median_age"] = median([case["age"] for case in citations]) if citations else None
        sources.append(source)

    return {
        "term": term, "source_count": len(source_ids), "node_count": len(graph),
        "edge_count": manifest["binary_edges"], "sources": sources,
        "held_for_review": manifest.get("cases_needing_review", manifest.get("case_review_counts", {}).get("needs_review", 0)),
        "flagged_citations": sum(manifest["citation_review_counts"].values()),
        "method": manifest.get("input_method", "Harvard archive opinion-block citation links; see the term manifest for selection and exclusions."),
        "input_sha256": {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                         for name in ("cases.csv", "citations.csv", "manifest.json")},
    }


def build_explorer(data_dir, output_dir, assets_dir=None, report_path=None):
    """Discover complete term folders, validate them, then write a portable site."""
    folders = sorted((folder for folder in Path(data_dir).glob("term_*")
                      if folder.is_dir() and folder.name[5:].isdigit()), key=lambda folder: int(folder.name[5:]))
    if not folders:
        raise ValueError("No term folders found")
    payload = {"schema_version": 1, "terms": [export_term(folder) for folder in folders]}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = Path(assets_dir) if assets_dir else PROJECT_DIR / "web"
    for name in ("index.html", "style.css", "app.js"):
        shutil.copy2(assets_dir / name, output_dir / name)
    (output_dir / "data.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    report_path = Path(report_path) if report_path else PROJECT_DIR / "reports/citation_age_report.html"
    shutil.copy2(report_path, output_dir / "comparison-report.html")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_DIR / "data")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "web/dist")
    args = parser.parse_args()
    payload = build_explorer(args.data_dir, args.output_dir)
    print(f"Built explorer: {len(payload['terms'])} terms, {sum(t['source_count'] for t in payload['terms'])} source cases → {args.output_dir}")


if __name__ == "__main__":
    main()
