"""Test the static explorer export independently of the browser."""

import csv
import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_explorer import build_explorer, export_term


class ExplorerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / 'data'
        self.folder = self.make_term(2004)

    def make_term(self, term):
        folder = self.data / f'term_{term}'
        folder.mkdir(parents=True)
        fields = ['case_id', 'case_name', 'date_filed', 'is_source', 'us_citation', 'url']
        with (folder / 'cases.csv').open('w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows([
                dict(zip(fields, ['S', 'Source & Co.', f'{term + 1}-06-01', 'True', '500 U.S. 1', 'https://example.org/s'])),
                dict(zip(fields, ['Z', 'Zero-link source', f'{term + 1}-06-02', 'True', '500 U.S. 2', 'https://example.org/z'])),
                dict(zip(fields, ['P', 'Older precedent', '1900-01', 'False', '100 U.S. 1', 'https://example.org/p'])),
            ])
        (folder / 'citations.csv').write_text('citing_case,cited_case\nS,P\n')
        (folder / 'manifest.json').write_text(json.dumps({
            'term': term, 'included_source_cases': 2, 'nodes': 3, 'binary_edges': 1,
            'citation_review_counts': {}, 'cases_needing_review': 1,
        }))
        return folder

    def test_export_preserves_ids_partial_dates_and_zero_citation_sources(self):
        term = export_term(self.folder)
        self.assertEqual(term['source_count'], 2)
        by_id = {case['id']: case for case in term['sources']}
        self.assertNotIn('P', by_id)
        cited = by_id['S']['citations'][0]
        self.assertEqual(cited['id'], 'P')
        self.assertEqual(cited['date'], '1900-01')
        self.assertEqual(cited['age'], 105)
        self.assertEqual(by_id['S']['median_age'], 105)
        self.assertIsNone(by_id['Z']['median_age'])
        self.assertEqual(by_id['Z']['citations'], [])

    def test_build_discovers_additional_terms_without_a_hardcoded_list(self):
        self.make_term(2005)
        assets = self.root / 'assets'
        assets.mkdir()
        for name in ('index.html', 'style.css', 'app.js'):
            (assets / name).write_text('test asset')
        report = self.root / 'report.html'
        report.write_text('<h1>Test report</h1>')
        output = self.root / 'site'
        payload = build_explorer(self.data, output, assets, report)
        self.assertEqual([term['term'] for term in payload['terms']], [2004, 2005])
        self.assertEqual(json.loads((output / 'data.json').read_text()), payload)
        self.assertEqual((output / 'comparison-report.html').read_text(), report.read_text())

    def test_manifest_mismatch_is_rejected(self):
        path = self.folder / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['binary_edges'] = 2
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'graph size differs'):
            export_term(self.folder)

    def test_unknown_case_and_unsafe_link_are_rejected(self):
        path = self.folder / 'citations.csv'
        path.write_text('citing_case,cited_case\nS,missing\n')
        with self.assertRaisesRegex(ValueError, 'unknown case'):
            export_term(self.folder)
        path.write_text('citing_case,cited_case\nS,P\n')
        cases = self.folder / 'cases.csv'
        cases.write_text(cases.read_text().replace('https://example.org/p', 'javascript:alert(1)'))
        with self.assertRaisesRegex(ValueError, 'Invalid opinion URL'):
            export_term(self.folder)


if __name__ == '__main__':
    unittest.main()
