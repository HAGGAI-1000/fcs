#!/usr/bin/env python3
"""Map a canonical expert-review JSON file to the compact evaluation-label CSV."""

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

OUTPUT_FIELDS = [
    "id",
    "expected_document_guids",
    "expected_out_of_scope",
    "review_status",
    "reference_answer_he",
    "review_notes",
]

REVIEW_SCHEMA_VERSION = 2
OUTCOME_NOT_REVIEWED = "not_reviewed"
OUTCOME_FOUND = "source_found"
OUTCOME_NOT_FOUND = "source_not_found"
OUTCOME_OUTSIDE = "requires_non_fcs_source"
OUTCOME_UNCERTAIN = "uncertain"
ALLOWED_OUTCOMES = {
    OUTCOME_NOT_REVIEWED,
    OUTCOME_FOUND,
    OUTCOME_NOT_FOUND,
    OUTCOME_OUTSIDE,
    OUTCOME_UNCERTAIN,
}
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
ALLOWED_STATUSES = {STATUS_PENDING, STATUS_APPROVED}


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
    title = (source.get("document_title") or "").strip()
    if not title:
        raise ValueError("Missing FCS document title")
    title_key = normalize_title(title)
    candidates = [document for document in documents if title_key in document_aliases(document)]

    date_value = normalize_date(source.get("publication_or_update_date", ""))
    if date_value:
        candidates = [document for document in candidates if (document.get("issue_date") or "")[:10] == date_value]

    url = (source.get("fcs_url") or "").strip()
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


def source_audit_note(source: dict, document: dict) -> str:
    parts = [f"מקור: {source['document_title']}"]
    if source.get("relevant_pages"):
        parts.append(f"עמודים: {source['relevant_pages']}")
    if source.get("publication_or_update_date"):
        parts.append(f"תאריך: {source['publication_or_update_date']}")
    if source.get("fcs_url"):
        parts.append(f"URL: {source['fcs_url']}")
    parts.append(f"GUID שמופה: {document['guid']}")
    if source.get("source_notes"):
        parts.append(f"הערת מקור: {source['source_notes']}")
    return "; ".join(parts)


def read_review(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported expert-review schema version: {payload.get('schema_version')!r}"
        )
    reviews = payload.get("reviews")
    if not isinstance(reviews, list):
        raise ValueError("Expert-review JSON must contain a reviews array")
    if payload.get("question_count") != len(reviews):
        raise ValueError("Expert-review question_count does not match the reviews array")
    return reviews


def convert_review(root: Path, input_path: Path | None = None) -> tuple[list[dict], dict]:
    canonical = read_csv(root / "data" / "metadata" / "eval_questions.csv")
    review_path = input_path or root / "data" / "metadata" / "eval_relevance_expert.json"
    expert_reviews = read_review(review_path)
    manifest = json.loads(
        (root / "data" / "metadata" / "fcs_document_downloads.json").read_text(encoding="utf-8")
    )
    documents = manifest.get("documents", [])
    if len(expert_reviews) != len(canonical):
        raise ValueError(
            f"Expert review must contain {len(canonical)} questions, found {len(expert_reviews)}"
        )
    for index, (canonical_row, expert_row) in enumerate(
        zip(canonical, expert_reviews, strict=True), start=1
    ):
        if expert_row.get("question_id") != canonical_row["id"]:
            raise ValueError(f"Question {index} has an unexpected compact ID")
        if expert_row.get("question_text_he") != canonical_row["question"]:
            raise ValueError(f"Question {canonical_row['id']} text does not match the canonical set")
        if not isinstance(expert_row.get("sources"), list):
            raise ValueError(f"Question {canonical_row['id']} sources must be an array")

    output: list[dict] = []
    approved_count = 0
    mapped_source_count = 0
    out_of_scope_count = 0
    for canonical_row, expert_row in zip(canonical, expert_reviews, strict=True):
        outcome = (expert_row.get("outcome") or "").strip()
        status = (expert_row.get("review_status") or "").strip()
        answer = (expert_row.get("reference_answer_he") or "").strip()
        notes = (expert_row.get("review_notes") or "").strip()
        if outcome not in ALLOWED_OUTCOMES:
            raise ValueError(f"Invalid review outcome for {canonical_row['id']}: {outcome!r}")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid review status for {canonical_row['id']}: {status!r}")

        expected_guids: list[str] = []
        audit_notes: list[str] = []
        for source in expert_row["sources"]:
            if not isinstance(source, dict):
                raise ValueError(f"A source for {canonical_row['id']} is not an object")
            if not (source.get("relevant_pages") or "").strip():
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
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/metadata/eval_relevance_expert.json"),
        help="Canonical expert-review JSON exported by the web application",
    )
    parser.add_argument("--output", type=Path, default=Path("data/metadata/eval_relevance.csv"))
    parser.add_argument("--check", action="store_true", help="Validate and map without writing the compact CSV")
    args = parser.parse_args()
    root = args.project_root.resolve()
    input_path = args.input if args.input.is_absolute() else root / args.input
    rows, summary = convert_review(root, input_path)
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
