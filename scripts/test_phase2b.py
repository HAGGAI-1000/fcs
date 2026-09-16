#!/usr/bin/env python3
"""Dependency-light regression checks for Phase 2B retrieval utilities."""

from __future__ import annotations

import unittest

from import_expert_relevance import match_document, normalize_date, normalize_title
from retrieval_common import BM25Index, normalize_for_search, reciprocal_rank_fusion, tokenize


class RetrievalUtilityTests(unittest.TestCase):
    def test_hebrew_tokenization(self) -> None:
        self.assertEqual(tokenize("ייבוא מזון, לישראל!"), ["ייבוא", "מזון", "לישראל"])

    def test_unicode_normalization(self) -> None:
        self.assertEqual(normalize_for_search("ABC  123"), "abc 123")

    def test_bm25_prefers_matching_hebrew_chunk(self) -> None:
        rows = [
            {"chunk_id": "a", "text": "אישור יבוא מזון רגיש"},
            {"chunk_id": "b", "text": "בדיקות מעבדה למים"},
        ]
        self.assertEqual(BM25Index(rows).search("מזון רגיש", 1)[0][0]["chunk_id"], "a")

    def test_rrf_rewards_shared_result(self) -> None:
        a = {"chunk_id": "a"}
        b = {"chunk_id": "b"}
        c = {"chunk_id": "c"}
        fused = reciprocal_rank_fusion([[(a, 3.0), (b, 2.0)], [(c, 0.9), (a, 0.8)]], 3, 60)
        self.assertEqual(fused[0][0]["chunk_id"], "a")

    def test_expert_title_normalization_handles_hebrew_punctuation(self) -> None:
        self.assertEqual(normalize_title('מסמך “בדיקה” - 2026.pdf'), normalize_title("מסמך בדיקה 2026 PDF"))

    def test_expert_date_normalization(self) -> None:
        self.assertEqual(normalize_date("16/09/2026"), "2026-09-16")

    def test_expert_source_maps_unique_document_name(self) -> None:
        documents = [
            {
                "guid": "guid-1",
                "document_name": "הנחיות ליבוא מזון",
                "file_name": "instructions.pdf",
                "item_title": "יבוא מזון",
                "issue_date": "2026-09-16T00:00:00",
            }
        ]
        source = {
            "document_title": "הנחיות ליבוא מזון",
            "publication_or_update_date": "2026-09-16",
            "fcs_url": "https://fcs.health.gov.il/publicationsCategories/0",
        }
        self.assertEqual(match_document(source, documents)["guid"], "guid-1")

    def test_expert_source_rejects_non_fcs_url(self) -> None:
        documents = [{"guid": "guid-1", "document_name": "מסמך", "issue_date": ""}]
        source = {
            "document_title": "מסמך",
            "publication_or_update_date": "",
            "fcs_url": "https://example.com/document",
        }
        with self.assertRaisesRegex(ValueError, "outside the approved FCS host"):
            match_document(source, documents)


if __name__ == "__main__":
    unittest.main(verbosity=2)
