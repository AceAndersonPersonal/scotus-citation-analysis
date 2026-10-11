"""Regression checks for observed acquisition and opinion-boundary failures."""

import unittest

from scripts.collect_terms import (case_page_range, match_official, normalize_docket,
                                   printed_page, select_majority)
from scripts.build_term_dataset import Metadata, references


class AcquisitionTests(unittest.TestCase):
    def test_docket_formats_and_date_discrepancies(self):
        self.assertEqual(normalize_docket("22O141"), normalize_docket("141, Orig."))
        self.assertEqual(normalize_docket("21-588 (21A85)"), "21-588")
        row = {"docket": "22O143", "dateDecision": "11/21/2021", "usCite": "595 U.S. 15"}
        official = {"docket": "143, Orig.", "date_filed": "2021-11-22", "key": "595:15"}
        match = match_official(row, [official])
        self.assertEqual(match["date_discrepancy"], {"scdb": "2021-11-21", "official": "2021-11-22"})
        self.assertIsNone(match_official(row, [official, official]))

    def test_report_part_is_sliced_before_opinion_selection(self):
        pages = ["PRELIMINARY PRINT", "43 OCTOBER TERM, 2020\nSyllabus\nEarlier case",
                 "44 EARLIER CASE\nOpinion of the Court\nJustice Thomas delivered the opinion of the Court.\n100 U. S. 1.",
                 "OCTOBER TERM, 2020 53\nSyllabus\nSelected case",
                 "54 SELECTED CASE\nOpinion of the Court\nJustice Breyer delivered the opinion of the Court.\n200 U. S. 2.",
                 "OCTOBER TERM, 2020 69\nSyllabus\nNext case"]
        index = [{"key": "592:43"}, {"key": "592:53"}, {"key": "592:69"}]
        begin, end = case_page_range(pages, "592:53", index)
        text = select_majority(pages[begin:end])["majority_text"]
        self.assertIn("200 U. S. 2", text)
        self.assertNotIn("100 U. S. 1", text)
        self.assertNotIn("Next case", text)
        with self.assertRaisesRegex(ValueError, "uniquely"):
            case_page_range(pages, "592:99", index)

    def test_printed_page_layouts(self):
        for text, expected in [("432\nOCTOBER TERM, 2022", 432), ("139OCTOBER\nTERM, 2020", 139),
                               ("CASES ADJUDGED\nIN THE", 1), ("Cite as: 603 U. S. 369 (2024) 371", 371),
                               ("592\n1 of 2\nPRELIMINARY PRINT", None)]:
            self.assertEqual(printed_page(text), expected)

    def test_discussion_of_a_dissent_is_not_a_section_boundary(self):
        pages = ["Opinion of the Court\nJustice Roberts delivered the opinion of the Court.\n"
                 "Justice Kavanaugh, dissenting in Dunn, explained that states should act.\n100 U. S. 1.\n"
                 "Justice Thomas, with whom Justice Alito joins, dissenting.\n200 U. S. 2."]
        result = select_majority(pages)
        self.assertIn("100 U. S. 1", result["majority_text"])
        self.assertNotIn("200 U. S. 2", result["majority_text"])
        self.assertTrue(result["end_preview"].startswith("Justice Thomas"))
        consolidated = select_majority(["Opinion of the Court\nJustice Kavanaugh delivered the opinion of the Court.\n100 U. S. 1.\nJustice Sotomayor, concurring as to No. 19–8709, and concurring in part, dissenting in part, and dissenting from the judgment as to No. 20–444.\n200 U. S. 2."])
        self.assertNotIn("200 U. S. 2", consolidated["majority_text"])

    def test_per_curiam_after_hyphenated_counsel_and_partial_majorities(self):
        pages = ["Syllabus\nCounsel: Jean-", "Kagan, J., concurring\nPer Curiam.\nDismissed.\nIt is so ordered.\nJustice Kagan, concurring.\n100 U. S. 1."]
        result = select_majority(pages)
        self.assertIsNone(result["problem"])
        self.assertEqual(result["start"], "Per Curiam.")
        self.assertNotIn("100 U. S. 1", result["majority_text"])
        partial = select_majority(["Opinion of the Court\nJustice Gorsuch announced the opinion of the Court, except as to Part III.\nText."])
        self.assertEqual(partial["problem"], "mixed_or_plurality_opening")

    def test_full_and_nominative_citations_exclude_short_forms(self):
        text = "Smith, 500 U. S., at 12; Smith v. Jones, 500 U. S. 1; 1 Cranch 137."
        self.assertEqual([key for key, _ in references(text)], ["500:1", "5:137"])

    def test_unpaginated_resolution_requires_unique_full_name_and_volume(self):
        metadata = Metadata.__new__(Metadata)
        metadata.names = {"593:1": {"googlellcvoracleamericainc"}, "500:2": {"smithvjones"}, "500:3": {"smithvjones"}}
        self.assertEqual(metadata.named_reference("593", "See Google LLC v. Oracle America, Inc., "), "593:1")
        self.assertIsNone(metadata.named_reference("594", "Google LLC v. Oracle America, Inc., "))
        self.assertIsNone(metadata.named_reference("593", "Google, "))
        self.assertIsNone(metadata.named_reference("500", "Smith v. Jones, "))


if __name__ == "__main__":
    unittest.main()
