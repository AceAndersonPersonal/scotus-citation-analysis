# Data Preparation Scripts

Run these commands from the project root, with the project environment active (`source .venv/bin/activate`). Each script resolves data paths relative to the project, even though the scripts now live in this folder. Running `start.py` or `make_report.py` does not run these data preparation steps.

| Script | Purpose | Inputs |
| --- | --- | --- |
| `build_explorer.py` | Export all complete curated terms to a static website | Term CSVs/manifests, `web/` assets, and the generated report |
| `build_2004_dataset.py` | Rebuild the 2004 curated data | Cached records in `data/term_2004/raw/` |
| `build_2024_dataset.py` | Rebuild the 2024 curated data | Cached 2024 text and metadata, 2004 IDs, and SCDB archive |
| `validate_2024_dataset.py` | Check recorded opinion audits and structural invariants | Curated CSVs, evidence records, and cached PDFs |
| `download_2024_opinions.py` | Download missing official PDFs for the matched SCDB roster | Existing SCDB archive and public Court URLs |
| `extract_2024_text.py` | Extract majority text from cached PDFs | PDF dependencies and cached opinions |
| `download_sample.py` | Acquire the original small CourtListener sample | CourtListener API token and network access for uncached requests |

## Rebuild and validate cached data

```bash
python3 scripts/build_2004_dataset.py
python3 scripts/build_2024_dataset.py
python3 scripts/validate_2024_dataset.py
```

These commands write generated data or audit records under the term folders. Raw inputs are retained locally and ignored by Git; they are needed for rebuilding, but not for the analysis or report.

The 2004 builder's optional `--publish` flag is a legacy export that recreates root-level CSV copies. It is unnecessary for the current analysis, which reads the term folders directly. Existing root CSV copies have been preserved under `data/archive/root_2004_snapshot/`.

## PDF acquisition and extraction

```bash
python3 scripts/download_2024_opinions.py
python3 -m pip install -r requirements-data.txt
python3 scripts/extract_2024_text.py
```

Install the PDF dependencies in the same virtual environment selected in VS Code. The pinned PDF dependencies require Python 3.10 or later; Python 3.12 is recommended. These steps are optional when the cached extracted text is already present. Changes to PDF versions or extraction libraries require renewed boundary checks; downloading the PDFs alone does not recreate the full target-metadata cache.

## Earlier CourtListener sample

The sample downloader now writes to `data/sample_3_cases/`, including its `manifest.json`, instead of placing CSVs at the project root. It checks for existing sample CSVs and requires `--overwrite` to replace them. The historical `data/sample_manifest.json` remains preserved.

```bash
python3 scripts/download_sample.py --help
```

The token is still read from the root `.courtlistener-token` file or the `COURTLISTENER_API_TOKEN` environment variable. Never include the token in shared data or source control. No token is needed for the report or standard graph tests.

## Additional terms: staging, checks, and publication

The reusable pipeline is exercised on 2020–2023. It uses the cached SCDB 2025_01 citation-centered archive at `data/term_2004/raw/scdb.zip`, committed 2004/2024 case registries for stable IDs, cached official indexes and reporter metadata under `data/term_2024/raw/`, and any newly downloaded reporter metadata in `data/reference_cache/`. Raw inputs are local and ignored by Git. A fresh clone reproduces analysis from the committed CSVs; exact acquisition rebuilds require these fingerprinted raw inputs. This is not yet a self-contained downloader for every historical term.

```bash
python3 scripts/collect_terms.py --terms 2023 2022 2021 2020
python3 scripts/build_term_dataset.py --terms 2023 2022 2021 2020 --fetch-metadata
python3 scripts/audit_terms.py --terms 2020 2021 2022 2023
python3 scripts/publish_terms.py --terms 2020 2021 2022 2023
python3 annual_summary.py
python3 scripts/build_explorer.py
```

Existing published destinations require the explicit `--replace` flag after reviewing their changes. `collect_terms.py --stage acquire` downloads only; `--stage extract` reuses cached PDFs. Downloads use three workers, retries for transient failures, and atomic cache writes. An unavailable individual PDF is logged and held for review instead of fabricated or silently included.

The collector matches source cases by docket and decision date, normalizes original-jurisdiction docket formats, selects a case's printed page range within report-part PDFs, and selects the majority/per-curiam section before a separate opinion. Partial-majority openings and join statements are held out. Full page text retains footnotes; a supplemental body-font stream bridges references interrupted by footnotes. Boundary-spanning footnotes can still be missed.

`build_term_dataset.py` exports cases, unique directed citation pairs, per-reference evidence, unresolved-reference records, and input fingerprints under `data/staging/term_YYYY/`. Full reporter citations and unambiguous full-name/volume references can resolve a target; unnamed short forms alone cannot. Matching uncertainty is recorded rather than guessed.

`audit_terms.py` checks every included source's author, distinct selected text, detected boundary, and disposition, and records targeted citation evidence checks for three purposively selected cases per new term. These are automated checks, not independent manual full-opinion audits or a statistical estimate of recall. Add and review an appropriate sample when expanding its `SAMPLES` mapping to another term. `publish_terms.py` checks the dataset contract and evidence before copying only the explicit export files; it does not publish to GitHub by itself.
