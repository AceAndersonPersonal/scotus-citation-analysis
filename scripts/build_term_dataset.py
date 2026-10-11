"""Resolve citations from staged official opinions and export reviewable term CSVs.

Network access is optional and limited to missing public reporter metadata.
Generated datasets remain in staging until explicitly published after review.
"""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from concurrent.futures import ThreadPoolExecutor

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts.collect_terms import (cite_key, eligible, fetch, normalize, official_rows,
                                  scdb_rows, sha256, write_json)

US = re.compile(r"\b(\d{1,3})\s+U\.\s*S\.\s+(\d+)\b")
UNPAGINATED = re.compile(r"\b(\d{1,3})\s+U\.\s*S\.\s+[_—–]{2,}")
NOM = re.compile(r"\b(\d+)\s+(Dall\.|Cranch|Wheat\.|Pet\.|How\.|Black|Wall\.)\s*(\d+)\b")
OFFSETS = {"Dall.": 0, "Cranch": 4, "Wheat.": 13, "Pet.": 25, "How.": 41, "Black": 65, "Wall.": 67}
CASE_FIELDS = ["case_id", "case_name", "date_filed", "is_source", "us_citation", "url", "term", "scdb_id", "issue_area", "decision_type"]
REVIEW_FIELDS = ["scdb_id", "case_id", "case_name", "status", "reason", "decision_type", "date_argument", "us_citation", "url"]
CITATION_FIELDS = ["source_case_id", "source_case_name", "citation_text", "reason", "context", "method"]


def references(text):
    for match in US.finditer(text):
        yield ":".join(match.groups()), match
    for match in NOM.finditer(text):
        yield f"{int(match[1]) + OFFSETS[match[2]]}:{match[3]}", match


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class Metadata:
    """Preserve published IDs and refuse unresolved or conflicting identities."""

    def __init__(self, project=PROJECT):
        self.project = project
        self.published = {}
        self.official = {}
        self.candidates = defaultdict(list)
        self.inputs = {}
        for path in (project / "data/term_2004/cases.csv", project / "data/term_2024/cases.csv"):
            self.inputs[str(path.relative_to(project))] = sha256(path)
            for row in read_csv(path):
                key = cite_key(row["us_citation"])
                if key is None:
                    continue
                previous = self.published.get(key)
                if previous and previous["case_id"] != row["case_id"]:
                    raise ValueError(f"Published identity conflict: {key}")
                self.published[key] = row
        for row in scdb_rows(project):
            key = cite_key(row["usCite"])
            if key:
                self.candidates[key].append({"case_name": row["caseName"],
                    "date_filed": datetime.strptime(row["dateDecision"], "%m/%d/%Y").date().isoformat(),
                    "identity": row["caseId"], "provenance": "scdb_2025_01",
                    "url": "https://supreme.justia.com/cases/federal/us/" + key.replace(":", "/") + "/"})
        paths = list((project / "data/term_2024/raw/indexes").glob("official-*.html"))
        paths += list((project / "data/staging").glob("term_*/raw/official-index.html"))
        paths.append(project / "data/term_2024/raw/official2024.html")
        for path in sorted(set(paths)):
            if not path.exists():
                continue
            self.inputs[str(path.relative_to(project))] = sha256(path)
            for row in official_rows(path.read_text(encoding="utf-8-sig"), required=False):
                if row["key"]:
                    self.official[row["key"]] = {**row, "case_name": row["name"], "provenance": "official_opinion_index"}
        self.load_archive()
        self.build_name_index()

    def build_name_index(self):
        self.names = defaultdict(set)
        for records in (self.published, self.official):
            for key, record in records.items():
                self.names[key].add(self.name_key(record["case_name"]))
        for key, records in self.candidates.items():
            self.names[key].update(self.name_key(row["case_name"]) for row in records)

    @staticmethod
    def name_key(name):
        return re.sub(r"[^a-z0-9]", "", name.casefold())

    def named_reference(self, volume, prefix):
        """Require an exact full case-name suffix and a unique reporter volume."""
        prefix = self.name_key(prefix)
        hits = {key for key, names in self.names.items() if key.split(":")[0] == volume
                and any(len(name) > 8 and prefix.endswith(name) for name in names)}
        return next(iter(hits)) if len(hits) == 1 else None

    def load_archive(self):
        paths = list((self.project / "data/term_2024/raw/indexes").glob("cap-*.json"))
        paths += list((self.project / "data/reference_cache").glob("cap-*.json"))
        self.archive = defaultdict(dict)
        for path in sorted(paths):
            self.inputs[str(path.relative_to(self.project))] = sha256(path)
            for row in json.loads(path.read_text()):
                if row["court"]["id"] != 9009:
                    continue
                citation = next((c["cite"] for c in row["citations"] if c["type"] == "official"), "")
                key = cite_key(citation)
                if key:
                    self.archive[key][str(row["id"])] = {"case_name": row["name_abbreviation"],
                        "date_filed": row["decision_date"], "identity": str(row["id"]),
                        "url": f'https://cite.case.law/us/{key.split(":")[0]}/{row["first_page"]}/',
                        "provenance": "harvard_cap_metadata"}

    def resolve(self, key):
        if key in self.published:
            record = {**self.published[key], "provenance": "existing_published_case_registry"}
            if record["url"].rstrip("/") == "https://scdb.la.psu.edu":
                record["url"] = "https://supreme.justia.com/cases/federal/us/" + key.replace(":", "/") + "/"
            return record, None
        if key in self.official:
            return self.official[key], None
        caps = self.archive[key]
        if len(caps) > 1:
            return None, "ambiguous_target"
        if caps:
            record = next(iter(caps.values()))
            if any(row["date_filed"] != record["date_filed"] for row in self.candidates[key]):
                return None, "conflicting_target_dates"
            return record, None
        rows = {row["identity"]: row for row in self.candidates[key]}
        if len(rows) > 1:
            return None, "ambiguous_target"
        if not rows:
            return None, "unresolved_target"
        return next(iter(rows.values())), None

    def case_id(self, key):
        return self.published.get(key, {}).get("case_id", "us:" + key)

    def acquire_missing(self, keys):
        volumes = sorted({int(key.split(":")[0]) for key in keys
                          if self.resolve(key)[1] and int(key.split(":")[0]) < 580})
        failures = []
        def download(volume):
            existing = self.project / f"data/term_2024/raw/indexes/cap-{volume}.json"
            if existing.exists():
                return
            path = self.project / f"data/reference_cache/cap-{volume}.json"
            try:
                fetch(f"https://static.case.law/us/{volume}/CasesMetadata.json", path)
            except Exception as error:
                failures.append({"volume": volume, "error": str(error)})
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(download, volumes))
        self.load_archive()
        return failures


def build(term, metadata, project=PROJECT):
    root = project / f"data/staging/term_{term}"
    raw = root / "raw"
    roster = json.loads((raw / "term-roster.json").read_text())
    overrides_path = project / "data/source_overrides.json"
    overrides = json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
    nodes, edges, sources = {}, set(), {}
    case_review, reviews, evidence, audit = [], [], [], []
    for item in roster:
        row, official = item["scdb"], item["official"]
        sid = row["caseId"]
        key = official["key"] if official else cite_key(row["usCite"])
        cid = metadata.case_id(key) if key else ""
        name = official["name"] if official else row["caseName"]
        status, reason = "included", "Argued SCDB type 1 or 6; complete majority/per-curiam section selected automatically."
        path = raw / "text" / f"{sid}-sections.json"
        section = json.loads(path.read_text()) if path.exists() else None
        if not eligible(row):
            status, reason = "excluded", "No oral argument or outside SCDB decision types 1 and 6."
        elif not official:
            status, reason = "needs_review", "No unique official-index match."
        elif not key:
            status, reason = "needs_review", "No paginated U.S. Reports identity."
        elif official.get("date_discrepancy") and overrides.get(sid, {}).get("date_discrepancy") != official["date_discrepancy"]:
            status, reason = "needs_review", "SCDB/official decision-date discrepancy: " + json.dumps(official["date_discrepancy"])
        elif section is None:
            status, reason = "needs_review", "PDF download or text extraction unavailable."
        elif section["problem"]:
            status, reason = "needs_review", section["problem"]
        elif not section["majority_text"].strip():
            status, reason = "needs_review", "Empty selected opinion text."
        if status == "included" and official.get("date_discrepancy"):
            reason += " " + overrides[sid]["reason"]
        case_review.append(dict(zip(REVIEW_FIELDS, [sid, cid, name, status, reason, row["decisionType"], row["dateArgument"],
                           official["citation"] if official else row["usCite"], official["url"] if official else ""])))
        if status != "included":
            continue
        source = dict(zip(CASE_FIELDS, [cid, name, official["date_filed"], "True", key.replace(":", " U.S. "),
                     official["url"], str(term), sid, row["issueArea"], row["decisionType"]]))
        if cid in sources:
            raise ValueError(f"Duplicate source opinion {cid}; consolidated record needs review")
        sources[cid] = source
        nodes[cid] = source
        for method, text in (("page_order", section["majority_text"]), ("body_flow", section["body_text"])):
            found = list(references(text))
            for match in UNPAGINATED.finditer(text):
                target_key = metadata.named_reference(match[1], text[max(0, match.start() - 250):match.start()])
                if target_key:
                    found.append((target_key, match))
                else:
                    reviews.append(dict(zip(CITATION_FIELDS, [cid, name, normalize(match[0]), "unpaginated_citation_needs_review",
                        normalize(text[max(0, match.start() - 180):match.end() + 120]), method])))
            for target_key, match in found:
                if target_key == key:
                    continue
                context = normalize(text[max(0, match.start() - 200):match.end() + 120])
                target, problem = metadata.resolve(target_key)
                if target:
                    precision = min(len(target["date_filed"]), len(source["date_filed"]))
                    if target["date_filed"][:precision] > source["date_filed"][:precision]:
                        problem = "target_date_after_source"
                if problem:
                    reviews.append(dict(zip(CITATION_FIELDS, [cid, name, target_key.replace(":", " U.S. "), problem, context, method])))
                    continue
                tid = metadata.case_id(target_key)
                if tid not in nodes:
                    nodes[tid] = dict(zip(CASE_FIELDS, [tid, target["case_name"], target["date_filed"], "False",
                                      target_key.replace(":", " U.S. "), target["url"], "", "", "", ""]))
                edges.add((cid, tid))
                evidence.append({"citing_case": cid, "cited_case": tid, "source_scdb_id": sid,
                                 "citation_text": normalize(match[0]), "canonical_citation": target_key.replace(":", " U.S. "),
                                 "extraction_stream": method, "character_offset": match.start(), "context": context,
                                 "target_metadata_source": target["provenance"],
                                 "resolution_method": "exact_case_name_and_volume" if UNPAGINATED.fullmatch(match[0]) else "full_reporter_citation"})
        audit.append({"scdb_id": sid, "case_id": cid, "majority_start": section["start"], "next_section": section["end_preview"],
                      "text_sha256": section["text_sha256"], "pdf_sha256": section["pdf_sha256"],
                      "majority_characters": len(section["majority_text"]), "body_characters": len(section["body_text"]), "pdf_page_range": section["pdf_page_range"],
                      "join_statements": section.get("join_statements", []), "review_status": "automated_boundary_checks"})
    nodes.update(sources)
    reviews = list({(row["source_case_id"], row["citation_text"], row["reason"], row["context"]): row for row in reviews}.values())
    write_csv(root / "cases.csv", CASE_FIELDS, sorted(nodes.values(), key=lambda row: row["case_id"]))
    write_csv(root / "citations.csv", ["citing_case", "cited_case"], [{"citing_case": a, "cited_case": b} for a, b in sorted(edges)])
    write_csv(root / "case_review.csv", REVIEW_FIELDS, case_review)
    write_csv(root / "citation_review.csv", CITATION_FIELDS, reviews)
    write_json(root / "edge_evidence.json", evidence)
    write_json(root / "opinion_audit.json", audit)
    manifest = {"term": term, "built_at": datetime.now(timezone.utc).isoformat(), "scdb_release": "2025_01",
        "scdb_term_cases": len(roster), "eligible_source_cases": sum(eligible(item["scdb"]) for item in roster),
        "included_source_cases": len(sources), "case_review_counts": dict(Counter(row["status"] for row in case_review)),
        "nodes": len(nodes), "binary_edges": len(edges), "citation_review_counts": dict(Counter(row["reason"] for row in reviews)),
        "sources_without_edges": [row["case_name"] for cid, row in sources.items() if not any(a == cid for a, _ in edges)],
        "review_status": "preliminary; automated checks with separately recorded targeted audits",
        "scope": "SCDB argued types 1 and 6; complete majority/per-curiam sections; mixed opinions and unresolved source records held for review.",
        "input_method": "Official Court PDFs; pypdf page-order text and supplemental body-font stream; common collector v1.",
        "limitations": ["Selected subset; whole opinions with mixed majority/plurality sections are held out.",
            "Full U.S. Reports/nominative references and uniquely matched full-name unpaginated references; short forms alone do not establish identities.",
            "Unresolved references are omitted and logged; targeted audits do not establish complete recall.",
            "2004 uses archive links and 2024 uses an earlier PDF extraction implementation; method differences remain.",
            "Citation links include procedural references and do not imply agreement or importance."],
        "source_urls": [f"https://www.supremecourt.gov/opinions/slipopinion/{str(term)[-2:]}",
                        "https://scdb.la.psu.edu/data/2025-release-01/", "https://static.case.law/"],
        "input_sha256": {"source_overrides.json": sha256(overrides_path) if overrides_path.exists() else None, "scdb.zip": sha256(project / "data/term_2004/raw/scdb.zip"),
                         "official-index.html": sha256(raw / "official-index.html"), "term-roster.json": sha256(raw / "term-roster.json")},
        "unpaginated_links_resolved": len({(row["citing_case"], row["cited_case"]) for row in evidence if row["resolution_method"] == "exact_case_name_and_volume"}),
        "script_sha256": {name: sha256(project / "scripts" / name) for name in ("collect_terms.py", "build_term_dataset.py")},
        "id_policy": "Reuse published case IDs on exact reporter-citation matches; new IDs use us:volume:first_page."}
    write_json(root / "manifest.json", manifest)
    write_json(root / "metadata_inputs.json", metadata.inputs)
    assert {(row["citing_case"], row["cited_case"]) for row in evidence} == edges
    assert all(a in sources and b in nodes and a != b for a, b in edges)
    print(json.dumps({k: manifest[k] for k in ("term", "eligible_source_cases", "included_source_cases", "binary_edges", "case_review_counts", "citation_review_counts")}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terms", type=int, nargs="+", required=True)
    parser.add_argument("--fetch-metadata", action="store_true")
    args = parser.parse_args()
    metadata = Metadata()
    if args.fetch_metadata:
        keys = set()
        for term in args.terms:
            for path in (PROJECT / f"data/staging/term_{term}/raw/text").glob("*-sections.json"):
                section = json.loads(path.read_text())
                if not section["problem"]:
                    for text in (section["majority_text"], section["body_text"]):
                        keys.update(key for key, _ in references(text))
        failures = metadata.acquire_missing(keys)
        write_json(PROJECT / "data/reference_cache/download_review.json", failures)
        if failures:
            print("Metadata downloads held:", failures, flush=True)
    for term in args.terms:
        build(term, metadata)


if __name__ == "__main__":
    main()
