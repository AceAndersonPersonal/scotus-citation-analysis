"""Describe annual citation patterns and overlap between consecutive terms.

Uses only committed CSVs and manifests. No API calls or plotting dependencies.
"""

import argparse
import csv
import hashlib
from html import escape
import json
from pathlib import Path
from statistics import mean

from compare_terms import opinion_metrics, summarize_opinions
from start import DATA_DIR, available_terms, load_term

PROJECT = Path(__file__).resolve().parent


def age_shares(graph, sources, years):
    """Give each age-bearing opinion equal weight in age-band percentages."""
    recent, old = [], []
    for source in sources:
        ages = [years[source] - years[target] for target in graph[source]]
        if any(age < 0 for age in ages):
            raise ValueError("Negative citation age")
        if ages:
            recent.append(sum(age <= 10 for age in ages) / len(ages))
            old.append(sum(age >= 50 for age in ages) / len(ages))
    return {"mean_share_0_to_10_years": mean(recent) if recent else None,
            "mean_share_50_plus_years": mean(old) if old else None}


def precedent_overlap(earlier, later):
    """Jaccard similarity of distinct cited-case sets, not of citation mentions."""
    union = earlier | later
    return {"shared_precedents": len(earlier & later), "union_precedents": len(union),
            "jaccard_share": len(earlier & later) / len(union) if union else None}


def collect_annual(data_dir=DATA_DIR):
    records, opinion_rows, overlaps = [], [], []
    previous_term, previous_targets = None, set()
    for term in available_terms(data_dir):
        folder = Path(data_dir) / f"term_{term}"
        manifest = json.loads((folder / "manifest.json").read_text())
        graph, names, years, sources = load_term(term, data_dir)
        opinions = opinion_metrics(graph, sources, years, names)
        summary = summarize_opinions(opinions)
        if summary["source_cases"] != manifest["included_source_cases"] or summary["citation_links"] != manifest["binary_edges"]:
            raise ValueError(f"Term {term}: manifest and graph disagree")
        held = manifest.get("cases_needing_review", manifest.get("case_review_counts", {}).get("needs_review", 0))
        records.append({"term": term, **summary, **age_shares(graph, sources, years),
                        "eligible_source_cases": manifest.get("eligible_source_cases", len(sources) + held),
                        "held_for_review": held,
                        "flagged_reference_entries": sum(manifest["citation_review_counts"].values()),
                        "method": manifest.get("input_method", "Harvard archive opinion-block citation links"),
                        "review_status": manifest.get("review_status", "Selected opinion audits; full recall not measured"),
                        "input_sha256": {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                                         for name in ("cases.csv", "citations.csv", "manifest.json")}})
        opinion_rows.extend({"term": term, **row} for row in opinions)
        targets = {target for source in sources for target in graph[source]}
        if previous_term == term - 1:
            overlaps.append({"earlier_term": previous_term, "later_term": term, **precedent_overlap(previous_targets, targets)})
        previous_term, previous_targets = term, targets
    if not records:
        raise ValueError("No term datasets found")
    return {"terms": records, "opinions": opinion_rows, "consecutive_term_overlap": overlaps,
            "limitations": "Descriptive selected subsets. Coverage, unresolved references, issue composition, and extraction methods can affect comparisons. Additional terms do not by themselves establish a historical trend.",
            "age_band_definition": "Mean within-opinion proportion of distinct cited cases aged 0–10 or at least 50 calendar years. Zero-link opinions are excluded only from age measures.",
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def formatted(value, percent=False):
    if value is None:
        return "Not available"
    return f"{value:.1%}" if percent else f"{value:.2f}"


def write_outputs(result, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "annual_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    fields = [key for key in result["terms"][0] if key != "input_sha256"]
    with (output_dir / "annual_summary.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in result["terms"])
    with (output_dir / "annual_opinion_metrics.csv").open("w", newline="", encoding="utf-8") as file:
        fields = ["term", "case_id", "case_name", "cited_cases", "total_citation_age", "mean_citation_age", "median_citation_age"]
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(result["opinions"])
    rows, age_rows, coverage_rows = [], [], []
    for row in result["terms"]:
        rows.append(f"<tr><th>{row['term']}</th><td>{row['source_cases']} / {row['eligible_source_cases']}</td><td>{row['citation_links']:,}</td><td>{formatted(row['mean_cited_cases'])}</td><td>{formatted(row['link_weighted_mean_age'])}</td><td>{formatted(row['equal_opinion_mean_age'])}</td></tr>")
        age_rows.append(f"<tr><th>{row['term']}</th><td>{row['sources_with_age_data']}</td><td>{row['zero_link_sources']}</td><td>{formatted(row['mean_share_0_to_10_years'], True)}</td><td>{formatted(row['mean_share_50_plus_years'], True)}</td></tr>")
        coverage_rows.append(f"<tr><th>{row['term']}</th><td>{row['held_for_review']}</td><td>{row['flagged_reference_entries']}</td><td>{escape(row['method'])}</td></tr>")
    overlap_rows = [f"<tr><th>{r['earlier_term']}–{r['later_term']}</th><td>{r['shared_precedents']}</td><td>{r['union_precedents']}</td><td>{formatted(r['jaccard_share'], True)}</td></tr>" for r in result["consecutive_term_overlap"]]
    document = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Annual Supreme Court Citation Summary</title>
<style>body{{font:16px/1.5 "Times New Roman",Times,serif;color:#000;background:#fff;max-width:1120px;margin:28px auto;padding:0 18px}}h1{{font-size:27px}}h2{{font-size:22px}}a{{color:#000;text-decoration:underline}}table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{text-align:left;padding:8px;vertical-align:top}}thead th{{border-bottom:1px solid #000}}tbody th{{font-weight:normal}}.table{{overflow:auto}}nav a{{margin-right:20px}}</style></head>
<body><nav><a href="index.html">Case Explorer</a><a href="https://github.com/AceAndersonPersonal/scotus-citation-analysis">Source Code</a></nav>
<h1>Annual Supreme Court Citation Summary</h1>
<p>October terms; selected argued majority and per-curiam opinions. New 2020–2023 datasets are preliminary: they have automated boundary and structural checks and targeted evidence checks, not complete manual citation audits.</p>
<h2>Citation counts and ages</h2>
<div class="table"><table><thead><tr><th>Term</th><th>Included / eligible sources</th><th>Distinct links</th><th>Mean cited cases per opinion</th><th>Mean age per link (years)</th><th>Mean of opinion mean ages (years)</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p>Eligible sources meet the SCDB oral-argument and decision-type rule; this is not the total number of Supreme Court decisions. The per-link mean gives opinions with more citations more weight. The final column gives each opinion with at least one recorded link equal weight.</p>
<h2>Age composition within opinions</h2>
<div class="table"><table><thead><tr><th>Term</th><th>Opinions with age data</th><th>Zero-link opinions</th><th>Mean share aged 0–10 years</th><th>Mean share aged 50+ years</th></tr></thead><tbody>{''.join(age_rows)}</tbody></table></div>
<p>{escape(result['age_band_definition'])} These are explicit descriptive thresholds; the two bands do not cover every age.</p>
<h2>Shared precedents between consecutive terms</h2>
<div class="table"><table><thead><tr><th>Terms</th><th>Cited in both</th><th>Cited in either</th><th>Overlap</th></tr></thead><tbody>{''.join(overlap_rows)}</tbody></table></div>
<p>Overlap is the number of distinct precedents cited in both terms divided by the number cited in either term (Jaccard similarity). Each precedent counts once in each set. This does not measure agreement, influence, or how frequently a shared precedent was cited. Gaps between collected terms are not treated as annual changes.</p>
<h2>Coverage and methods</h2>
<div class="table"><table><thead><tr><th>Term</th><th>Source cases held</th><th>Flagged reference entries</th><th>Extraction method</th></tr></thead><tbody>{''.join(coverage_rows)}</tbody></table></div>
<p>Mixed majority/plurality opinions and unresolved source records are held out. Unresolved citation references are logged and omitted. Flagged entries may repeat a precedent and may concern procedural orders; their number is not a count of missing edges or an estimate of recall. Review-entry counting also differs between the original and expanded datasets.</p>
<p>All four new terms use the same extraction implementation. The 2004 archive method and the earlier 2024 PDF implementation differ. Footnotes spanning section boundaries and unnamed short forms may be missed. A zero-link record means no links were extracted under these rules, not necessarily that an opinion cites no Supreme Court cases.</p>
<p>{escape(result['limitations'])}</p>
<p><a href="annual_summary.csv">Term summaries (CSV)</a> · <a href="annual_opinion_metrics.csv">Every source opinion (CSV)</a> · <a href="annual_summary.json">Summary and input fingerprints (JSON)</a></p>
<p>Reproduce with <code>python3 annual_summary.py</code>.</p></body></html>'''
    (output_dir / "annual_summary.html").write_text(document, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "reports")
    args = parser.parse_args()
    result = collect_annual(args.data_dir)
    write_outputs(result, args.output_dir)
    for row in result["terms"]:
        print(f"{row['term']}: {row['source_cases']} sources; {row['citation_links']} links; equal-opinion mean age {formatted(row['equal_opinion_mean_age'])}")
    print("Outputs:", args.output_dir)


if __name__ == "__main__":
    main()
