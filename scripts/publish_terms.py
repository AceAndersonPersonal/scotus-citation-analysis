"""Promote checked staging exports; raw opinions remain local caches."""

import argparse
import csv
import json
from pathlib import Path
import shutil
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.build_explorer import export_term

FILES = ("cases.csv", "citations.csv", "manifest.json", "case_review.csv", "citation_review.csv",
         "edge_evidence.json", "opinion_audit.json", "targeted_checks.json", "metadata_inputs.json")


def publish(term, replace=False):
    source = PROJECT / f"data/staging/term_{term}"
    destination = PROJECT / f"data/term_{term}"
    for name in FILES:
        if not (source / name).exists():
            raise ValueError(f"Missing checked export: {source / name}")
    payload = export_term(source)
    checks = json.loads((source / "targeted_checks.json").read_text())
    audits = {r["scdb_id"]: r for r in json.loads((source / "opinion_audit.json").read_text())}
    if checks["all_sources_checked"] != payload["source_count"]:
        raise ValueError("Boundary checks are stale")
    for sample in checks["samples"]:
        audit = audits[sample["scdb_id"]]
        if any(sample[key] != audit[key] for key in ("text_sha256", "pdf_sha256")):
            raise ValueError("Targeted checks are stale")
    pairs = {(r["citing_case"], r["cited_case"]) for r in csv.DictReader((source / "citations.csv").open())}
    evidence = json.loads((source / "edge_evidence.json").read_text())
    if pairs != {(r["citing_case"], r["cited_case"]) for r in evidence}:
        raise ValueError("Edges differ from recorded evidence")
    if destination.exists() and not replace:
        raise ValueError(f"{destination} exists; use --replace only after reviewing the changes")
    destination.mkdir(exist_ok=True)
    for name in FILES:
        shutil.copyfile(source / name, destination / name)
    print(f"Term {term}: published {payload['source_count']} sources and {payload['edge_count']} links locally")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terms", type=int, nargs="+", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    for term in args.terms:
        publish(term, args.replace)


if __name__ == "__main__":
    main()
