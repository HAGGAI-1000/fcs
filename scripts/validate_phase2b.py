#!/usr/bin/env python3
"""Validate Phase 2B chunks, persisted index, and evaluation outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from import_expert_relevance import convert_review
from retrieval_common import atomic_json, read_jsonl


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project_root.resolve()
    failures: list[str] = []
    warnings: list[str] = []

    config = json.loads((root / "config" / "retrieval.json").read_text(encoding="utf-8"))
    scope_id = config.get("scope_id")
    if config.get("application_language") != "he":
        failures.append("Application interaction language must be Hebrew")

    pages_path = root / Path(config["inputs"]["pages"])
    chunks_path = root / "data" / "processed" / "fcs_chunks.jsonl"
    chunk_manifest = json.loads((root / "data" / "metadata" / "chunk_manifest.json").read_text(encoding="utf-8"))
    chunks = read_jsonl(chunks_path)
    if chunk_manifest.get("scope_id") != scope_id:
        failures.append("Chunk manifest scope mismatch")
    if chunk_manifest.get("input_sha256") != sha256_file(pages_path):
        failures.append("Chunk input checksum is stale")
    if chunk_manifest.get("output_sha256") != sha256_file(chunks_path):
        failures.append("Chunk output checksum mismatch")
    if chunk_manifest.get("chunks") != len(chunks):
        failures.append("Chunk count does not match manifest")

    source_manifest = json.loads(
        (root / "data" / "metadata" / "fcs_document_downloads.json").read_text(encoding="utf-8")
    )
    source_hashes = {row["guid"]: row["sha256"] for row in source_manifest.get("documents", [])}
    chunk_ids = set()
    for row in chunks:
        chunk_id = row.get("chunk_id")
        if chunk_id in chunk_ids:
            failures.append(f"Duplicate chunk ID: {chunk_id}")
        chunk_ids.add(chunk_id)
        if row.get("scope_id") != scope_id:
            failures.append(f"Chunk scope mismatch: {chunk_id}")
        if not row.get("text", "").strip():
            failures.append(f"Empty chunk: {chunk_id}")
        if int(row.get("page_start", 0)) < 1 or int(row.get("page_end", 0)) < int(row.get("page_start", 0)):
            failures.append(f"Invalid page range: {chunk_id}")
        if source_hashes.get(row.get("document_guid")) != row.get("source_sha256"):
            failures.append(f"Source checksum/provenance mismatch: {chunk_id}")
        host = (urlparse(row.get("source_catalogue_url", "")).hostname or "").lower()
        if host != "fcs.health.gov.il":
            failures.append(f"Chunk source is outside FCS scope: {chunk_id}")

    index_manifest_path = root / "data" / "metadata" / "index_manifest.json"
    index_manifest = json.loads(index_manifest_path.read_text(encoding="utf-8"))
    if index_manifest.get("scope_id") != scope_id:
        failures.append("Index manifest scope mismatch")
    if index_manifest.get("chunks_sha256") != sha256_file(chunks_path):
        failures.append("Persisted index is stale")
    if index_manifest.get("dense_model") != config["retrieval"]["dense_model"]:
        failures.append("Persisted index model mismatch")
    index_dir = root / Path(index_manifest["dense_index"])
    for name in ["docstore.json", "index_store.json", "default__vector_store.json"]:
        if not (index_dir / name).is_file():
            failures.append(f"Missing LlamaIndex storage file: {name}")

    questions = read_csv(root / Path(config["inputs"]["evaluation_questions"]))
    labels = read_csv(root / "data" / "metadata" / "eval_relevance.csv")
    candidates = read_jsonl(root / "data" / "processed" / "retrieval_candidates.jsonl")
    question_ids = [row.get("id") for row in questions]
    if len(questions) != 50 or len(set(question_ids)) != 50:
        failures.append("Evaluation set must contain 50 unique questions")
    for row in questions:
        if row.get("language") != "he" or not re.search(r"[\u0590-\u05ff]", row.get("question", "")):
            failures.append(f"Evaluation question is not Hebrew: {row.get('id')}")
    if [row.get("id") for row in labels] != question_ids:
        failures.append("Relevance template IDs do not match evaluation questions")
    if [row.get("id") for row in candidates] != question_ids:
        failures.append("Retrieval candidate IDs do not match evaluation questions")
    try:
        _expert_rows, expert_summary = convert_review(root)
        if expert_summary.get("questions") != 50:
            failures.append("Expert-review files do not contain all 50 questions")
    except (FileNotFoundError, KeyError, ValueError) as exc:
        failures.append(f"Expert-review files are invalid: {exc}")
    for record in candidates:
        for mode in ["bm25", "dense", "hybrid"]:
            results = record.get(mode, [])
            if not results:
                failures.append(f"No {mode} results for {record.get('id')}")
            for result in results:
                if result.get("chunk_id") not in chunk_ids:
                    failures.append(f"Unknown result chunk for {record.get('id')}: {result.get('chunk_id')}")

    approved = sum(row.get("review_status") == "approved" for row in labels)
    if approved == 0:
        warnings.append("No evaluation questions have domain-approved relevance labels; Recall/MRR are unavailable")
    result = {
        "validated_at": now(),
        "scope_id": scope_id,
        "chunks": len(chunks),
        "evaluation_questions": len(questions),
        "approved_relevance_labels": approved,
        "failures": failures,
        "warnings": warnings,
        "status": "passed" if not failures else "failed",
    }
    atomic_json(root / "data" / "metadata" / "phase2b_validation.json", result)
    report = [
        "# Phase 2B validation",
        "",
        f"Run at: {result['validated_at']}",
        "",
        f"- Status: {result['status']}",
        f"- Chunks: {result['chunks']}",
        f"- Hebrew evaluation questions: {result['evaluation_questions']}",
        f"- Approved relevance labels: {result['approved_relevance_labels']}",
        f"- Failures: {len(failures)}",
        f"- Warnings: {len(warnings)}",
        "",
    ]
    if failures:
        report.extend(["## Failures", "", *[f"- {value}" for value in failures], ""])
    if warnings:
        report.extend(["## Warnings", "", *[f"- {value}" for value in warnings], ""])
    report_path = root / "reports" / "phase2b_validation.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {report_path}: {result['status']}")
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
