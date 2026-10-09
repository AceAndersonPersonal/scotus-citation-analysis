"""Build binary majority-opinion citation CSVs from saved public source records.

Run from the project directory after acquisition. This is data preparation only;
the student's graph and analysis functions are kept in their own files.
All exclusions and unresolved links are exported rather than silently guessed.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import zipfile


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_csv(path, fields, rows):
    temporary = path.with_suffix('.csv.tmp')
    with temporary.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def official_cite(case):
    return next((c['cite'] for c in case['citations'] if c['type'] == 'official'), '')


def cap_id(case):
    return 'cap:' + str(case['id'])


def build(inputs, output):
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(inputs/'scdb.zip') as archive:
        name = next(n for n in archive.namelist() if n.endswith('.csv'))
        all_scdb = list(csv.DictReader(io.StringIO(archive.read(name).decode('utf-8-sig'))))
    scdb = [r for r in all_scdb if r['term'] == '2004']
    roster = read_json(inputs/'term-roster.json')
    sources = read_json(inputs/'source-cases.json')
    targets = read_json(inputs/'target-cases.json')
    flags = read_json(inputs/'case-flags.json')
    legacy = read_json(inputs/'legacy_ids.json')
    source_by_id = {c['id']:c for c in sources}
    source_by_scdb = {r['scdb']['caseId']:source_by_id[r['cap_id']] for r in roster}
    all_cases = {c['id']:c for c in sources + targets}
    if len(source_by_scdb) != 75:
        raise ValueError('Expected all 75 SCDB majority/per-curiam candidates to be downloaded.')

    # Preserve sample CourtListener IDs when the reporter citation matches uniquely.
    citation_ids = defaultdict(set)
    for c in all_cases.values():
        citation_ids[official_cite(c)].add(c['id'])
    ids = {}
    for cid, c in all_cases.items():
        cite = official_cite(c)
        ids[cid] = legacy[cite] if cite in legacy and len(citation_ids[cite]) == 1 else cap_id(c)
    if len(set(ids.values())) != len(ids):
        raise ValueError('Case identifier collision.')

    reviews = []
    included = {}
    for row in scdb:
        c = source_by_scdb.get(row['caseId'])
        status, reason = 'included', 'SCDB argued decision; separately identifiable majority opinion'
        if not row['dateArgument']:
            status, reason = 'excluded', 'No oral argument recorded in SCDB'
        elif row['decisionType'] == '7':
            status, reason = 'excluded', 'SCDB judgment of Court without a majority opinion'
        elif row['decisionType'] not in ('1','6'):
            status, reason = 'excluded', 'Outside selected SCDB decision types'
        elif c is None:
            raise ValueError('Missing source: ' + row['caseId'])
        elif str(c['id']) in flags:
            status, reason = 'needs_review', flags[str(c['id'])]
        else:
            opinions = c['casebody']['opinions']
            if not opinions or opinions[0]['type'] != 'majority':
                raise ValueError('Unexpected majority index: ' + c['name_abbreviation'])
            if sum(o['type'] == 'majority' for o in opinions) != 1:
                raise ValueError('Multiple majority records require explicit review')
            if c['court']['id'] != 9009:
                raise ValueError('Source court is not SCOTUS')
            if official_cite(c) != row['usCite']:
                raise ValueError('SCDB citation mismatch')
            if c['decision_date'] != datetime.strptime(row['dateDecision'],'%m/%d/%Y').date().isoformat():
                raise ValueError('SCDB decision date mismatch')
            included[c['id']] = c
        reviews.append({'scdb_id':row['caseId'], 'case_name':c['name_abbreviation'] if c else row['caseName'],
                        'us_citation':row['usCite'], 'date_argument':row['dateArgument'],
                        'decision_type':row['decisionType'], 'status':status, 'reason':reason,
                        'case_id':ids[c['id']] if c else '',
                        'cap_url':next((r['url'] for r in roster if r['scdb']['caseId']==row['caseId']), '')})

    edges = set()
    evidence = []
    citation_reviews = []
    referenced = set(included)
    text_checks = 0
    for source_id, source in included.items():
        normalized_text = re.sub(r'\s+', '', source['casebody']['opinions'][0]['text'])
        for ref in source['cites_to']:
            # -1 is head matter; dissent/concurrence indexes are also excluded.
            if ref.get('opinion_index') != 0:
                continue
            paths = ref.get('case_paths', [])
            candidates = ref.get('case_ids', [])
            is_us_ref = ref.get('reporter') == 'U.S.' or any(p.startswith('/us/') for p in paths)
            if not is_us_ref:
                continue
            if ref.get('reporter') == 'U.S.':
                if re.sub(r'\s+', '', ref['cite']) not in normalized_text:
                    raise ValueError('Citation entry missing from selected majority text')
                text_checks += 1
            reason = ''
            if len(candidates) != 1 or len(paths) != 1:
                reason = 'ambiguous_target' if len(candidates) > 1 else 'unresolved_target'
            elif not paths[0].startswith('/us/'):
                reason = 'target_outside_US_Reports_archive'
            elif candidates[0] not in all_cases:
                raise ValueError('Required precedent record not downloaded')
            else:
                target = all_cases[candidates[0]]
                if target['court']['id'] != 9009:
                    reason = 'target_not_SCOTUS'
                elif target['decision_date'] > source['decision_date']:
                    reason = 'target_date_after_source_needs_review'
                elif target['id'] == source_id:
                    reason = 'self_reference_excluded'
            if reason:
                citation_reviews.append({'source_case_id':ids[source_id], 'source_case_name':source['name_abbreviation'],
                                         'citation_text':ref['cite'], 'reason':reason,
                                         'candidate_cap_ids':json.dumps(candidates)})
                continue
            target_id = candidates[0]
            referenced.add(target_id)
            edges.add((ids[source_id], ids[target_id]))
            evidence.append({'citing_case':ids[source_id], 'cited_case':ids[target_id],
                             'source_cap_id':source_id, 'target_cap_id':target_id,
                             'opinion_index':0, 'opinion_type':'majority', 'citation_text':ref['cite'],
                             'target_archive_path':paths[0],
                             'archive_extraction_weight':ref.get('weight',1)})

    rows = []
    for cid in sorted(referenced):
        c = all_cases[cid]
        rows.append({'case_id':ids[cid], 'case_name':c['name_abbreviation'], 'date_filed':c['decision_date'],
                     'is_sample_source':cid in included, 'is_source':cid in included,
                     'us_citation':official_cite(c), 'cap_id':cid,
                     'id_namespace':'courtlistener' if not ids[cid].startswith('cap:') else 'harvard_cap',
                     'url':f"https://cite.case.law/us/{official_cite(c).split()[0]}/{c['first_page']}/"})
    source_ids = {ids[cid] for cid in included}
    nodes = {r['case_id'] for r in rows}
    assert len(nodes) == len(rows)
    assert all(a in source_ids and b in nodes and a != b for a,b in edges)
    assert {(e['citing_case'],e['cited_case']) for e in evidence} == edges
    assert len(reviews) == len(scdb) == 80
    assert len(included) == 70
    write_csv(output/'cases.csv', list(rows[0]), rows)
    write_csv(output/'citations.csv', ['citing_case','cited_case'],
              [{'citing_case':a,'cited_case':b} for a,b in sorted(edges)])
    write_csv(output/'case_review.csv', list(reviews[0]), reviews)
    write_csv(output/'citation_review.csv', list(citation_reviews[0]), citation_reviews)
    (output/'edge_evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    (output/'id_crosswalk.json').write_text(json.dumps({str(k):v for k,v in ids.items() if k in referenced},indent=2))
    source_details = []
    for c in included.values():
        source_details.append({'case_id':ids[c['id']], 'cap_id':c['id'],
                               'majority_text_sha256':hashlib.sha256(c['casebody']['opinions'][0]['text'].encode()).hexdigest(),
                               'judges_statement':c['casebody']['judges'],
                               'majority_opening':c['casebody']['opinions'][0]['text'][:400]})
    (output/'opinion_audit.json').write_text(json.dumps(source_details,indent=2),encoding='utf-8')
    manifest = {
        'built_at':datetime.now(timezone.utc).isoformat(), 'term':2004,
        'scdb_release':'2025_01', 'scdb_term_cases':80, 'argued_cases':76,
        'included_source_cases':len(included), 'cases_needing_review':5,
        'argued_cases_excluded_no_majority':1, 'unargued_cases_excluded':4,
        'nodes':len(rows), 'binary_edges':len(edges),
        'full_US_citation_entries_checked_against_majority_text':text_checks,
        'unit_of_analysis':'SCDB case-centered citation units; consolidated disputes counted once',
        'citation_review_counts':dict(Counter(r['reason'] for r in citation_reviews)),
        'source_ids_without_edges':sorted(source_ids - {a for a,b in edges}),
        'scope':'SCDB term=2004 with oral argument date and decisionType in {1,6}; '
                'only clearly separable majority opinions. Five mixed/plurality or malformed opinion records held for review. '
                'SCOTUS targets from any date up to the source decision; one directed edge per distinct case pair.',
        'sources':{'scdb':'https://scdb.la.psu.edu/data/2025-release-01/',
                   'scdb_codebook':'https://scdb.la.psu.edu/online-codebook/decision-type/',
                   'opinion_archive':'https://static.case.law/',
                   'legacy_ids':'CourtListener sample cache, retained only for unambiguous reporter-citation matches'},
        'limitations':[
            'This is a 70-case reviewed subset of the 76 argued decisions, not complete majority-section coverage.',
            'Automated archive citation extraction and OCR are imperfect; unresolved and ambiguous targets are omitted and logged.',
            'Archive opinion_index links citations to opinion blocks; no dissent, concurrence, or head-matter citations are intentionally included.',
            'Five cases need section-level review before inclusion; see case_review.csv.',
            'Archive extraction weights are provenance only, not verified counts of all mentions; graph edges remain binary.',
            'Cited-only cases have not had outgoing citations collected; an empty adjacency list does not mean they cited nothing.',
            'Future 2024 comparison requires a comparable acquisition/extraction method and coverage audit; Harvard archive ends before 2024.'
        ],
        'compatibility':'Existing sample CourtListener IDs are retained when uniquely matched. New IDs have a cap: prefix. '
                        'Treat all case_id values as opaque strings. is_sample_source is a compatibility alias for is_source.',
        'input_sha256':{name:hashlib.sha256((inputs/name).read_bytes()).hexdigest() for name in
                        ['scdb.zip','term-roster.json','source-cases.json','target-cases.json','case-flags.json','legacy_ids.json']}
    }
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ['included_source_cases','nodes','binary_edges','citation_review_counts','source_ids_without_edges']},indent=2))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    project = Path(__file__).resolve().parents[1]
    parser.add_argument('--inputs', type=Path, default=project/'data/term_2004/raw')
    parser.add_argument('--output', type=Path, default=project/'data/term_2004')
    parser.add_argument('--publish', action='store_true', help='Back up the current root CSVs and replace them with this dataset')
    args = parser.parse_args()
    build(args.inputs,args.output)
    if args.publish:
        backup = project/'data/sample_3_cases'
        backup.mkdir(parents=True,exist_ok=True)
        for name in ['cases.csv','citations.csv']:
            if (project/name).exists() and not (backup/name).exists():
                shutil.copy2(project/name,backup/name)
            shutil.copy2(args.output/name,project/name)
        print('Published CSVs; original sample preserved in data/sample_3_cases.')
