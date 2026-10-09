"""Download a small CourtListener SCOTUS sample; graph analysis is left to you.

Run --setup-token once in your own Terminal, then run this script normally.
Only Python's standard library is needed. Reruns reuse cached API responses.
"""

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.courtlistener.com/api/rest/v4/"
TOKEN_FILE = ROOT / ".courtlistener-token"
OUTPUT = ROOT / "data" / "sample_3_cases"


def api_id(value):
    return int(str(value).rstrip("/").split("/")[-1])


def term_start(year):
    first = date(year, 10, 1)
    return date(year, 10, 1 + (-first.weekday()) % 7).isoformat()


class Client:
    def __init__(self, token):
        self.token = token
        self.cache = ROOT / "data" / "raw"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.history = self.cache / "request_times.json"
        self.times = json.loads(self.history.read_text()) if self.history.exists() else []
        self.calls = 0

    def get(self, url):
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc != "www.courtlistener.com"
                or not parsed.path.startswith("/api/rest/v4/")):
            raise RuntimeError("Unexpected API URL; refusing to send the token.")
        path = self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        if path.exists():
            return json.loads(path.read_text())["response"]
        now = time.time()
        self.times = [t for t in self.times if now - t < 86400]
        if self.calls >= 35 or len(self.times) >= 120:
            raise RuntimeError("Request budget reached. Rerun later; cached progress is saved.")
        if sum(now - t < 3600 for t in self.times) >= 45:
            raise RuntimeError("Hourly request budget reached. Rerun in an hour.")
        if self.times:
            time.sleep(max(0, 13 - (now - self.times[-1])))
        self.times.append(time.time())
        self.history.write_text(json.dumps(self.times))
        self.calls += 1
        request = Request(url, headers={"Authorization": "Token " + self.token,
                                       "Accept": "application/json"})
        try:
            with urlopen(request, timeout=45) as response:
                data = json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"CourtListener returned HTTP {error.code}. "
                               "For 401/403 check account access; for 429 rerun later.") from None
        path.write_text(json.dumps({"url": url,
                                   "retrieved_at": datetime.now(timezone.utc).isoformat(),
                                   "response": data}, indent=2))
        print(f"Downloaded API response {self.calls}; saved locally.", flush=True)
        return data


def write_csv(name, fields, rows):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT / (name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(OUTPUT / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup-token", action="store_true")
    parser.add_argument("--term", type=int, choices=[2004], default=2004,
                        help="This starter sample covers three named cases in the 2004 term")
    parser.add_argument("--limit", type=int, default=3, help="Number of source cases (default: 3)")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing nonempty CSV files")
    args = parser.parse_args()
    if args.setup_token:
        token = getpass.getpass("Paste CourtListener API token (hidden), then press Return: ").strip()
        if not token or any(c.isspace() for c in token):
            raise RuntimeError("Token must be nonempty and contain no whitespace.")
        descriptor = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(token + "\n")
        print("Token saved privately. Tell Codex setup is complete; do not share the token.")
        return
    if not 1 <= args.limit <= 10:
        raise RuntimeError("Choose a sample size between 1 and 10.")
    for name in ["cases.csv", "citations.csv"]:
        path = OUTPUT / name
        if path.exists() and path.stat().st_size and not args.overwrite:
            raise RuntimeError(f"{name} already has data. Use --overwrite only to replace it.")
    token = os.environ.get("COURTLISTENER_API_TOKEN", "").strip()
    if not token and TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
    if not token:
        raise RuntimeError("First run this script with --setup-token in your Terminal.")
    client = Client(token)
    end = (date.fromisoformat(term_start(args.term + 1)) - timedelta(days=1)).isoformat()
    query = {"court": "scotus", "type": "o", "order_by": "dateFiled asc",
             "q": f"dateFiled:[{term_start(args.term)} TO {end}] AND caseName:(Leocal OR Koons OR Kirby)"}
    url = BASE + "search/?" + urlencode(query)
    sources = []
    while url and len(sources) < args.limit:
        page = client.get(url)
        for result in page["results"][:args.limit - len(sources)]:
            if result["court_id"] != "scotus":
                raise RuntimeError("Search returned a non-SCOTUS source.")
            cluster = client.get(BASE + f"clusters/{result['cluster_id']}/?" + urlencode({
                "fields": "id,case_name,date_filed,docket,sub_opinions"}))
            if not term_start(args.term) <= cluster["date_filed"] <= end:
                raise RuntimeError("Source falls outside the requested term.")
            sources.append(cluster)
        url = page.get("next")
    if not sources:
        raise RuntimeError("No source cases returned; CSV files were left unchanged.")
    clusters = {c["id"]: c for c in sources}
    source_ids = set(clusters)
    edges = set()
    evidence = []
    pending = []
    for source in sources:
        print(f"Collecting citations: {source['case_name']}", flush=True)
        for opinion_url in source["sub_opinions"]:
            opinion = client.get(opinion_url + "?fields=id,type,opinions_cited")
            if "opinions_cited" not in opinion:
                raise RuntimeError("API response lacks citation data; refusing to treat it as empty.")
            for cited_url in opinion["opinions_cited"]:
                pending.append((source["id"], opinion["id"], opinion.get("type"), api_id(cited_url)))
    target_ids = sorted({item[3] for item in pending})
    resolved = {}
    for offset in range(0, len(target_ids), 10):
        batch = set(target_ids[offset:offset + 10])
        query = {"type": "o", "q": "id:(" + " OR ".join(map(str, sorted(batch))) + ")"}
        for status in ["Published", "Unpublished", "Errata", "Separate", "In-chambers", "Relating-to", "Unknown"]:
            query["stat_" + status] = "on"
        url = BASE + "search/?" + urlencode(query)
        while url:
            page = client.get(url)
            for result in page["results"]:
                ids = set(result.get("sibling_ids", []))
                ids.update(op["id"] for op in result.get("opinions", []))
                for opinion_id in batch & ids:
                    if result["court_id"] != "scotus":
                        resolved[opinion_id] = None
                    else:
                        cid = result["cluster_id"]
                        resolved[opinion_id] = cid
                        clusters.setdefault(cid, {"id": cid, "case_name": result["caseName"],
                                                  "date_filed": result["dateFiled"]})
            url = page.get("next")
    # Search indexes can lag the database. Resolve missing opinions directly.
    for opinion_id in target_ids:
        if opinion_id in resolved:
            continue
        target = client.get(BASE + f"opinions/{opinion_id}/?fields=id,cluster")
        cid = api_id(target["cluster"])
        if cid not in clusters:
            cluster = client.get(BASE + f"clusters/{cid}/?" + urlencode({
                "fields": "id,case_name,date_filed,docket,sub_opinions"}))
            docket = client.get(cluster["docket"] + "?fields=court")
            if str(docket["court"]).rstrip("/").split("/")[-1] != "scotus":
                resolved[opinion_id] = None
                continue
            clusters[cid] = cluster
        resolved[opinion_id] = cid
    for source_id, opinion_id, opinion_type, target_id in pending:
        cid = resolved[target_id]
        if cid is None or source_id == cid:
            continue
        edges.add((source_id, cid))
        evidence.append({"citing_case": source_id, "cited_case": cid,
                         "citing_opinion": opinion_id, "cited_opinion": target_id,
                         "citing_opinion_type": opinion_type})
    rows = [{"case_id": cid, "case_name": c["case_name"], "date_filed": c["date_filed"],
             "is_sample_source": cid in source_ids,
             "url": f"https://www.courtlistener.com/opinion/{cid}/"}
            for cid, c in sorted(clusters.items())]
    write_csv("cases.csv", ["case_id", "case_name", "date_filed", "is_sample_source", "url"], rows)
    write_csv("citations.csv", ["citing_case", "cited_case"],
              [{"citing_case": a, "cited_case": b} for a, b in sorted(edges)])
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "term": args.term,
                "source_case_ids": sorted(source_ids), "cases": len(rows), "edges": len(edges),
                "scope": "Illustrative 2004-term sample selected by names Leocal, Koons, and Kirby; not a representative or complete term. "
                         "Includes all available opinion types within each source cluster. "
                         "Only resolved citations to SCOTUS cases; distinct case pairs, no self-edges. "
                         "Cited-only nodes have not had their outgoing citations collected.",
                "opinion_level_evidence": evidence}
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Saved {len(rows)} cases and {len(edges)} citation edges from {len(sources)} source cases.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        raise SystemExit(str(error)) from None
