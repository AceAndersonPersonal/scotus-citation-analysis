# Term datasets and expansion

Published datasets cover October Term 2004 and October terms 2020–2024. The 2020–2023 expansion is preliminary and has automated boundary/structure checks and targeted evidence checks; it has not received complete manual citation audits. Their different extraction methods and selected coverage limit historical comparisons. More terms provide additional observations, but do not by themselves resolve selection or measurement bias.

## Explorer input contract

Add each reviewed dataset under `data/term_YYYY/`. The explorer discovers these folders automatically, in year order. A partially prepared term should stay outside that naming pattern until it is ready; missing or inconsistent required files cause the export to fail.

Each term needs:

- `cases.csv`: unique `case_id`, `case_name`, `date_filed`, `is_source`, `us_citation`, and `url` columns. Source flags use the strings `True` and `False`. Preserve recorded date precision; the analysis uses the decision year.
- `citations.csv`: unique `citing_case,cited_case` pairs. Both IDs must exist in `cases.csv`; only included source cases may have outgoing edges. Include sources with no links in `cases.csv`.
- `manifest.json`: `term`, `included_source_cases`, `nodes`, `binary_edges`, `citation_review_counts`, `input_method`, and review counts (`cases_needing_review` or `case_review_counts.needs_review`). Record selection rules, provenance, exclusions, and input hashes as in the existing manifests.
- Review and evidence records following the existing datasets: `case_review.csv`, `citation_review.csv`, `edge_evidence.json`, and opinion audits. The explorer does not replace those records.

Use stable case IDs across terms. A case's identity should not change when it appears in a different year's citations. Do not assume that matching names alone establish identity.

Build the explorer with `python3 scripts/build_explorer.py`. The export validates manifest totals, case IDs, source-only outgoing edges, nonnegative citation ages, and opinion-link protocols. It does not validate extraction recall or automatically approve a new dataset for research.

## Next expansion

The first consecutive block is now 2020–2024. Continue backward from 2019 after checking the older official PDF layouts, or extend the archive-based acquisition for earlier terms. Preserve the distinction between the common 2020–2023 parser, the original 2024 PDF parser, and the 2004 archive method.

Loper Bright (decided June 28, 2024) is a source in October Term 2023 and a cited-only case in the 2024 dataset. Term labels identify October terms, not calendar years.

Before comparing more terms:

1. Freeze the source selection rule: argued majority and per-curiam opinions, with an explicit policy for dismissals and mixed majority/plurality sections.
2. Apply a common citation extraction and case-resolution procedure where practical. Until then, report extraction methods separately and conduct matched audits across them.
3. Audit a recorded sample of complete opinions, including footnotes, separate opinions, zero-link cases, and missed or ambiguous citations. Record how the sample was selected; selected checks are not an estimate of overall recall.
4. Preserve source texts and metadata locally, export citation evidence, and log exclusions instead of silently dropping them.
5. Validate IDs, dates, duplicate links, counts, and shared precedents; update dataset tests deliberately when adding terms.
6. Compare per-source measurements and distributions alongside edge-weighted results, and consider issue composition before attributing differences to historical change.

The reusable acquisition, extraction, resolution, and promotion commands are documented in [the scripts guide](../scripts/README.md). They have been exercised on 2020–2023. Earlier layouts still need validation; adding a year argument does not guarantee a comparable dataset.
