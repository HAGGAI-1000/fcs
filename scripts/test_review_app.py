#!/usr/bin/env python3
"""Dependency-free checks for the static Hebrew expert-review application."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReviewAppTests(unittest.TestCase):
    def test_static_questions_match_canonical_json(self) -> None:
        canonical = json.loads(
            (ROOT / "data" / "metadata" / "eval_questions.json").read_text(
                encoding="utf-8"
            )
        )
        static = json.loads((ROOT / "review_app" / "questions.json").read_text(encoding="utf-8"))
        self.assertEqual(len(static), 50)
        self.assertEqual(
            [(row["id"], row["question"], row["category"], row["risk_level"]) for row in static],
            [(row["id"], row["question"], row["category"], row["risk_level"]) for row in canonical],
        )

    def test_page_is_hebrew_rtl_and_backend_free(self) -> None:
        html = (ROOT / "review_app" / "index.html").read_text(encoding="utf-8")
        self.assertIn('lang="he" dir="rtl"', html)
        self.assertIn('id="add-source"', html)
        self.assertIn('id="save-question"', html)
        self.assertIn('id="export-review"', html)
        self.assertIn('id="import-review"', html)
        self.assertIn('href="styles.css?v=4"', html)
        self.assertIn('src="app.js?v=4"', html)
        self.assertIn("הנחיות למילוי השאלון", html)
        self.assertIn("האם נמצאו מקורות בפורטל שירות המזון?", html)
        self.assertIn('id="answer-label"', html)
        self.assertIn('placeholder="תשובה קצרה, משפט או שניים"', html)
        self.assertIn('placeholder="אי-בהירות, סתירות, תלות בתאריך או הערות אחרות"', html)
        self.assertLess(html.index('id="sources-list"'), html.index('id="reference-answer"'))
        self.assertNotIn('id="risk-badge"', html)
        self.assertNotIn('id="open-recovery"', html)
        self.assertNotIn('id="recovery-dialog"', html)
        self.assertNotIn("תוצאת הבדיקה", html)
        self.assertNotIn("תשובת ייחוס בעברית", html)
        self.assertNotIn("הערות בדיקה", html)
        self.assertNotIn("יש למלא שורה נפרדת", html)
        self.assertNotIn("גרסאות והעברת תוצאות", html)
        self.assertNotIn("<footer", html)
        self.assertNotIn('id="review-status"', html)
        self.assertNotIn('id="validate-all"', html)
        self.assertNotIn('id="reset-all"', html)
        self.assertNotIn('id="export-questions"', html)
        self.assertNotIn('id="export-sources"', html)
        self.assertNotIn("<form", html.lower())

    def test_canonical_json_schema_and_local_storage_are_declared(self) -> None:
        script = (ROOT / "review_app" / "app.js").read_text(encoding="utf-8")
        for field in [
            "schema_version",
            "question_id",
            "question_text_he",
            "outcome",
            "review_status",
            "reference_answer_he",
            "review_notes",
            "sources",
            "document_title",
            "relevant_pages",
            "publication_or_update_date",
            "fcs_url",
            "source_notes",
        ]:
            self.assertIn(field, script)
        self.assertIn('"eval_relevance_expert.json"', script)
        self.assertIn("localStorage", script)
        self.assertIn("indexedDB", script)
        self.assertIn('const SNAPSHOT_LIMIT = 20;', script)
        self.assertIn('createSnapshot("question_saved"', script)
        self.assertIn('createSnapshot("import"', script)
        self.assertNotIn('createSnapshot("before_restore"', script)
        self.assertIn("fcs.health.gov.il", script)

    def test_user_facing_result_file_terms_are_format_neutral(self) -> None:
        html = (ROOT / "review_app" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "review_app" / "app.js").read_text(encoding="utf-8")
        self.assertIn("ייצוא קובץ תוצאות", html)
        self.assertIn("ייבוא קובץ תוצאות", html)
        self.assertNotIn("קובץ JSON", html)
        self.assertNotIn("קובץ ה-JSON", script)

    def test_canonical_json_template_matches_questions(self) -> None:
        payload = json.loads(
            (ROOT / "data" / "metadata" / "eval_relevance_expert.json").read_text(
                encoding="utf-8"
            )
        )
        questions = json.loads(
            (ROOT / "data" / "metadata" / "eval_questions.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["question_count"], 50)
        self.assertEqual(len(payload["reviews"]), 50)
        self.assertTrue(all(isinstance(row["sources"], list) for row in payload["reviews"]))
        self.assertEqual(
            [(row["question_id"], row["question_text_he"]) for row in payload["reviews"]],
            [(row["id"], row["question"]) for row in questions],
        )

    def test_revised_questions_do_not_depend_on_missing_product_context(self) -> None:
        questions = json.loads(
            (ROOT / "data" / "metadata" / "eval_questions.json").read_text(
                encoding="utf-8"
            )
        )
        revised_ids = {"Q009", "Q030", "Q032", "Q036", "Q040", "Q043", "Q049"}
        revised = {row["id"]: row["question"] for row in questions if row["id"] in revised_ids}
        self.assertEqual(set(revised), revised_ids)
        for question in revised.values():
            for ambiguous_phrase in ["מוצר זה", "אותו מוצר", "סוג מזון זה", "המזהם", "בבקשתי"]:
                self.assertNotIn(ambiguous_phrase, question)

    def test_active_evaluation_files_are_json_only(self) -> None:
        metadata = ROOT / "data" / "metadata"
        self.assertTrue((metadata / "eval_questions.json").is_file())
        self.assertTrue((metadata / "eval_relevance_expert.json").is_file())
        self.assertFalse((metadata / "eval_questions.csv").exists())
        self.assertFalse((metadata / "eval_relevance.csv").exists())
        evaluator = (ROOT / "scripts" / "evaluate_retrieval.py").read_text(encoding="utf-8")
        self.assertNotIn("eval_candidate_review", evaluator)

    def test_pages_workflow_has_required_permissions(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("pages: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("review_app", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
