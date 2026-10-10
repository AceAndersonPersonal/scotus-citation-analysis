"""Compare citation ages with one observation per source opinion.

This complements the link-level summaries in start.py. It does not estimate
historical trends or correct differences in extraction and case selection.
"""

import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
from statistics import mean, median

from start import DATA_DIR, load_term

PROJECT_DIR = Path(__file__).resolve().parent

def opinion_metrics(graph, source_ids, case_years, case_names):
    """Keep zero-link sources, but leave their age statistics undefined."""
    rows = []

    for case_id in source_ids:
        ages = []
        for cited_id in graph[case_id]:
            age = case_years[case_id] - case_years[cited_id]
            if age < 0:
                raise ValueError(f"Negative citation age for {case_id} -> {cited_id}")
            ages.append(age)

        rows.append({
            "case_id": case_id,
            "case_name": case_names[case_id],
            "cited_cases": len(ages),
            "total_citation_age": sum(ages),
            "mean_citation_age": mean(ages) if ages else None,
            "median_citation_age": median(ages) if ages else None,
        })

    return rows

def summarize_opinions(rows):
    """Distinguish a mean across links from a mean across source opinions."""
    counts = [row["cited_cases"] for row in rows]
    opinion_means = [row["mean_citation_age"] for row in rows
                     if row["mean_citation_age"] is not None]
    links = sum(counts)

    return {
        "source_cases": len(rows),
        "sources_with_age_data": len(opinion_means),
        "zero_link_sources": len(rows) - len(opinion_means),
        "citation_links": links,
        "mean_cited_cases": mean(counts) if counts else None,
        "median_cited_cases": median(counts) if counts else None,
        "link_weighted_mean_age": sum(row["total_citation_age"] for row in rows) / links if links else None,
        "equal_opinion_mean_age": mean(opinion_means) if opinion_means else None,
        "median_of_opinion_mean_ages": median(opinion_means) if opinion_means else None,
    }

def omission_effects(earlier_rows, later_rows):
    """Remove one age-bearing opinion at a time, from either term.

    The measured difference is later minus earlier, using equal-opinion means.
    Each removal starts from the full datasets. This is a sensitivity check,
    not a confidence interval, significance test, or correction for bias.
    """
    earlier = [row for row in earlier_rows if row["mean_citation_age"] is not None]
    later = [row for row in later_rows if row["mean_citation_age"] is not None]
    if not earlier or not later:
        return []

    earlier_mean = mean(row["mean_citation_age"] for row in earlier)
    later_mean = mean(row["mean_citation_age"] for row in later)
    baseline = later_mean - earlier_mean
    effects = []

    for group, rows in (("earlier", earlier), ("later", later)):
        if len(rows) < 2:
            continue
        total = sum(row["mean_citation_age"] for row in rows)
        for row in rows:
            remaining_mean = (total - row["mean_citation_age"]) / (len(rows) - 1)
            difference = later_mean - remaining_mean if group == "earlier" else remaining_mean - earlier_mean
            effects.append({
                "omitted_group": group,
                "case_id": row["case_id"],
                "case_name": row["case_name"],
                "difference_after_omission": difference,
                "change_from_full_difference": difference - baseline,
            })

    return sorted(effects, key=lambda row: (-abs(row["change_from_full_difference"]),
                                          row["omitted_group"], row["case_id"]))

def compare_terms(earlier_term, later_term, data_dir=DATA_DIR):
    if earlier_term >= later_term:
        raise ValueError("Choose two terms in chronological order.")

    terms = []
    for term in (earlier_term, later_term):
        graph, names, years, source_ids = load_term(term, data_dir)
        rows = opinion_metrics(graph, source_ids, years, names)
        rows.sort(key=lambda row: (row["case_name"].casefold(), row["case_id"]))
        folder = Path(data_dir) / f"term_{term}"
        terms.append({
            "term": term,
            "summary": summarize_opinions(rows),
            "opinions": rows,
            "input_sha256": {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                             for name in ("cases.csv", "citations.csv", "manifest.json")},
        })

    before, after = (term["summary"] for term in terms)
    differences = {}
    for metric in ("mean_cited_cases", "median_cited_cases", "link_weighted_mean_age",
                   "equal_opinion_mean_age", "median_of_opinion_mean_ages"):
        differences[metric] = after[metric] - before[metric] if before[metric] is not None and after[metric] is not None else None

    effects = omission_effects(terms[0]["opinions"], terms[1]["opinions"])
    baseline = differences["equal_opinion_mean_age"]
    sensitivity = {
        "full_difference": baseline,
        "tested_omissions": len(effects),
        "minimum_difference": min(row["difference_after_omission"] for row in effects) if effects else None,
        "maximum_difference": max(row["difference_after_omission"] for row in effects) if effects else None,
        "omissions": effects,
    }
    return {
        "difference_direction": "later term minus earlier term",
        "age_weighting": "Equal-opinion age statistics exclude zero-link sources; citation-count statistics include them.",
        "sensitivity_definition": "Omit exactly one age-bearing opinion from either term; recompute the equal-opinion mean difference. Not a confidence interval.",
        "limitations": "Describes the curated datasets only. Source selection, issue composition, extraction differences, and missing citations are not controlled.",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "terms": terms,
        "differences": differences,
        "one_opinion_sensitivity": sensitivity,
    }

def number(value):
    return "Not available" if value is None else f"{value:.2f}"

def write_outputs(result, output_dir):
    """Export every opinion and every omission, so aggregate results are traceable."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "opinion_comparison.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with (output_dir / "opinion_metrics.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["term", "case_id", "case_name", "cited_cases", "total_citation_age", "mean_citation_age", "median_citation_age"])
        writer.writeheader()
        for term in result["terms"]:
            for row in term["opinions"]:
                writer.writerow({"term": term["term"], **row})

    with (output_dir / "opinion_omission_effects.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["omitted_term", "case_id", "case_name", "difference_after_omission", "change_from_full_difference"])
        writer.writeheader()
        for row in result["one_opinion_sensitivity"]["omissions"]:
            row = dict(row)
            group = row.pop("omitted_group")
            row["omitted_term"] = result["terms"][0 if group == "earlier" else 1]["term"]
            writer.writerow(row)

    terms = result["terms"]
    metrics = [
        ("Source opinions", "source_cases"),
        ("Opinions with citation-age data", "sources_with_age_data"),
        ("Zero-link opinions", "zero_link_sources"),
        ("Mean distinct cited cases per opinion", "mean_cited_cases"),
        ("Median distinct cited cases per opinion", "median_cited_cases"),
        ("Mean citation age, one observation per link (years)", "link_weighted_mean_age"),
        ("Mean of opinion mean citation ages (years)", "equal_opinion_mean_age"),
        ("Median of opinion mean citation ages (years)", "median_of_opinion_mean_ages"),
    ]
    table_rows = "".join("<tr><th scope='row'>" + label + "</th>" + "".join(
        "<td>" + (str(term["summary"][metric]) if metric in ("source_cases", "sources_with_age_data", "zero_link_sources") else number(term["summary"][metric])) + "</td>" for term in terms) + "</tr>" for label, metric in metrics)
    sensitivity = result["one_opinion_sensitivity"]
    influence_rows = ""
    for row in sensitivity["omissions"][:5]:
        term = terms[0 if row["omitted_group"] == "earlier" else 1]["term"]
        influence_rows += f"<tr><td>{term}</td><td>{html.escape(row['case_name'])}</td><td>{number(row['difference_after_omission'])}</td><td>{number(row['change_from_full_difference'])}</td></tr>"
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Opinion-level citation comparison</title>
<style>body{{font:16px/1.5 'Times New Roman',Times,serif;color:#000;background:#fff;max-width:1050px;margin:28px auto;padding:0 18px}}h1{{font-size:28px}}h2{{font-size:22px}}a{{color:#000}}table{{border-collapse:collapse;width:100%;margin:18px 0}}th,td{{padding:8px;text-align:left;vertical-align:top}}thead th{{border-bottom:1px solid #000}}tbody th{{font-weight:normal}}.table{{overflow:auto}}</style></head><body>
<h1>Opinion-level citation comparison: {terms[0]['term']} and {terms[1]['term']}</h1>
<p>Does the citation-age difference persist when each source opinion receives equal weight?</p>
<div class="table"><table><thead><tr><th>Measure</th><th>{terms[0]['term']}</th><th>{terms[1]['term']}</th></tr></thead><tbody>{table_rows}</tbody></table></div>
<p>The later-minus-earlier difference is {number(result['differences']['link_weighted_mean_age'])} years when each citation link has equal weight, and {number(result['differences']['equal_opinion_mean_age'])} years when each opinion with at least one link has equal weight. The latter is the average of the individual opinion means, not the age of a typical citation.</p>
<h2>Sensitivity to individual opinions</h2>
<p>Removing one opinion at a time produces equal-opinion mean differences from {number(sensitivity['minimum_difference'])} to {number(sensitivity['maximum_difference'])} years, across {sensitivity['tested_omissions']} valid removals. Each removal begins with the full datasets. This range measures sensitivity to a single included opinion; it is not a confidence interval and does not address missing citations, omitted opinions, or several influential opinions acting together.</p>
<p>The five removals with the largest absolute effect are shown below. Change is measured relative to the full equal-opinion difference; a negative change reduces that difference.</p>
<div class="table"><table><thead><tr><th>Omitted term</th><th>Omitted opinion</th><th>Remaining difference (years)</th><th>Change (years)</th></tr></thead><tbody>{influence_rows}</tbody></table></div>
<h2>Definitions and limitations</h2>
<p>Each distinct source-to-precedent pair contributes one citation age: source decision year minus cited decision year. Opinion means are calculated from those distinct links. Zero-link opinions remain in citation-count statistics; their age statistics are undefined and excluded from age summaries. A median of opinion means is different from a median across all links.</p>
<p>{html.escape(result['limitations'])} In particular, the 2004 data use Harvard archive opinion-block links and the 2024 data use official PDF extraction. The sensitivity check cannot establish a historical trend or explain why a difference occurs.</p>
<p><a href="opinion_metrics.csv">All opinion metrics (CSV)</a> · <a href="opinion_omission_effects.csv">All omission results (CSV)</a> · <a href="opinion_comparison.json">Summary and input fingerprints (JSON)</a></p>
<p>Reproduce from the project root: <code>python3 compare_terms.py --terms {terms[0]['term']} {terms[1]['term']}</code>. No additional dependencies or API access are required.</p>
</body></html>"""
    (output_dir / "opinion_comparison.html").write_text(document, encoding="utf-8")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terms", type=int, nargs=2, default=(2004, 2024), metavar=("EARLIER", "LATER"))
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "reports")
    args = parser.parse_args()
    result = compare_terms(*args.terms, data_dir=args.data_dir)
    write_outputs(result, args.output_dir)
    for term in result["terms"]:
        summary = term["summary"]
        print(f"Term {term['term']}: {summary['source_cases']} opinions; {summary['sources_with_age_data']} with age data")
        print("  Link-weighted mean citation age:", number(summary["link_weighted_mean_age"]))
        print("  Mean of opinion mean citation ages:", number(summary["equal_opinion_mean_age"]))
        print("  Median of opinion mean citation ages:", number(summary["median_of_opinion_mean_ages"]))
    sensitivity = result["one_opinion_sensitivity"]
    print("Equal-opinion difference (later minus earlier):", number(sensitivity["full_difference"]))
    print("Single-opinion omission range:", number(sensitivity["minimum_difference"]), "to", number(sensitivity["maximum_difference"]))
    print("Sensitivity range only; not a confidence interval.")
    print("Outputs:", args.output_dir)

if __name__ == "__main__":
    main()
