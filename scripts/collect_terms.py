"""Acquire and prepare additional October terms without modifying published data.

Raw downloads are cached under data/staging/term_YYYY/raw. Publication is a
separate step after extraction, structural checks, and recorded opinion audits.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import datetime, timezone
import hashlib
from html import unescape
import io
import json
from pathlib import Path
import re
import shutil
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
USER_AGENT = "SCOTUS citation research (educational; cached requests)"
US = re.compile(r"\b(\d{1,3})\s+U\.\s*S\.\s+(\d+)\b")


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def cite_key(text):
    match = US.search(text)
    return ":".join(match.groups()) if match else None


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url, path, pdf=False):
    """Cache successful downloads atomically; retry transient failures."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=60) as response:
                content = response.read()
            if pdf and not content.startswith(b"%PDF"):
                raise ValueError(f"Expected PDF: {url}")
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_bytes(content)
            temporary.replace(path)
            return
        except Exception as error:
            if isinstance(error, HTTPError) and error.code in (400, 401, 403, 404):
                raise
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def scdb_rows(project=PROJECT):
    path = project / "data/term_2004/raw/scdb.zip"
    with zipfile.ZipFile(path) as archive:
        name = next(name for name in archive.namelist() if name.endswith("_caseCentered_Citation.csv"))
        return list(csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig"))))


def official_rows(text, required=True):
    rows = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", text, re.S | re.I):
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.S | re.I)
        if len(cells) != 6:
            continue
        link = re.search(r'''href=['"](/opinions/[^'"]+\.pdf)''', cells[3])
        if not link:
            continue
        values = [normalize(unescape(re.sub(r"<[^>]*>", "", cell))) for cell in cells]
        item = dict(zip(("number", "date", "docket", "name", "author", "citation"), values))
        item["url"] = "https://www.supremecourt.gov" + link[1]
        item["date_filed"] = datetime.strptime(item["date"], "%m/%d/%y").date().isoformat()
        item["key"] = cite_key(item["citation"])
        rows.append(item)
    if not rows and required:
        raise ValueError("No official opinion rows; index format needs review")
    return rows


def eligible(row):
    return bool(row["dateArgument"]) and row["decisionType"] in {"1", "6"}


def normalize_docket(value):
    value = value.replace("–", "-").strip()
    original = re.fullmatch(r"22O(\d+)", value)
    if original:
        return "original:" + str(int(original[1]))
    original = re.fullmatch(r"(\d+),?\s*Orig\.", value)
    if original:
        return "original:" + str(int(original[1]))
    return re.sub(r"\s*\([^)]*\)$", "", value)


def match_official(row, index):
    date = datetime.strptime(row["dateDecision"], "%m/%d/%Y").date().isoformat()
    docket = normalize_docket(row["docket"])
    hits = [item for item in index if item["date_filed"] == date
            and normalize_docket(item["docket"]) == docket]
    if len(hits) != 1 and cite_key(row["usCite"]):
        hits = [item for item in index if item["date_filed"] == date and item["key"] == cite_key(row["usCite"])]
    # Preserve a discrepancy for review instead of silently correcting SCDB.
    if not hits:
        docket_hits = [item for item in index if normalize_docket(item["docket"]) == docket]
        if len(docket_hits) == 1:
            return {**docket_hits[0], "date_discrepancy": {"scdb": date, "official": docket_hits[0]["date_filed"]}}
    return hits[0] if len(hits) == 1 else None


def acquire(term, project=PROJECT):
    root = project / f"data/staging/term_{term}"
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    cached = project / f"data/term_2024/raw/indexes/official-{term}.html"
    index_path = raw / "official-index.html"
    if not index_path.exists() and cached.exists():
        shutil.copyfile(cached, index_path)
    fetch(f"https://www.supremecourt.gov/opinions/slipopinion/{str(term)[-2:]}", index_path)
    index = official_rows(index_path.read_text(encoding="utf-8-sig"))
    roster = [row for row in scdb_rows(project) if row["term"] == str(term)]
    if not roster:
        raise ValueError(f"Term {term} absent from cached SCDB release")
    matched = [{"scdb": row, "official": match_official(row, index)} for row in roster]
    write_json(raw / "official-index.json", index)
    write_json(raw / "term-roster.json", matched)
    candidates = [item for item in matched if eligible(item["scdb"]) and item["official"]]
    failures = []
    def download(item):
        sid = item["scdb"]["caseId"]
        path = raw / "pdf" / f"{sid}.pdf"
        fetch(item["official"]["url"], path, pdf=True)
        return {"scdb_id": sid, "url": item["official"]["url"], "sha256": sha256(path), "bytes": path.stat().st_size}
    records = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(download, item): item for item in candidates}
        for future in as_completed(futures):
            try:
                records.append(future.result())
            except Exception as error:
                failures.append({"scdb_id": futures[future]["scdb"]["caseId"], "error": str(error)})
            if (len(records) + len(failures)) % 10 == 0:
                print(f"Term {term}: {len(records)}/{len(candidates)} PDFs cached", flush=True)
    write_json(raw / "downloads.json", {"cached_at": datetime.now(timezone.utc).isoformat(),
               "files": sorted(records, key=lambda row: row["scdb_id"]), "failures": failures})
    missing = [item["scdb"]["caseName"] for item in matched if eligible(item["scdb"]) and not item["official"]]
    print(f"Term {term}: {len(records)} PDFs, {len(missing)} unmatched candidate cases, {len(failures)} download failures", flush=True)
    if missing:
        print("Unmatched:", missing, flush=True)
    if not records:
        raise RuntimeError("No PDFs available; rerun acquisition after resolving download failures")
    if failures:
        print("Unavailable PDFs remain held for review; rerun acquisition to retry.", flush=True)
    return root



AUTHOR = r"(?:Chief\s+Justice|Justice)\s+[A-Za-z’'‐-]+"
START = re.compile(r"(?m)^\s*" + AUTHOR + r"\s+(?:delivered|announced)\s+(?:the|an)\s+opinion[^.]*\.", re.I)
SEPARATE = re.compile(
    r"(?m)^\s*" + AUTHOR + r"\s*,\s*(?:with whom\s+[^.]{0,400}?,\s*)?"
    r"(?:(?:No\.\s*\d+[–-]\d+|concurring|dissenting|in|parts?|the|judgment|and|as|to|from|[IVX]+)\b[\s,]*)+\.", re.I)

HEADER = re.compile(r"^(?:Opinion of |Per Curiam$|Syllabus$|Appendix to opinion|[A-Z][a-z]+, (?:J\.|C\. J\.),|Reporter[’']s Note)")


def strip_page_header(text):
    lines = text.replace("Page Proof Pending Publication", "").strip().splitlines()
    for position, line in enumerate(lines[:10]):
        if HEADER.search(line.strip()):
            return "\n".join(lines[position + 1:]), line.strip()
    return "\n".join(lines), ""


def select_majority(pages):
    """Select one complete majority/per-curiam section; flag partial majorities.

    This is a conservative layout heuristic, not a general legal opinion parser.
    Stored starts, ends, and headers make every selection inspectable.
    """
    stripped = [strip_page_header(page) for page in pages]
    full = "\n".join(re.sub(r"(?<=[A-Za-z])[-\u00ad]\s*\n\s*(?=[A-Za-z])", "", text) for text, header in stripped)
    starts = [match for match in (START.search(full), re.search(r"(?m)^\s*Per Curiam\.", full)) if match]
    start = min(starts, key=lambda match: match.start()) if starts else None
    if start is None:
        return {"majority_text": "", "problem": "majority_start_not_found", "headers": [h for _, h in stripped]}
    opening = normalize(start[0])
    problem = None
    if not re.fullmatch(AUTHOR + r" delivered the opinion of the Court\.", opening, re.I) and opening != "Per Curiam.":
        problem = "mixed_or_plurality_opening"
    # The syllabus sometimes records the majority qualification only in its join statement.
    prefatory = full[:start.start()]
    joins = re.findall(r"[A-Z][a-z]+, (?:J\.|C\. J\.), (?:delivered|announced)[\s\S]{0,850}", prefatory)
    for join in joins:
        clause = normalize(join).split("in which", 1)[0]
        if re.search(r"except|with respect|as to|judgment", clause, re.I):
            problem = "mixed_or_plurality_join_statement"
    ending = SEPARATE.search(full, start.end())
    stop = ending.start() if ending else len(full)
    tail = full[start.start():stop]
    # Some PDFs append a revision notice or a fresh copy after the opinion.
    revision = tail.find("The attached opinion has been revised")
    if revision >= 0:
        tail = tail[:revision]
    return {"majority_text": tail, "problem": problem, "start": opening,
            "end_preview": full[stop:stop + 250] if ending else None,
            "headers": [h for _, h in stripped], "join_statements": joins,
            "text_sha256": hashlib.sha256(tail.encode()).hexdigest()}



def printed_page(text):
    lines = text.replace("Page Proof Pending Publication", "").strip().splitlines()
    if not lines:
        return None
    line = lines[0].strip()
    if line == "CASES ADJUDGED":
        return 1
    if line.isdigit() and not any("PRELIMINARY PRINT" in value for value in lines[:8]):
        return int(line)
    if line.startswith("Cite as:"):
        match = re.search(r"\)\s+(\d+)\s*$", line)
    else:
        match = re.match(r"^(\d+)\s*[A-Z]", line) or re.search(r"\s(\d+)\s*$", line)
    return int(match[1]) if match else None


def case_page_range(pages, key, index):
    """Some official links point to a whole report part, containing many cases."""
    volume, first = map(int, key.split(":"))
    later = [int(row["key"].split(":")[1]) for row in index if row["key"]
             and int(row["key"].split(":")[0]) == volume and int(row["key"].split(":")[1]) > first]
    following = min(later) if later else None
    starts = [i for i, page in enumerate(pages) if printed_page(page) == first]
    if len(starts) != 1:
        raise ValueError(f"Cannot uniquely locate printed start page {key}")
    begin = starts[0]
    end = len(pages)
    for i in range(begin + 1, len(pages)):
        number = printed_page(pages[i])
        if number is not None and ((following is not None and number >= following) or number < first):
            end = i
            break
    return begin, end


def extract(term, project=PROJECT):
    from pypdf import PdfReader
    raw = project / f"data/staging/term_{term}/raw"
    roster = json.loads((raw / "term-roster.json").read_text())
    reviews = []
    index = json.loads((raw / "official-index.json").read_text())
    pdf_streams = {}
    for item in roster:
        row = item["scdb"]
        if not eligible(row) or not item["official"]:
            continue
        sid = row["caseId"]
        path = raw / "pdf" / f"{sid}.pdf"
        if not path.exists():
            continue
        text_path = raw / "text" / f"{sid}.json"
        digest = sha256(path)
        cached = json.loads(text_path.read_text()) if text_path.exists() else {}
        if cached.get("extractor_version") == 2 and cached.get("pdf_sha256") == digest:
            streams = cached
        elif digest in pdf_streams:
            streams = pdf_streams[digest]
            write_json(text_path, streams)
        else:
            pages, body_pages = [], []
            for page in PdfReader(path).pages:
                body = []
                def visitor(text, cm, tm, font, size):
                    # Body text is roughly 11–12pt; footnotes are smaller.
                    # Font sizes must include PDF text and graphics transforms.
                    # The full page stream retains footnotes. This supplemental
                    # stream bridges references interrupted by footnotes.
                    effective_size = size * (tm[2] ** 2 + tm[3] ** 2) ** 0.5 * (cm[2] ** 2 + cm[3] ** 2) ** 0.5
                    if 10 < effective_size < 14:
                        body.append(text)
                pages.append(page.extract_text(visitor_text=visitor) or "")
                body_pages.append("".join(body))
            streams = {"extractor_version": 2, "pages": pages, "body_pages": body_pages, "pdf_sha256": digest}
            write_json(text_path, streams)
        pdf_streams[digest] = streams
        try:
            begin, end = case_page_range(streams["pages"], item["official"]["key"], index)
        except ValueError as error:
            reviews.append({"scdb_id": sid, "name": item["official"]["name"], "problem": str(error)})
            write_json(raw / "text" / f"{sid}-sections.json", {"majority_text": "", "body_text": "", "problem": str(error), "pdf_sha256": digest})
            continue
        section = select_majority(streams["pages"][begin:end])
        body = select_majority(streams["body_pages"][begin:end])
        section["pdf_page_range"] = [begin + 1, end]
        section["body_text"] = body["majority_text"] if body.get("start") == section.get("start") and not body["problem"] else ""
        section["pdf_sha256"] = streams["pdf_sha256"]
        write_json(raw / "text" / f"{sid}-sections.json", section)
        reviews.append({"scdb_id": sid, "name": item["official"]["name"], "problem": section["problem"],
                        "start": section.get("start"), "end_preview": section.get("end_preview"),
                        "characters": len(section["majority_text"]), "body_characters": len(section["body_text"])})
        if len(reviews) % 10 == 0:
            print(f"Term {term}: extracted {len(reviews)} opinions", flush=True)
    write_json(raw / "section-review.json", reviews)
    print(f"Term {term}: {len(reviews)} extracted; {sum(bool(r['problem']) for r in reviews)} section holds", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("acquire", "extract", "all"), default="all")
    parser.add_argument("--terms", type=int, nargs="+", required=True)
    args = parser.parse_args()
    for term in args.terms:
        if args.stage in ("acquire", "all"):
            acquire(term)
        if args.stage in ("extract", "all"):
            extract(term)


if __name__ == "__main__":
    main()
