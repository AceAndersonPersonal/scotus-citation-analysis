"""Record reproducible boundary and citation spot checks for staged terms.

These targeted checks exercise known layouts and edge cases. They are not
random samples, manual full-opinion audits, or estimates of extraction recall.
"""

import argparse
import csv
import json
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.collect_terms import normalize, select_majority, write_json
from scripts.build_term_dataset import cite_key, references

SAMPLES = {2020: ["2020-001", "2020-003", "2020-028"],
           2021: ["2021-002", "2021-030", "2021-055"],
           2022: ["2022-027", "2022-047", "2022-050"],
           2023: ["2023-015", "2023-048", "2023-060"]}
AUTHORS = {"R": "Roberts", "T": "Thomas", "A": "Alito", "B": "Breyer", "SS": "Sotomayor",
           "EK": "Kagan", "NG": "Gorsuch", "BK": "Kavanaugh", "AB": "Barrett", "KJ": "Jackson", "PC": "Per Curiam"}


def audit(term):
    root = PROJECT / f"data/staging/term_{term}"
    cases = list(csv.DictReader((root / "cases.csv").open()))
    by_id = {row["case_id"]: row for row in cases}
    sources = {row["scdb_id"]: row for row in cases if row["is_source"] == "True"}
    roster = {item["scdb"]["caseId"]: item for item in json.loads((root / "raw/term-roster.json").read_text())}
    edges = {(r["citing_case"], r["cited_case"]) for r in csv.DictReader((root / "citations.csv").open())}
    evidence = json.loads((root / "edge_evidence.json").read_text())
    source_hashes = set()
    for sid, row in sources.items():
        section = json.loads((root / "raw/text" / f"{sid}-sections.json").read_text())
        assert not section["problem"], sid
        assert section["text_sha256"] not in source_hashes, f"Duplicate selected text: {sid}"
        source_hashes.add(section["text_sha256"])
        expected_author = AUTHORS[roster[sid]["official"]["author"]]
        assert expected_author in section["start"], (sid, expected_author, section["start"])
        assert not (section["end_preview"] is None and any(re.search(r"concurring|dissenting|^Opinion of (?!the Court)", h) for h in section["headers"])), sid
        assert re.search(r"so ordered|[Aa]ff[irﬃ]*r?med|[Rr]eversed|[Vv]acated|[Dd]ismissed", normalize(re.split(r"(?m)^APPENDI(?:X|CES)\b", section["majority_text"])[0])[-4500:]), sid
    records = []
    for sid in SAMPLES[term]:
        row = sources[sid]
        section = json.loads((root / "raw/text" / f"{sid}-sections.json").read_text())
        source_evidence = [r for r in evidence if r["citing_case"] == row["case_id"]]
        examples = []
        for item in source_evidence[:3]:
            text = section["majority_text"] if item["extraction_stream"] == "page_order" else section["body_text"]
            offset = item["character_offset"]
            assert normalize(text[offset:offset + 80]).startswith(item["citation_text"]), sid
            assert (item["citing_case"], item["cited_case"]) in edges
            examples.append({"citation": item["canonical_citation"], "context": item["context"], "target": by_id[item["cited_case"]]["case_name"]})
        record = {"scdb_id": sid, "case_name": row["case_name"], "pdf_url": row["url"],
                  "pdf_sha256": section["pdf_sha256"], "text_sha256": section["text_sha256"],
                  "pdf_page_range": section["pdf_page_range"], "selected_start": section["start"],
                  "selected_tail": normalize(section["majority_text"])[-350:], "next_section": section["end_preview"],
                  "links": sum(a == row["case_id"] for a, b in edges), "citation_spot_checks": examples,
                  "check_type": "automated targeted boundary and evidence checks"}
        records.append(record)
    result = {"term": term, "selection_rule": "Purposive cases covering report-part PDFs, corrected metadata, narrative dissent references, major opinions, and zero-link decisions.",
              "all_sources_checked": len(sources), "checks": ["Unique selected texts", "Author agrees with official index", "Separate-opinion boundary when separate headers exist", "Disposition present near selected end", "Sample citation evidence offsets and graph membership"],
              "limitations": "Automated targeted checks; no claim of manual full-opinion review or measured citation recall. Footnotes spanning section boundaries and unnamed short forms may be missed.",
              "samples": records}
    write_json(root / "targeted_checks.json", result)
    print(f"Term {term}: {len(sources)} source boundary checks and {len(records)} targeted evidence records passed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terms", type=int, nargs="+", required=True)
    for term in parser.parse_args().terms:
        audit(term)


if __name__ == "__main__":
    main()
