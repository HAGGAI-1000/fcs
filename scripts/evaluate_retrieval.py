#!/usr/bin/env python3
"""Run all Hebrew evaluation questions and create a ground-truth review queue."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

from retrieval_common import atomic_jsonl
from retrieval_engine import RetrievalEngine


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def ensure_relevance_template(path: Path, questions: list[dict]) -> list[dict]:
    fields = [
        "id",
        "expected_document_guids",
        "expected_out_of_scope",
        "review_status",
        "reference_answer_he",
        "review_notes",
    ]
    if not path.exists():
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for question in questions:
                writer.writerow({"id": question["id"], "review_status": "pending"})
    rows = read_csv(path)
    if [row["id"] for row in rows] != [row["id"] for row in questions]:
        raise ValueError("Evaluation relevance rows must match the 50 question IDs in order")
    return rows


def compact(row: dict, score: float, rank: int) -> dict:
    return {
        "rank": rank,
        "score": score,
        "chunk_id": row["chunk_id"],
        "document_guid": row["document_guid"],
        "document_name": row.get("document_name"),
        "category": row.get("category"),
        "page_start": row.get("page_start"),
        "page_end": row.get("page_end"),
        "source_catalogue_url": row.get("source_catalogue_url"),
        "needs_ocr_review": row.get("needs_ocr_review"),
        "preview": row.get("text", "")[:280],
    }


def unique_documents(results: list[tuple[dict, float]], limit: int) -> list[str]:
    seen = []
    for row, _score in results:
        guid = row["document_guid"]
        if guid not in seen:
            seen.append(guid)
        if len(seen) == limit:
            break
    return seen


def labelled_metrics(records: list[dict], labels: dict[str, dict], mode: str) -> dict | None:
    labelled = []
    for record in records:
        label = labels[record["id"]]
        expected = {
            value.strip()
            for value in label.get("expected_document_guids", "").replace(",", ";").split(";")
            if value.strip()
        }
        if label.get("review_status") == "approved" and expected:
            labelled.append((record, expected))
    if not labelled:
        return None
    hits = 0
    reciprocal_ranks = []
    for record, expected in labelled:
        ranked = []
        for result in record[mode]:
            guid = result["document_guid"]
            if guid not in ranked:
                ranked.append(guid)
        rank = next((index for index, guid in enumerate(ranked, start=1) if guid in expected), None)
        hits += rank is not None and rank <= 5
        reciprocal_ranks.append(0.0 if rank is None else 1.0 / rank)
    return {
        "labelled_questions": len(labelled),
        "document_recall_at_5": hits / len(labelled),
        "document_mrr_at_10": sum(reciprocal_ranks) / len(labelled),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project_root.resolve()
    engine = RetrievalEngine(root)
    questions = read_csv(root / Path(engine.config["inputs"]["evaluation_questions"]))
    if len(questions) != 50:
        raise ValueError(f"Expected 50 evaluation questions, found {len(questions)}")
    if any(row.get("language") != "he" for row in questions):
        raise ValueError("Every evaluation question must have language=he")
    labels_path = root / "data" / "metadata" / "eval_relevance.csv"
    label_rows = ensure_relevance_template(labels_path, questions)
    labels = {row["id"]: row for row in label_rows}

    records = []
    top1_agreement = 0
    overlaps = []
    top_k = int(engine.config["retrieval"]["top_k"])
    for number, question in enumerate(questions, start=1):
        print(f"Evaluating {number}/50: {question['id']}", flush=True)
        bm25 = engine.search(question["question"], "bm25", top_k)
        dense = engine.search(question["question"], "dense", top_k)
        hybrid = engine.search(question["question"], "hybrid", top_k)
        bm_docs = set(unique_documents(bm25, 5))
        dense_docs = set(unique_documents(dense, 5))
        overlaps.append(len(bm_docs & dense_docs) / len(bm_docs | dense_docs) if bm_docs | dense_docs else 0.0)
        if bm25 and dense and bm25[0][0]["document_guid"] == dense[0][0]["document_guid"]:
            top1_agreement += 1
        records.append(
            {
                "evaluated_at": now(),
                "scope_id": engine.config["scope_id"],
                **question,
                "bm25": [compact(row, score, rank) for rank, (row, score) in enumerate(bm25, 1)],
                "dense": [compact(row, score, rank) for rank, (row, score) in enumerate(dense, 1)],
                "hybrid": [compact(row, score, rank) for rank, (row, score) in enumerate(hybrid, 1)],
            }
        )

    output_path = root / "data" / "processed" / "retrieval_candidates.jsonl"
    atomic_jsonl(output_path, records)
    review_path = root / "data" / "processed" / "eval_candidate_review.csv"
    with review_path.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["שאלה", "שם_מסמך_מוצע", "עמודים_מוצעים", "כתובת_FCS"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            pooled = {}
            for mode in ["bm25", "dense", "hybrid"]:
                for result in record[mode][:5]:
                    entry = pooled.setdefault(
                        result["document_guid"],
                        {
                            "document_name": result["document_name"],
                            "pages": set(),
                            "source_catalogue_url": result["source_catalogue_url"],
                        },
                    )
                    entry["pages"].add(f"{result['page_start']}-{result['page_end']}")
            for result in sorted(pooled.values(), key=lambda value: (value["document_name"] or "").casefold()):
                writer.writerow(
                    {
                        "שאלה": record["question"],
                        "שם_מסמך_מוצע": result["document_name"],
                        "עמודים_מוצעים": ";".join(sorted(result["pages"])),
                        "כתובת_FCS": result["source_catalogue_url"],
                    }
                )

    metrics = {mode: labelled_metrics(records, labels, mode) for mode in ["bm25", "dense", "hybrid"]}
    approved = sum(row.get("review_status") == "approved" for row in label_rows)
    report = [
        "# Phase 2B retrieval diagnostic",
        "",
        f"Run at: {now()}",
        "",
        f"- Hebrew questions executed: {len(records)}",
        f"- Questions with approved relevance review: {approved}",
        f"- BM25/dense top-result document agreement: {top1_agreement}/{len(records)}",
        f"- Mean BM25/dense top-5 document Jaccard overlap: {statistics.mean(overlaps):.3f}",
        f"- Candidate results: `data/processed/retrieval_candidates.jsonl`",
        f"- Unranked second-pass candidate pool: `data/processed/eval_candidate_review.csv`",
        f"- Relevance labels: `data/metadata/eval_relevance.csv`",
        "",
        "## Ground-truth metrics",
        "",
    ]
    if not any(metrics.values()):
        report.extend(
            [
                "Recall and MRR are intentionally not reported yet. The evaluation questions do not have independently reviewed expected documents, and treating retrieval output as its own ground truth would produce invalid metrics.",
                "",
            ]
        )
    else:
        report.extend(["| Retriever | Labelled questions | Recall@5 | MRR@10 |", "|---|---:|---:|---:|"])
        for mode, values in metrics.items():
            if values:
                report.append(
                    f"| {mode} | {values['labelled_questions']} | {values['document_recall_at_5']:.3f} | {values['document_mrr_at_10']:.3f} |"
                )
        report.append("")
    report.extend(
        [
            "The current dense model is a lightweight local baseline, not a production model selection. Complete relevance review before comparing retrievers or tuning fusion weights.",
            "",
        ]
    )
    report_path = root / "reports" / "retrieval_evaluation.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {output_path}")
    print(f"Wrote {review_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
