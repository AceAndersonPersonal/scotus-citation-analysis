SCOTUS CITATION PROJECT — 2024 TERM

This is the October 2024 term, including decisions in 2025, not calendar year 2024.
The term comes from the SCDB 2025_01 citation-centered case file.

CURRENT DATA
58 source opinions, 803 total case nodes, 879 directed binary citation links.
Each citations.csv row means the source majority/per-curiam opinion cites the
SCOTUS target at least once. Repeated references do not add edges or weight.
A citation does not imply agreement or endorsement.

Of 64 SCDB term cases, 58 are included, 5 are excluded under the argued-case /
decision-type rule, and Hewitt is held for review. Hewitt has majority Parts
I–III and plurality Parts IV–V; a section-level extraction is needed. See
case_review.csv for every decision. Argued per-curiam dismissals are included
under the existing scope, so Facebook, NVIDIA, and LabCorp have zero edges.

FILES
cases.csv               All source and cited case nodes, including zero-edge sources.
citations.csv           Unique citing_case,cited_case pairs.
case_review.csv         Roster and inclusion/exclusion decisions.
citation_review.csv     68 unresolved/ambiguous/unpaginated source-citation entries.
edge_evidence.json      Citation text, surrounding context, and metadata provenance.
manifest.json           Counts, input fingerprints, scope, and limitations.
validation_audit.json   Three nonempty opinion audits and one zero-edge audit.
parser_2004_checks.json Recognition check against five earlier 2004 text audits.
opinion_audit.json     Majority boundaries, join statements, and text hashes.
raw/                   Official PDFs, extracted text, and frozen metadata caches.

LOADING THE DATA
The root start.py loads both data/term_2004 and data/term_2024 automatically.
Its load_term() function reads the term's cases.csv and citations.csv and includes
all listed cases, including source cases with no outgoing citations.
Run python3 start.py from the project folder to print both term summaries.
The old root CSV copies are preserved in data/archive/root_2004_snapshot;
the active analysis does not read those archived copies.

Read case_id as an opaque string. Shared reporter citations reuse the existing
2004 IDs; new nodes use us:volume:first_page. Targets may be much older than 2024.
is_source is the string True or False. Cited-only nodes have no outgoing links
collected; an empty neighbor list for those nodes does not mean they never cite.
is_sample_source is retained only for compatibility and mirrors is_source.

REBUILDING OFFLINE
From the project folder:

    python3 scripts/build_2024_dataset.py
    python3 scripts/validate_2024_dataset.py

These commands need only the Python standard library and the cached raw files.
They overwrite generated files within data/term_2024, not your graph algorithms.
The builder also uses data/term_2004/cases.csv to preserve IDs and the existing
SCDB ZIP in data/term_2004/raw/scdb.zip to resolve case metadata.
The validator checks this frozen release's expected counts and reviewed cases;
update those expectations deliberately if you change scope or resolve reviews.

RE-EXTRACTING THE CACHED PDFs (OPTIONAL)
Install requirements-data.txt in a virtual environment, then run:

    python3 scripts/extract_2024_text.py
    python3 scripts/build_2024_dataset.py
    python3 scripts/validate_2024_dataset.py

Extraction uses pypdf page-order text including footnotes, supplemented with
pdfplumber body-only text to bridge citations interrupted by page footnotes.
Boundaries are specific to these preliminary-print layouts. Recheck them when
PDFs or extraction library versions change. Text is cached for offline builds.

The optional scripts/download_2024_opinions.py matches the official index against the
SCDB roster and downloads missing PDFs; it reuses existing cached PDFs and index.
It does not acquire all target metadata from scratch. The frozen metadata cache
and raw/metadata-provenance.json are part of the reproducible input snapshot.
CourtListener search responses are cached; rebuilding makes no API calls and
needs no API token. The downloader likewise uses public Supreme Court URLs.

AUDIT FINDINGS AND LIMITATIONS
Bouarfa: 8 substantive links. E.M.D. Sales: 18. Dewberry: 3. Facebook: 0.
The three nonempty opinions' unresolved own-certiorari orders are explicitly
logged and not counted as matched substantive precedents in those audits.
Selected text audits do not establish whole-term precision or recall.

Martin's official PDF prints Hui v. Castaneda as 599 U.S. 799; the correct cite
is 559 U.S. 799. A source-specific correction is recorded in edge_evidence.json.
The printed error was visually checked; case identity was checked against the
559 bound-volume index and the published case at:
https://www.supremecourt.gov/opinions/boundvolumes/559bv.pdf
https://supreme.justia.com/cases/federal/us/559/799/
Other reviewed metadata ambiguities are recorded in raw/metadata-overrides.json.

The 68 review entries are 65 unresolved targets, 1 ambiguous target and 2
unpaginated references. Many are procedural orders, but not all. For example,
CASA cites emergency orders. They remain omissions, not evidence of no citation.
There is no global policy that removes all procedural-history citations.
Full U.S. Reports and nominative reporter citations are recognized. A short-form
reference cannot establish a target by itself; unmatched short forms are not
exhaustively logged by the current parser. This remains a pilot extraction.

2004 used Harvard opinion-index citation links; 2024 uses official PDF text.
The new citation recognizer found all 56 previously audited 2004 precedent links,
but that test does not validate PDF segmentation or establish method equivalence.
Before interpreting differences as changes in the Court, use a common extraction
method or a larger matched audit, and resolve or consistently exclude order
citations. Source counts and issue mixes also differ. Compare citation rates per
source case and report coverage; raw totals alone are not a meaningful trend.

PRIMARY SOURCES
https://www.supremecourt.gov/opinions/slipopinion/24
https://scdb.la.psu.edu/data/2025-release-01/
https://static.case.law/
CourtListener supplied selected exact-citation metadata matches; request URLs
and public results are cached under raw/api. No credentials are stored there.
