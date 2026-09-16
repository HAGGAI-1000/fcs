#!/usr/bin/env python3
"""Map a completed Hebrew expert review to the compact evaluation-label CSV."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from prepare_expert_review import (
    ALLOWED_OUTCOMES,
    ALLOWED_STATUSES,
    OUTCOME_FOUND,
    OUTCOME_NOT_FOUND,
    OUTCOME_NOT_REVIEWED,
    OUTCOME_OUTSIDE,
    OUTCOME_UNCERTAIN,
    QUESTION_FIELDS,
    SOURCE_FIELDS,
    STATUS_APPROVED,
    STATUS_PENDING,
)


OUTPUT_FIELDS = [
    "id",
    "expected_document_guids",
    "expected_out_of_scope",
    "review_status",
    "reference_answer_he",
    "review_notes",
]


def read_csv(path: Path, expected_fields: list[str] | None = None) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        if expected_fields is not None and fields != expected_fields:
            raise ValueError(f"Unexpected columns in {path}: {fields}")
        return list(reader)


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"[\u05f3\u05f4'\"`´‘’“”.,:;()\[\]{}_/\\–—-]+", " ", value)
    return " ".join(value.split())


def normalize_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    for pattern in ["%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"]:
        try:
            return datetime.strptime(value[:10], pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {value!r}; use YYYY-MM-DD")


def document_aliases(document: dict) -> set[str]:
    aliases = set()
    for field in ["document_name", "file_name", "item_title"]:
        value = (document.get(field) or "").strip()
        if value:
            aliases.add(normalize_title(value))
            if value.lower().endswith(".pdf"):
                aliases.add(normalize_title(value[:-4]))
    return aliases


def match_document(source: dict, documents: list[dict]) -> dict:
    title = (source.get("שם_המסמך_באתר_FCS") or "").strip()
    if not title:
        raise ValueError("Missing FCS document title")
    title_key = normalize_title(title)
    candidates = [document for document in documents if title_key in document_aliases(document)]

    date_value = normalize_date(source.get("תאריך_פרסום_או_עדכון", ""))
    if date_value:
        candidates = [document for document in candidates if (document.get("issue_date") or "")[:10] == date_value]

    url = (source.get("כתובת_FCS") or "").strip()
    if url:
        host = (urlparse(url).hostname or "").lower()
        if host != "fcs.health.gov.il":
            raise ValueError(f"Source URL is outside the approved FCS host: {url}")

    if not candidates:
        raise ValueError(f"No crawled FCS document matches title/date: {title!r}, {date_value or 'no date'}")
    if len(candidates) > 1:
        descriptions = "; ".join(
            f"{row.get('document_name')} [{row.get('guid')}]" for row in candidates
        )
        raise ValueError(f"Ambiguous FCS document title; provide the exact document name and date: {descriptions}")
    return candidates[0]


def source_has_details(row: dict) -> bool:
    return any((row.get(field) or "").strip() for field in SOURCE_FIELDS[1:])


def source_audit_note(source: dict, document: dict) -> str:
    parts = [f"מקור: {source['שם_המסמך_באתר_FCS']}"]
    if source.get("עמודים_רלוונטיים"):
        parts.append(f"עמודים: {source['עמודים_רלוונטיים']}")
    if source.get("תאריך_פרסום_או_עדכון"):
        parts.append(f"תאריך: {source['תאריך_פרסום_או_עדכון']}")
    if source.get("כתובת_FCS"):
        parts.append(f"URL: {source['כתובת_FCS']}")
    parts.append(f"GUID שמופה: {document['guid']}")
    if source.get("הערות_מקור"):
        parts.append(f"הערת מקור: {source['הערות_מקור']}")
    return "; ".join(parts)


def convert_review(root: Path) -> tuple[list[dict], dict]:
    canonical = read_csv(root / "data" / "metadata" / "eval_questions.csv")
    expert_questions = read_csv(
        root / "data" / "metadata" / "eval_relevance_expert_he.csv", QUESTION_FIELDS
    )
    expert_sources = read_csv(
        root / "data" / "metadata" / "eval_relevance_expert_sources_he.csv", SOURCE_FIELDS
    )
    manifest = json.loads(
        (root / "data" / "metadata" / "fcs_document_downloads.json").read_text(encoding="utf-8")
    )
    documents = manifest.get("documents", [])
    canonical_questions = [row["question"] for row in canonical]
    if [row.get("שאלה") for row in expert_questions] != canonical_questions:
        raise ValueError("Expert question rows must exactly match the 50 canonical Hebrew questions in order")
    known_questions = set(canonical_questions)
    unknown_sources = sorted({row.get("שאלה", "") for row in expert_sources} - known_questions)
    if unknown_sources:
        raise ValueError(f"Source rows contain unknown or changed questions: {unknown_sources}")
    source_question_set = {row.get("שאלה", "") for row in expert_sources}
    missing_source_rows = [question for question in canonical_questions if question not in source_question_set]
    if missing_source_rows:
        raise ValueError("Every question must retain at least one row in the expert source file")

    sources_by_question: dict[str, list[dict]] = {question: [] for question in canonical_questions}
    for row in expert_sources:
        if source_has_details(row):
            sources_by_question[row["שאלה"]].append(row)

    output: list[dict] = []
    approved_count = 0
    mapped_source_count = 0
    out_of_scope_count = 0
    for canonical_row, expert_row in zip(canonical, expert_questions, strict=True):
        question = canonical_row["question"]
        outcome = (expert_row.get("תוצאת_הבדיקה") or "").strip()
        status = (expert_row.get("סטטוס_בדיקה") or "").strip()
        answer = (expert_row.get("תשובת_ייחוס_בעברית") or "").strip()
        notes = (expert_row.get("הערות_בדיקה") or "").strip()
        if outcome not in ALLOWED_OUTCOMES:
            raise ValueError(f"Invalid review outcome for {canonical_row['id']}: {outcome!r}")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid review status for {canonical_row['id']}: {status!r}")

        expected_guids: list[str] = []
        audit_notes: list[str] = []
        for source in sources_by_question[question]:
            if not (source.get("עמודים_רלוונטיים") or "").strip():
                raise ValueError(f"A source row for {canonical_row['id']} is missing relevant pages")
            document = match_document(source, documents)
            if document["guid"] not in expected_guids:
                expected_guids.append(document["guid"])
            audit_notes.append(source_audit_note(source, document))
            mapped_source_count += 1

        expected_out_of_scope = ""
        machine_status = "pending"
        if status == STATUS_APPROVED:
            if not answer:
                raise ValueError(f"Approved question {canonical_row['id']} is missing a Hebrew reference answer")
            if outcome == OUTCOME_FOUND:
                if not expected_guids:
                    raise ValueError(f"Approved question {canonical_row['id']} has no mapped FCS source")
                expected_out_of_scope = "false"
            elif outcome == OUTCOME_OUTSIDE:
                if expected_guids:
                    raise ValueError(f"Out-of-scope question {canonical_row['id']} must not have accepted FCS sources")
                expected_out_of_scope = "true"
                out_of_scope_count += 1
            elif outcome in {OUTCOME_NOT_FOUND, OUTCOME_UNCERTAIN, OUTCOME_NOT_REVIEWED}:
                raise ValueError(
                    f"Question {canonical_row['id']} cannot be approved with outcome {outcome!r}; keep it pending"
                )
            machine_status = "approved"
            approved_count += 1

        combined_notes = " | ".join(value for value in [notes, *audit_notes] if value)
        output.append(
            {
                "id": canonical_row["id"],
                "expected_document_guids": ";".join(expected_guids),
                "expected_out_of_scope": expected_out_of_scope,
                "review_status": machine_status,
                "reference_answer_he": answer,
                "review_notes": combined_notes,
            }
        )
    return output, {
        "questions": len(output),
        "approved": approved_count,
        "mapped_sources": mapped_source_count,
        "approved_out_of_scope": out_of_scope_count,
    }


def write_output(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8-sig", newline="", delete=False, dir=path.parent, suffix=".tmp"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        temporary = Path(stream.name)
    temporary.replace(path)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("data/metadata/eval_relevance.csv"))
    parser.add_argument("--check", action="store_true", help="Validate and map without writing the compact CSV")
    args = parser.parse_args()
    root = args.project_root.resolve()
    rows, summary = convert_review(root)
    if args.check:
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    output = args.output if args.output.is_absolute() else root / args.output
    write_output(output, rows)
    print(f"Wrote {output}")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
