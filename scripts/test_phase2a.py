#!/usr/bin/env python3
"""Small dependency-free regression suite for Phase 2A content triage."""

from __future__ import annotations

import unittest

from collect_referenced_sources import assess_payload
from extract_documents import normalize_text, position_aware_text, quality_state, text_metrics


class PayloadAssessmentTests(unittest.TestCase):
    def test_empty_body_is_not_ingestible(self) -> None:
        self.assertEqual(assess_payload("text/html", b"")[0], "invalid_content")

    def test_aws_challenge_is_not_ingestible(self) -> None:
        html = b'<html><div id="challenge-container"></div></html>'
        self.assertEqual(assess_payload("text/html", html)[0], "blocked_content_challenge")

    def test_pdf_signature_is_accepted(self) -> None:
        self.assertEqual(assess_payload("application/pdf", b"%PDF-1.7\n")[0], "downloaded")

    def test_false_pdf_is_rejected(self) -> None:
        self.assertEqual(assess_payload("application/pdf", b"<html></html>")[0], "invalid_content")


class TextQualityTests(unittest.TestCase):
    def test_substantial_arabic_is_not_sent_to_ocr(self) -> None:
        metrics = text_metrics("هذا نص عربي واضح ومفيد لاختبار استخراج المستندات بدون تشغيل التعرف الضوئي")
        self.assertGreater(metrics["arabic_characters"], 20)
        self.assertEqual(quality_state(metrics, None), ("native_text_non_hebrew", False))

    def test_substantial_hebrew_is_native_text(self) -> None:
        metrics = text_metrics("זהו טקסט עברי ברור ושימושי לבדיקת חילוץ מסמכים ללא צורך בזיהוי אופטי")
        self.assertEqual(quality_state(metrics, None), ("native_text", False))

    def test_sparse_page_requires_review(self) -> None:
        metrics = text_metrics("כותרת 13")
        self.assertEqual(quality_state(metrics, None), ("low_text", True))

    def test_normalization_removes_control_characters(self) -> None:
        self.assertEqual(normalize_text("abc\x00\n\n\nxyz"), "abc\n\nxyz")

    def test_position_aware_extraction_orders_hebrew_right_to_left(self) -> None:
        class FakePage:
            def get_text(self, mode: str, sort: bool = False):
                self.assert_mode = (mode, sort)
                return [
                    (10, 0, 20, 10, "מזון", 0, 0, 0),
                    (30, 0, 40, 10, "יבוא", 0, 0, 1),
                ]

        self.assertEqual(position_aware_text(FakePage()), "יבוא מזון")


if __name__ == "__main__":
    unittest.main(verbosity=2)
