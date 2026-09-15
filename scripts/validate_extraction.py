#!/usr/bin/env python3
"""Validate page-level extraction outputs against the FCS download manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
    return rows


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    root = args.project_root.resolve()
    source_path = root / "data" / "metadata" / "fcs_document_downloads.json"
    extraction_path = root / "data" / "metadata" / "extraction_manifest.json"
    documents_path = root / "data" / "processed" / "fcs_documents.jsonl"
    pages_path = root / "data" / "processed" / "fcs_pages.jsonl"
    source_manifest = json.loads(source_path.read_text(encoding="utf-8"))
    extraction_manifest = json.loads(extraction_path.read_text(encoding="utf-8"))
    documents = read_jsonl(documents_path)
    pages = read_jsonl(pages_path)
    failures: list[str] = []
    warnings: list[str] = []

    scope_id = source_manifest.get("scope_id")
    if extraction_manifest.get("scope_id") != scope_id:
        failures.append("Extraction manifest scope does not match the source manifest")
    if extraction_manifest.get("input_manifest_sha256") != sha256_file(source_path):
        failures.append("Extraction manifest input checksum is stale")

    source_by_guid = {row.get("guid"): row for row in source_manifest.get("documents", [])}
    document_by_guid = {row.get("document_guid"): row for row in documents}
    if len(source_by_guid) != len(source_manifest.get("documents", [])):
        failures.append("Source manifest contains duplicate document GUIDs")
    if len(document_by_guid) != len(documents):
        failures.append("Extraction output contains duplicate document GUIDs")
    missing_documents = sorted(set(source_by_guid) - set(document_by_guid))
    extra_documents = sorted(set(document_by_guid) - set(source_by_guid))
    if missing_documents:
        failures.append(f"Missing extracted documents: {missing_documents}")
    if extra_documents:
        failures.append(f"Unexpected extracted documents: {extra_documents}")

    pages_by_guid: dict[str, list[dict]] = defaultdict(list)
    seen_page_keys: set[tuple[str, int]] = set()
    for row in pages:
        guid = row.get("document_guid")
        page_number = row.get("page_number")
        key = (guid, page_number)
        if key in seen_page_keys:
            failures.append(f"Duplicate page record: {key}")
        seen_page_keys.add(key)
        pages_by_guid[guid].append(row)
        if guid not in source_by_guid:
            failures.append(f"Page belongs to an unknown document: {guid}")
        if row.get("scope_id") != scope_id:
            failures.append(f"Page has incorrect scope: {key}")
        text = row.get("text", "")
        expected_text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if row.get("text_sha256") != expected_text_hash:
            failures.append(f"Page text checksum mismatch: {key}")
        should_need_ocr = row.get("quality_state") in {"empty", "low_text", "extraction_error"}
        if bool(row.get("needs_ocr")) != should_need_ocr:
            failures.append(f"OCR flag is inconsistent with quality state: {key}")

    for guid, source in source_by_guid.items():
        document = document_by_guid.get(guid)
        if not document:
            continue
        source_file = root / Path(source["saved_path"])
        if not source_file.is_file():
            failures.append(f"Source file is missing: {guid}")
        else:
            if source_file.stat().st_size != int(source["bytes"]):
                failures.append(f"Source byte count mismatch: {guid}")
            if sha256_file(source_file) != source.get("sha256"):
                failures.append(f"Source checksum mismatch: {guid}")
        if document.get("status") == "error":
            failures.append(f"Document extraction failed: {guid}: {document.get('error')}")
            continue
        document_pages = sorted(pages_by_guid.get(guid, []), key=lambda row: row["page_number"])
        expected_page_count = int(document.get("page_count", 0))
        if len(document_pages) != expected_page_count:
            failures.append(
                f"Page count mismatch for {guid}: expected {expected_page_count}, got {len(document_pages)}"
            )
        expected_numbers = list(range(1, expected_page_count + 1))
        actual_numbers = [row["page_number"] for row in document_pages]
        if actual_numbers != expected_numbers:
            failures.append(f"Page sequence is incomplete for {guid}")
        if document.get("pages_needing_ocr"):
            warnings.append(
                f"{guid} has {len(document['pages_needing_ocr'])} page(s) requiring OCR review"
            )

    quality_counts = Counter(row.get("quality_state") for row in pages)
    result = {
        "validated_at": now(),
        "scope_id": scope_id,
        "source_documents": len(source_by_guid),
        "extracted_documents": len(document_by_guid),
        "extracted_pages": len(pages),
        "pages_needing_ocr": sum(bool(row.get("needs_ocr")) for row in pages),
        "quality_states": dict(quality_counts),
        "failures": failures,
        "warnings": warnings,
        "status": "passed" if not failures else "failed",
    }
    output_path = root / "data" / "metadata" / "extraction_validation.json"
    atomic_json(output_path, result)

    report_lines = [
        "# FCS extraction validation",
        "",
        f"Run at: {result['validated_at']}",
        "",
        f"- Status: {result['status']}",
        f"- Source documents: {result['source_documents']}",
        f"- Extracted documents: {result['extracted_documents']}",
        f"- Extracted pages: {result['extracted_pages']}",
        f"- Pages requiring OCR review: {result['pages_needing_ocr']}",
        f"- Validation failures: {len(failures)}",
        f"- OCR warnings: {len(warnings)}",
        "",
    ]
    if failures:
        report_lines.extend(["## Failures", ""] + [f"- {failure}" for failure in failures] + [""])
    report_lines.extend(
        [
            "OCR warnings do not fail structural validation. They identify pages that need visual review or an OCR pass before indexing.",
            "",
        ]
    )
    report_path = root / "reports" / "extraction_validation.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Wrote {output_path}: {result['status']}")
    print(f"Wrote {report_path}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
