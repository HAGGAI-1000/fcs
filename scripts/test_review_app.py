#!/usr/bin/env python3
"""Dependency-free checks for the static Hebrew expert-review application."""

from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReviewAppTests(unittest.TestCase):
    def test_static_questions_match_canonical_csv(self) -> None:
        with (ROOT / "data" / "metadata" / "eval_questions.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as stream:
            canonical = list(csv.DictReader(stream))
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
        self.assertIn('id="export-review"', html)
        self.assertIn('id="import-review"', html)
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
        self.assertIn("fcs.health.gov.il", script)

    def test_canonical_json_template_matches_questions(self) -> None:
        payload = json.loads(
            (ROOT / "data" / "metadata" / "eval_relevance_expert.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["question_count"], 50)
        self.assertEqual(len(payload["reviews"]), 50)
        self.assertTrue(all(isinstance(row["sources"], list) for row in payload["reviews"]))

    def test_pages_workflow_has_required_permissions(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("pages: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("review_app", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
