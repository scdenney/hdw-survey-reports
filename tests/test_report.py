import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import report  # noqa: E402

FIXTURE = HERE / "fixture_export.csv"
EXPECTED_QUESTIONS = {
    "Is a photo I take of a book page already data?",
    "What is the difference between metadata and provenance?",
    "Does OCR count as born-digital?",
    "Why does the census not record self-description?",
    "Can I use a Wikipedia page as my Part A object?",
    "How do I find the edition of a scan?",
}


class ReportFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = report.load_surveys()
        cls.survey = report.select_survey(cfg, "2", "en", "opener")
        tags = set(report.content_tags(cls.survey))
        raw = report.response_rows(FIXTURE, tags)
        cls.raw_count = len(raw)
        cls.rows = report.drop_identity(report.finished_rows(raw), cls.survey["identity_tags"])
        cls.text = report.render_markdown(cls.survey, cls.rows, "2026-10-12 14:00 UTC", "fixture")

    def test_finished_count(self):
        self.assertEqual(self.raw_count, 13)
        self.assertEqual(len(self.rows), 11)
        self.assertIn("Finished responses: 11", self.text)

    def test_identity_never_in_output(self):
        for needle in ("Fixture0", "Surname", "s1000000", "Q2.N1"):
            self.assertNotIn(needle, self.text)
        for row in self.rows:
            for tag in self.survey["identity_tags"]:
                self.assertNotIn(tag, row)

    def test_label_order_and_percentages(self):
        item = self.survey["items"][0]
        table = report.count_table(self.rows, item["tag"], item["labels"])
        self.assertEqual([t[0] for t in table], item["labels"])
        self.assertEqual(sum(t[1] for t in table), 11)
        self.assertAlmostEqual(sum(t[2] for t in table), 100.0, places=6)

    def test_arm_table_has_both_conditions(self):
        arm = self.survey["arms"][0]
        table = report.arm_table(self.rows, arm, self.survey["condition_field"])
        conditions = set(table[0][1].keys())
        self.assertEqual(conditions, {"page_only", "page_plus_metadata"})
        per_arm = {c: sum(cells[c][0] for _, cells in table) for c in conditions}
        self.assertEqual(sum(per_arm.values()), 11)
        self.assertTrue(all(n > 0 for n in per_arm.values()))
        self.assertIn("| page_only | page_plus_metadata |", self.text)

    def test_free_text_blanks_dropped_and_set_equal(self):
        texts = report.free_text(self.rows, "Q2.Q")
        self.assertEqual(set(texts), EXPECTED_QUESTIONS)
        self.assertEqual(len(texts), len(EXPECTED_QUESTIONS))
        self.assertIn("6 answers, in random order.", self.text)
        bullets = re.findall(r"^- (.+)$", self.text, flags=re.M)
        self.assertEqual(set(bullets), EXPECTED_QUESTIONS)

    def test_consent_tags_not_reported(self):
        self.assertNotIn("Q2.P1", self.text)
        self.assertNotIn("aggregate reuse is permitted", self.text)

    def test_missing_survey_fails_plainly(self):
        with self.assertRaises(SystemExit) as ctx:
            report.select_survey(report.load_surveys(), "2", "nl", "opener")
        self.assertIn("No survey configured for 2/nl/opener", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()


class ClassViewTests(unittest.TestCase):
    def test_class_view_has_no_free_text_or_identity(self):
        import classview
        cfg = report.load_surveys()
        survey = report.select_survey(cfg, "2", "en", "opener")
        rows = report.drop_identity(report.finished_rows(report.response_rows(
            FIXTURE, set(report.content_tags(survey)))), survey["identity_tags"])
        page = classview.render_class_html(survey, rows, "test")
        self.assertIn("class=\"slide", page)
        self.assertNotIn("Fixture", page)
        for tag in survey.get("free_text", []):
            for row in rows:
                if (row.get(tag) or "").strip():
                    self.assertNotIn(row[tag].strip(), page)
