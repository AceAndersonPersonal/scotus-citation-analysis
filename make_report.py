"""Generate a chart and standalone HTML report from the curated term CSVs.

Run: python3 make_report.py
Optional: --data-dir PATH --output-dir PATH
The analysis functions live in start.py; this file handles presentation.
"""

import argparse
import hashlib
import json
import math
import re
from datetime import datetime
from html import escape
from importlib.metadata import version
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from start import DATA_DIR, TERMS, citation_ages, load_term, summarize_term


PROJECT_DIR = Path(__file__).resolve().parent
COLORS = {2004: "#226B88", 2024: "#B5532B"}
BIN_WIDTH = 10


def collect_results(data_dir):
    results = []

    for term in TERMS:
        graph, names, years, sources = load_term(term, data_dir)
        ages = citation_ages(graph, sources, years)
        summary = summarize_term(term, data_dir)
        manifest_path = data_dir / f"term_{term}" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        if not ages:
            raise ValueError(f"Term {term} has no citation ages to plot.")
        if any(age < 0 for age in ages):
            raise ValueError(f"Term {term} contains a negative citation age.")
        if len(ages) != summary["edges"]:
            raise ValueError(f"Term {term} has edges outside the selected sources.")
        if summary["source_cases"] != manifest["included_source_cases"]:
            raise ValueError(f"Term {term} source count differs from its manifest.")
        if summary["edges"] != manifest["binary_edges"]:
            raise ValueError(f"Term {term} edge count differs from its manifest.")

        fingerprints = {}
        for name in ("cases.csv", "citations.csv", "manifest.json"):
            path = data_dir / f"term_{term}" / name
            fingerprints[f"term_{term}/{name}"] = hashlib.sha256(path.read_bytes()).hexdigest()

        results.append({
            "summary": summary,
            "ages": ages,
            "manifest": manifest,
            "input_sha256": fingerprints,
        })

    return results


def make_chart(results, output_dir):
    oldest = max(max(result["ages"]) for result in results)
    upper = (oldest // BIN_WIDTH + 1) * BIN_WIDTH
    bins = list(range(0, upper + 1, BIN_WIDTH))
    largest_share = 0

    for result in results:
        counts = [0] * (len(bins) - 1)
        for age in result["ages"]:
            counts[age // BIN_WIDTH] += 1
        assert sum(counts) == len(result["ages"])
        result["histogram"] = {
            "bin_width_years": BIN_WIDTH,
            "bin_left_edges": bins[:-1],
            "counts": counts,
            "percentages": [100 * count / len(result["ages"]) for count in counts],
        }
        largest_share = max(largest_share, max(result["histogram"]["percentages"]))

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 11,
        "axes.labelcolor": "#25394B",
        "text.color": "#172D3D",
        "xtick.color": "#526571",
        "ytick.color": "#526571",
        "svg.fonttype": "none",
    })
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, sharey=True)
    fig.patch.set_facecolor("white")
    fig.subplots_adjust(left=0.09, right=0.97, top=0.79, bottom=0.20, hspace=0.46)
    fig.text(0.09, 0.95, "SUPREME COURT OF THE UNITED STATES", fontsize=10, weight="bold", color="#526571")
    fig.text(0.09, 0.90, "Distribution of Supreme Court Citation Ages", fontsize=23, weight="bold")
    fig.text(0.09, 0.853, "October Terms 2004 and 2024  ·  Percentage of observed citation links within each term", fontsize=12)
    y_limit = math.ceil(largest_share / 5) * 5 + 5

    for ax, result in zip(axes, results):
        summary = result["summary"]
        term = summary["term"]
        color = COLORS[term]
        histogram = result["histogram"]
        ax.bar(bins[:-1], histogram["percentages"], width=BIN_WIDTH, align="edge",
               color=color, alpha=0.82, edgecolor="white", linewidth=0.6, zorder=3)
        ax.axvline(summary["median_citation_age"], color="#162E3E", linewidth=1.7, zorder=4)
        ax.axvline(summary["average_citation_age"], color="#162E3E", linewidth=1.7,
                   linestyle=(0, (4, 3)), zorder=4)
        ax.set_title(
            f"{term} term  |  {summary['source_cases']} source opinions  ·  {summary['edges']:,} links",
            loc="left", fontsize=12, weight="bold", color=color, pad=10,
        )
        ax.text(0.99, 0.90,
                f"Median {summary['median_citation_age']:.0f} years  |  Mean {summary['average_citation_age']:.2f} years",
                transform=ax.transAxes, ha="right", va="top", fontsize=11)
        ax.set_ylim(0, y_limit)
        ax.set_xlim(0, upper)
        ax.set_ylabel("Share of links")
        ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
        ax.set_yticks(range(0, int(y_limit) + 1, 10))
        ax.grid(axis="y", color="#E5EBEE", linewidth=0.8, zorder=0)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color("#CCD7DE")
        ax.tick_params(axis="both", length=0, pad=7)

    axes[-1].set_xlabel("Citation age in calendar years  =  source decision year − cited decision year", labelpad=12)
    fig.text(0.09, 0.075, "Solid line: median   ·   Dashed line: mean   ·   Bins: 0–9, 10–19, … years; shared axes", fontsize=10)
    fig.text(0.09, 0.035, "Exploratory subsets. Extraction methods differ; unresolved citations are omitted. No inference of a historical trend.",
             fontsize=9.5, color="#526571")
    png_path = output_dir / "citation_age_distribution.png"
    svg_path = output_dir / "citation_age_distribution.svg"
    fig.savefig(png_path, dpi=180, facecolor="white")
    fig.savefig(svg_path, facecolor="white")
    plt.close(fig)
    return svg_path


def make_html(results, svg_path, output_dir):
    first, second = [result["summary"] for result in results]
    source_total = sum(result["summary"]["source_cases"] for result in results)
    link_total = sum(result["summary"]["edges"] for result in results)
    table_rows = []
    for result in results:
        s = result["summary"]
        table_rows.append(
            f"<tr><th scope='row'>{s['term']}</th><td>{s['source_cases']}</td>"
            f"<td>{s['edges']:,}</td><td>{s['average_out_degree']:.2f}</td>"
            f"<td>{s['average_citation_age']:.2f}</td><td>{s['median_citation_age']:.0f}</td></tr>"
        )
    coverage_rows = []
    for result in results:
        s, m = result["summary"], result["manifest"]
        held = m.get("cases_needing_review", m.get("case_review_counts", {}).get("needs_review", 0))
        coverage_rows.append(
            f"<li><strong>{s['term']}:</strong> {s['source_cases']} included source opinions; "
            f"{held} additional source case(s) held for review. "
            f"{sum(m['citation_review_counts'].values())} flagged citation-review entries "
            "(not a count of all missing citations).</li>"
        )
    svg = svg_path.read_text(encoding="utf-8")
    svg = svg[svg.index("<svg"):]
    svg = re.sub(r'<svg\b', '<svg role="img" aria-label="Two histograms of citation ages with shared percentage axes. Mean and median are marked for each term."', svg, count=1)
    date = datetime.now(ZoneInfo("America/Denver")).strftime("%B %d, %Y")
    source_note = (
        "The 2004 dataset uses Harvard archive opinion-block citation links; the 2024 dataset "
        "uses official Supreme Court PDF text with resolved case metadata. Majority/per-curiam "
        "source opinions follow the existing argued-case selection rule. "
        "Mixed majority/plurality sections can be held for review."
    )
    html = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Distribution of Supreme Court Citation Ages — 2004 and 2024 Terms</title>
<style>
:root {{ color-scheme: light; --ink:#172d3d; --muted:#526571; --line:#dce5ea; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f2f5f6; color:var(--ink); font:16px/1.6 system-ui,-apple-system,sans-serif; }}
main {{ max-width:1120px; margin:36px auto; background:white; padding:48px 56px; border:1px solid var(--line); border-radius:12px; }}
.eyebrow {{ color:#226b88; font-size:12px; font-weight:750; letter-spacing:.12em; text-transform:uppercase; }}
h1 {{ font-size:clamp(30px,4vw,43px); line-height:1.15; margin:10px 0 16px; letter-spacing:-.025em; }}
h2 {{ font-size:22px; margin:28px 0 10px; line-height:1.25; }}
p {{ margin:10px 0 16px; }}
.lead {{ font-size:18px; max-width:850px; color:var(--muted); }}
.tag {{ display:inline-block; border:1px solid #d7e2e8; border-radius:20px; padding:3px 12px; font-size:12px; margin-right:8px; color:var(--muted); }}
figure {{ margin:26px -16px 12px; }}
figure svg {{ display:block; width:100%; height:auto; }}
figcaption {{ font-size:13px; color:var(--muted); padding:0 16px; }}
.table-wrap {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; margin:14px 0; font-variant-numeric:tabular-nums; }}
th,td {{ padding:12px 10px; border-bottom:1px solid var(--line); text-align:right; }}
th:first-child {{ text-align:left; }}
thead th {{ background:#f3f6f8; font-size:12px; font-weight:650; }}
.note {{ background:#fff7ed; border-left:4px solid #b5532b; padding:16px 20px; margin:24px 0; border-radius:0 6px 6px 0; }}
.note p:last-child {{ margin-bottom:0; }}
li {{ margin:6px 0; }}
ul {{ padding-left:22px; }}
code {{ font-size:.88em; background:#f0f4f6; padding:2px 5px; border-radius:4px; }}
pre {{ background:#172d3d; color:#f2f6f7; padding:18px; border-radius:7px; overflow:auto; font-size:13px; line-height:1.7; }}
pre code {{ background:none; color:inherit; padding:0; }}
a {{ color:#226b88; text-underline-offset:3px; }}
footer {{ margin-top:28px; padding-top:18px; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }}
@media (max-width:650px) {{ main {{ margin:0; padding:25px 20px; border:0; border-radius:0; }} figure {{ margin:20px -12px; }} }}
@media print {{ body {{ background:white; }} main {{ margin:0; padding:0; border:0; }} figure,.note,table {{ break-inside:avoid; }} }}
</style>
</head>
<body><main>
<div class="eyebrow">Supreme Court Citation Networks · Exploratory Comparative Analysis</div>
<h1>Distribution of Supreme Court Citation Ages</h1>
<p class="lead">An exploratory comparison of observed citation links from the October 2004 and 2024 terms. A directed edge connects a source opinion to a Supreme Court case it cites.</p>
<span class="tag">Python · Adjacency lists · CSV</span><span class="tag">{source_total:,} source opinions · {link_total:,} links</span>
<figure>{svg}<figcaption>Percentages use each term’s own citation-link total. Bars have identical 10-year bins and both panels share the same axes; the full observed age range is shown.</figcaption></figure>
<h2>Descriptive Statistics</h2>
<p>The median citation age is <strong>{first['median_citation_age']:.0f} years in 2004</strong> and <strong>{second['median_citation_age']:.0f} years in 2024</strong>. Mean ages are {first['average_citation_age']:.2f} and {second['average_citation_age']:.2f} years, respectively. In both term datasets, the mean exceeds the median, consistent with the long tail of older citations visible above.</p>
<div class="table-wrap"><table>
<thead><tr><th scope="col">Term</th><th scope="col">Source<br>opinions</th><th scope="col">Citation<br>links</th><th scope="col">Links per<br>source</th><th scope="col">Mean age<br>(years)</th><th scope="col">Median age<br>(years)</th></tr></thead>
<tbody>{''.join(table_rows)}</tbody></table></div>
<h2>Definition and Unit of Analysis</h2>
<p><strong>Age = source decision year − cited decision year.</strong> This is a calendar-year difference, not elapsed time to the day. Term labels are not decision years: the October 2024 term includes opinions decided in 2025.</p>
<p>Each distinct source–target pair counts once. If five source opinions cite the same precedent, it contributes five ages. Repeated mentions within one source contribute only one age. Zero-citation sources count toward links per source but contribute no citation ages. The distribution is weighted by links, so opinions with more links contribute more observations.</p>
<div class="note"><strong>Limitations of the Comparison</strong>
<p>The two term datasets do not establish a historical trend or a change in the Court’s reliance on precedent. Extraction methods and coverage differ, issue mixes differ, and unresolved references are omitted. A citation alone does not indicate agreement, legal weight, or how heavily an opinion relies on a case.</p></div>
<h2>Data Sources and Coverage</h2>
<p>{escape(source_note)}</p><ul>{''.join(coverage_rows)}</ul>
<p>The 2024 source set includes three argued per-curiam dismissals with zero links. Short-form-only and unresolved order citations can be missed. Review queues and selected opinion audits document known issues; they do not establish complete recall.</p>
<p>Sources: <a href="https://scdb.la.psu.edu/data/2025-release-01/">Supreme Court Database, release 2025_01</a>; <a href="https://static.case.law/">Harvard Caselaw Access Project</a>; <a href="https://www.supremecourt.gov/opinions/slipopinion/24">Supreme Court 2024 term opinions</a>. Selected case identities were supplemented with CourtListener metadata. Individual CSV inputs and their SHA-256 fingerprints are recorded in <code>citation_age_summary.json</code>.</p>
<h2>Reproducibility</h2>
<p>From the project folder, create an environment once, then run the report generator. It uses the saved curated CSVs and makes no API requests.</p>
<pre><code>python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-report.txt
python3 make_report.py</code></pre>
<p><code>start.py</code> contains the graph and metric functions. <code>make_report.py</code> reuses them to write this standalone HTML report, PNG and SVG charts, and a JSON summary under <code>reports/</code>. Inspect the per-term <code>case_review.csv</code>, <code>citation_review.csv</code>, and audit files before extending the interpretation.</p>
<footer>Generated {date} · Exploratory Comparative Analysis · The chart is embedded; this report opens offline.<br>Further research: harmonize extraction and audit coverage, then compare citation ages within similar case categories.</footer>
</main></body></html>
'''
    (output_dir / "citation_age_report.html").write_text(html, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "reports")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = collect_results(args.data_dir)
    svg_path = make_chart(results, args.output_dir)
    make_html(results, svg_path, args.output_dir)
    public_results = []
    for result in results:
        public_results.append({
            "summary": result["summary"],
            "histogram": result["histogram"],
            "input_sha256": result["input_sha256"],
            "citation_review_counts": result["manifest"]["citation_review_counts"],
        })
    payload = {
        "metric": "Source decision year minus target decision year, once per binary edge",
        "matplotlib_version": version("matplotlib"),
        "script_sha256": {
            "make_report.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "start.py": hashlib.sha256(Path(summarize_term.__code__.co_filename).read_bytes()).hexdigest(),
        },
        "terms": public_results,
    }
    (args.output_dir / "citation_age_summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Report and chart saved to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
