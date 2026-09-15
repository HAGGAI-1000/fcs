#!/usr/bin/env python3
"""Extract checksum-verified FCS PDFs into page-level JSONL records."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


MIN_USEFUL_NON_WHITESPACE = 40
MIN_USEFUL_LETTERS = 20


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").replace("\r\n", "\n").replace("\r", "\n")
    value = "".join(
        character
        for character in value
        if character in {"\n", "\t"} or unicodedata.category(character) != "Cc"
    )
    value = "\n".join(line.rstrip() for line in value.splitlines())
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def is_hebrew(character: str) -> bool:
    codepoint = ord(character)
    return 0x0590 <= codepoint <= 0x05FF or 0xFB1D <= codepoint <= 0xFB4F


def is_arabic(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x0600 <= codepoint <= 0x06FF
        or 0x0750 <= codepoint <= 0x077F
        or 0x08A0 <= codepoint <= 0x08FF
        or 0xFB50 <= codepoint <= 0xFDFF
        or 0xFE70 <= codepoint <= 0xFEFF
    )


def text_metrics(text: str) -> dict:
    return {
        "character_count": len(text),
        "non_whitespace_characters": sum(not character.isspace() for character in text),
        "letter_characters": sum(unicodedata.category(character).startswith("L") for character in text),
        "hebrew_characters": sum(is_hebrew(character) for character in text),
        "arabic_characters": sum(is_arabic(character) for character in text),
        "latin_characters": sum(
            ("A" <= character <= "Z") or ("a" <= character <= "z") for character in text
        ),
        "digit_characters": sum(character.isdigit() for character in text),
    }


def quality_state(metrics: dict, extraction_error: str | None) -> tuple[str, bool]:
    if extraction_error:
        return "extraction_error", True
    if metrics["non_whitespace_characters"] == 0:
        return "empty", True
    if (
        metrics["non_whitespace_characters"] < MIN_USEFUL_NON_WHITESPACE
        or metrics["letter_characters"] < MIN_USEFUL_LETTERS
    ):
        return "low_text", True
    if metrics["hebrew_characters"] == 0:
        return "native_text_non_hebrew", False
    return "native_text", False


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def atomic_jsonl(path: Path, rows: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--limit-documents", type=int)
    args = parser.parse_args()

    try:
        import pypdf
        from pypdf import PdfReader
    except ImportError:
        print("pypdf is required. Install requirements-phase2.txt", file=sys.stderr)
        return 2

    root = args.project_root.resolve()
    policy = json.loads((root / "config" / "crawl_policy.json").read_text(encoding="utf-8"))
    input_path = root / "data" / "metadata" / "fcs_document_downloads.json"
    source_manifest = json.loads(input_path.read_text(encoding="utf-8"))
    if source_manifest.get("scope_id") != policy.get("scope_id"):
        raise ValueError("Document manifest does not match the active crawl policy")
    if source_manifest.get("errors"):
        raise ValueError("Document manifest contains unresolved download errors")

    source_documents = source_manifest.get("documents", [])
    if args.limit_documents is not None:
        source_documents = source_documents[: args.limit_documents]

    page_rows: list[dict] = []
    document_rows: list[dict] = []
    document_errors = 0
    for index, source in enumerate(source_documents, start=1):
        guid = source.get("guid")
        source_path = root / Path(source["saved_path"])
        print(f"Extracting {index}/{len(source_documents)}: {guid}", flush=True)
        base = {
            "scope_id": policy["scope_id"],
            "document_guid": guid,
            "document_name": source.get("document_name"),
            "file_name": source.get("file_name"),
            "category": source.get("category"),
            "item_title": source.get("item_title"),
            "issue_date": source.get("issue_date"),
            "source_catalogue_url": source.get("source_catalogue_url"),
            "source_path": source_path.relative_to(root).as_posix(),
            "source_sha256": source.get("sha256"),
        }
        try:
            if not source_path.is_file():
                raise FileNotFoundError(source_path)
            if source_path.stat().st_size != int(source["bytes"]):
                raise ValueError("Source byte count does not match the download manifest")
            actual_hash = sha256_file(source_path)
            if actual_hash != source.get("sha256"):
                raise ValueError("Source SHA-256 does not match the download manifest")
            reader = PdfReader(source_path, strict=False)
            if reader.is_encrypted and reader.decrypt("") == 0:
                raise ValueError("PDF is encrypted and cannot be opened without a password")
            page_count = len(reader.pages)
            document_page_rows = []
            for page_index, page in enumerate(reader.pages, start=1):
                extraction_error = None
                try:
                    text = normalize_text(page.extract_text() or "")
                except Exception as exc:
                    text = ""
                    extraction_error = f"{type(exc).__name__}: {exc}"
                metrics = text_metrics(text)
                state, needs_ocr = quality_state(metrics, extraction_error)
                row = {
                    **base,
                    "page_number": page_index,
                    "page_count": page_count,
                    "extraction_method": "pypdf_native",
                    "quality_state": state,
                    "needs_ocr": needs_ocr,
                    "extraction_error": extraction_error,
                    **metrics,
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "text": text,
                }
                page_rows.append(row)
                document_page_rows.append(row)

            states = Counter(row["quality_state"] for row in document_page_rows)
            ocr_pages = [row["page_number"] for row in document_page_rows if row["needs_ocr"]]
            document_rows.append(
                {
                    **base,
                    "status": "partial" if states.get("extraction_error") else "extracted",
                    "page_count": page_count,
                    "text_characters": sum(row["character_count"] for row in document_page_rows),
                    "hebrew_characters": sum(row["hebrew_characters"] for row in document_page_rows),
                    "pages_needing_ocr": ocr_pages,
                    "quality_states": dict(states),
                }
            )
        except Exception as exc:
            document_errors += 1
            document_rows.append(
                {
                    **base,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "page_count": 0,
                    "text_characters": 0,
                    "hebrew_characters": 0,
                    "pages_needing_ocr": [],
                    "quality_states": {},
                }
            )

    processed_dir = root / "data" / "processed"
    metadata_dir = root / "data" / "metadata"
    report_dir = root / "reports"
    processed_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    pages_path = processed_dir / "fcs_pages.jsonl"
    documents_path = processed_dir / "fcs_documents.jsonl"
    atomic_jsonl(pages_path, page_rows)
    atomic_jsonl(documents_path, document_rows)

    all_states = Counter(row["quality_state"] for row in page_rows)
    manifest = {
        "extracted_at": now(),
        "scope_id": policy["scope_id"],
        "extractor": "pypdf_native",
        "extractor_version": pypdf.__version__,
        "input_manifest": "data/metadata/fcs_document_downloads.json",
        "input_manifest_sha256": sha256_file(input_path),
        "document_output": "data/processed/fcs_documents.jsonl",
        "page_output": "data/processed/fcs_pages.jsonl",
        "documents_requested": len(source_documents),
        "documents_processed": len(source_documents) - document_errors,
        "document_errors": document_errors,
        "pages_extracted": len(page_rows),
        "pages_needing_ocr": sum(row["needs_ocr"] for row in page_rows),
        "quality_states": dict(all_states),
    }
    manifest_path = metadata_dir / "extraction_manifest.json"
    atomic_json(manifest_path, manifest)

    ocr_documents = [row for row in document_rows if row.get("pages_needing_ocr")]
    report_lines = [
        "# FCS PDF extraction quality",
        "",
        f"Run at: {manifest['extracted_at']}",
        "",
        f"- Documents requested: {manifest['documents_requested']}",
        f"- Documents processed: {manifest['documents_processed']}",
        f"- Document errors: {manifest['document_errors']}",
        f"- Pages extracted: {manifest['pages_extracted']}",
        f"- Pages flagged for OCR: {manifest['pages_needing_ocr']}",
        f"- Documents containing OCR-flagged pages: {len(ocr_documents)}",
        "",
        "## Page quality states",
        "",
        "| State | Pages |",
        "|---|---:|",
    ]
    report_lines.extend(f"| {name} | {count} |" for name, count in all_states.most_common())
    report_lines.extend(["", "## Documents requiring OCR review", ""])
    if ocr_documents:
        report_lines.extend(
            f"- `{row['document_guid']}` - pages {', '.join(map(str, row['pages_needing_ocr']))} - {row.get('file_name') or row.get('document_name')}"
            for row in ocr_documents
        )
    else:
        report_lines.append("No pages met the automatic OCR threshold.")
    report_lines.extend(
        [
            "",
            "OCR flags are triage signals, not proof that a page is scanned. Visual review is required before OCR is applied.",
            "",
        ]
    )
    report_path = report_dir / "extraction_quality.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Wrote {documents_path}")
    print(f"Wrote {pages_path}")
    print(f"Wrote {manifest_path}")
    print(f"Wrote {report_path}")
    return 1 if document_errors else 0


if __name__ == "__main__":
    sys.exit(main())
