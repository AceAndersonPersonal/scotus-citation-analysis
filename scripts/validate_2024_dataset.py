"""Check the dataset against hand-reviewed opinions and graph invariants (offline)."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
DATA = PROJECT / 'data' / 'term_2024'
RAW = DATA / 'raw'

def read_csv(name):
    with (DATA / name).open(newline='', encoding='utf-8') as file:
        return list(csv.DictReader(file))

cases = read_csv('cases.csv')
edges = read_csv('citations.csv')
by_id = {case['case_id']: case for case in cases}
sources = {case['scdb_id']: case for case in cases if case['is_source'] == 'True'}
pairs = {(edge['citing_case'], edge['cited_case']) for edge in edges}
assert len(by_id) == len(cases), 'Duplicate node IDs'
assert len(pairs) == len(edges), 'Duplicate binary edges'
assert all(a in by_id and b in by_id and a != b for a, b in pairs)
assert all(by_id[a]['is_source'] == 'True' for a, b in pairs)
assert all(by_id[b]['date_filed'] <= by_id[a]['date_filed'] for a, b in pairs)
assert len(cases) == 803 and len(edges) == 879 and len(sources) == 58
assert all(case['term'] == '2024' for case in sources.values())
assert '2024-024' not in sources, 'Mixed majority/plurality Hewitt must stay in review'

# Expectations transcribed after reading the opinion texts, independently of graph output.
fixtures = {
    '2024-001': {
        'expected': ['486:592', '509:43', '533:289', '558:233', '589:221', '590:418', '596:328', '597:785'],
        'cert_grant': '601 U.S. 1166',
        'notes': 'Bouarfa: read majority including five footnotes. Biden v. Texas reference crosses a page break interrupted by footnotes; supplemental body flow recovers it.'
    },
    '2024-012': {
        'expected': ['97:237', '232:37', '309:350', '320:118', '356:129', '376:254', '417:188', '418:323', '441:418', '455:745', '459:375', '462:393', '490:228', '498:279', '564:91', '567:142', '579:93', '601:23'],
        'cert_grant': '602 U.S. 1029',
        'separate_only': ['548:1', '501:104', '572:545'],
        'notes': 'E.M.D. Sales: read majority and Gorsuch concurrence. Three concurrence-only authorities excluded; Microsoft appears in both and is retained.'
    },
    '2024-023': {
        'expected': ['524:51', '538:468', '591:430'],
        'cert_grant': '602 U.S. 1038',
        'separate_only': ['543:426', '333:591', '281:111', '591:71', '469:189', '401:321'],
        'notes': 'Dewberry: read majority including footnotes and full Sotomayor concurrence. All six concurrence-only precedents excluded.'
    },
    '2024-013': {
        'expected': [],
        'notes': 'Facebook: one-sentence argued per-curiam dismissal as improvidently granted; zero citations is valid.'
    }
}
reviews = read_csv('citation_review.csv')
results = []
for sid, fixture in fixtures.items():
    source = sources[sid]
    actual = {by_id[b]['us_citation'] for a, b in pairs if a == source['case_id']}
    expected = {key.replace(':', ' U.S. ') for key in fixture['expected']}
    assert actual == expected, (sid, actual - expected, expected - actual)
    separate_only = {key.replace(':', ' U.S. ') for key in fixture.get('separate_only', [])}
    assert actual.isdisjoint(separate_only), 'Separate opinion leaked into majority'
    if 'cert_grant' in fixture:
        assert any(row['source_case_id'] == source['case_id'] and row['citation_text'] == fixture['cert_grant'] for row in reviews)
    results.append({
        'scdb_id': sid, 'case_name': source['case_name'], 'source_url': source['url'],
        'pdf_sha256': hashlib.sha256((RAW / 'pdf' / (sid + '.pdf')).read_bytes()).hexdigest(),
        'expected_citations': sorted(expected), 'actual_citations': sorted(actual),
        'separate_opinion_only_citations_excluded': sorted(separate_only),
        'unresolved_certiorari_order': fixture.get('cert_grant'),
        'notes': fixture['notes'], 'passed': True
    })
# Every accepted edge must have an inspectable citation context.
evidence = json.loads((DATA / 'edge_evidence.json').read_text())
assert {(row['citing_case'], row['cited_case']) for row in evidence} == pairs
corrections = [row for row in evidence if row['citation_correction']]
assert corrections and all(row['source_scdb_id'] == '2024-062' and row['canonical_citation'] == '559 U.S. 799' for row in corrections)

# Shared reporter citations must preserve the existing term's node IDs.
with (PROJECT / 'data/term_2004/cases.csv').open(newline='', encoding='utf-8') as file:
    legacy = {row['us_citation'].replace(' ', ''): row['case_id'] for row in csv.DictReader(file)}
shared = 0
for case in cases:
    key = case['us_citation'].replace(' ', '')
    if key in legacy:
        assert case['case_id'] == legacy[key], ('Changed shared ID', key)
        shared += 1

report = {
    'audited_on': '2026-10-06', 'reviewer': 'AI-assisted text audit',
    'method': 'Read complete extracted majority texts and footnotes for three nonempty opinions; inspect separate opinions for exclusion and one zero-citation dismissal. Visual spot checks performed for Bouarfa layout and Martin printed citation error.',
    'source_opinions_checked': len(results), 'nonempty_source_opinions_checked': 3,
    'substantive_binary_links_checked': sum(len(f['expected']) for f in fixtures.values()),
    'shared_node_ids_checked': shared, 'structural_checks_passed': True,
    'citation_review_counts': dict(Counter(row['reason'] for row in reviews)),
    'results': results,
    'limits': 'These are selected spot checks, not an estimate of whole-term recall. Unresolved certiorari orders remain in the review queue; they are not counted as substantive precedent edges in these fixtures. Full US/nominative citations are recognized; short forms and unpaginated citations require review when no complete citation establishes the case.'
}
(DATA / 'validation_audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(f"Passed: {len(sources)} sources, {len(cases)} nodes, {len(edges)} edges; 29 substantive links audited; {shared} shared IDs preserved.")
