#!/usr/bin/env python3
"""Build stable, page-citable chunks from the validated Phase 2A corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from retrieval_common import atomic_json, atomic_jsonl, read_jsonl


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def words(value: str) -> list[str]:
    return re.findall(r"\S+", value)


def split_words(value: str, target: int, overlap: int) -> list[str]:
    tokens = words(value)
    if len(tokens) <= target:
        return [value.strip()] if value.strip() else []
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + target, len(tokens))
        chunks.append(" ".join(tokens[start:end]))
        if end == len(tokens):
            break
        start = end - overlap
    return chunks


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    root = args.project_root.resolve()
    config_path = root / "config" / "retrieval.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    validation_path = root / Path(config["inputs"]["extraction_validation"])
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation.get("status") != "passed" or validation.get("failures"):
        raise ValueError("Phase 2A extraction validation must pass before chunking")
    if validation.get("scope_id") != config.get("scope_id"):
        raise ValueError("Retrieval and extraction scopes do not match")

    pages_path = root / Path(config["inputs"]["pages"])
    pages = read_jsonl(pages_path)
    by_document: dict[str, list[dict]] = defaultdict(list)
    for page in pages:
        if page.get("scope_id") != config["scope_id"]:
            raise ValueError(f"Page has invalid scope: {page.get('document_guid')}")
        by_document[page["document_guid"]].append(page)

    chunking = config["chunking"]
    target = int(chunking["target_words"])
    overlap = int(chunking["overlap_words"])
    if target <= 0 or overlap < 0 or overlap >= target:
        raise ValueError("Invalid chunk target/overlap configuration")
    minimum_letters = int(chunking["minimum_letters"])
    sparse_max = int(chunking["sparse_heading_max_words"])

    output: list[dict] = []
    skipped_empty = 0
    skipped_noncontent = 0
    merged_sparse = 0
    for guid in sorted(by_document):
        document_pages = sorted(by_document[guid], key=lambda row: row["page_number"])
        pending: list[dict] = []
        document_chunk_number = 0
        for page in document_pages:
            text = page.get("text", "").strip()
            letter_count = int(page.get("letter_characters", 0))
            if not text:
                skipped_empty += 1
                continue
            page_words = words(text)
            is_sparse_heading = (
                page.get("quality_state") == "low_text"
                and minimum_letters <= letter_count
                and len(page_words) <= sparse_max
            )
            if is_sparse_heading:
                pending.append(page)
                continue
            if page.get("quality_state") == "low_text" and letter_count < minimum_letters:
                skipped_noncontent += 1
                continue

            prefix = "\n".join(item["text"].strip() for item in pending if item.get("text", "").strip())
            page_numbers = [item["page_number"] for item in pending] + [page["page_number"]]
            quality_states = [item["quality_state"] for item in pending] + [page["quality_state"]]
            needs_ocr = any(bool(item.get("needs_ocr")) for item in pending) or bool(page.get("needs_ocr"))
            if pending:
                merged_sparse += len(pending)
            combined_text = f"{prefix}\n\n{text}".strip() if prefix else text
            pending = []
            for part in split_words(combined_text, target, overlap):
                document_chunk_number += 1
                title = page.get("document_name") or page.get("file_name") or page.get("item_title") or guid
                embedding_text = "\n".join(
                    value for value in [title, page.get("item_title"), page.get("category"), part] if value
                )
                identity = "|".join(
                    [page["source_sha256"], str(min(page_numbers)), str(max(page_numbers)), str(document_chunk_number), part]
                )
                chunk_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
                output.append(
                    {
                        "scope_id": config["scope_id"],
                        "chunk_id": chunk_id,
                        "document_guid": guid,
                        "document_name": page.get("document_name"),
                        "file_name": page.get("file_name"),
                        "item_title": page.get("item_title"),
                        "category": page.get("category"),
                        "issue_date": page.get("issue_date"),
                        "page_start": min(page_numbers),
                        "page_end": max(page_numbers),
                        "source_catalogue_url": page.get("source_catalogue_url"),
                        "source_path": page.get("source_path"),
                        "source_sha256": page.get("source_sha256"),
                        "extraction_method": page.get("extraction_method"),
                        "quality_states": sorted(set(quality_states)),
                        "needs_ocr_review": needs_ocr,
                        "word_count": len(words(part)),
                        "text_sha256": hashlib.sha256(part.encode("utf-8")).hexdigest(),
                        "text": part,
                        "embedding_text": embedding_text,
                    }
                )
        if pending:
            for sparse_page in pending:
                if int(sparse_page.get("letter_characters", 0)) < minimum_letters:
                    skipped_noncontent += 1
                    continue
                document_chunk_number += 1
                part = sparse_page["text"].strip()
                title = sparse_page.get("document_name") or sparse_page.get("file_name") or guid
                identity = "|".join(
                    [sparse_page["source_sha256"], str(sparse_page["page_number"]), str(document_chunk_number), part]
                )
                output.append(
                    {
                        "scope_id": config["scope_id"],
                        "chunk_id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32],
                        "document_guid": guid,
                        "document_name": sparse_page.get("document_name"),
                        "file_name": sparse_page.get("file_name"),
                        "item_title": sparse_page.get("item_title"),
                        "category": sparse_page.get("category"),
                        "issue_date": sparse_page.get("issue_date"),
                        "page_start": sparse_page["page_number"],
                        "page_end": sparse_page["page_number"],
                        "source_catalogue_url": sparse_page.get("source_catalogue_url"),
                        "source_path": sparse_page.get("source_path"),
                        "source_sha256": sparse_page.get("source_sha256"),
                        "extraction_method": sparse_page.get("extraction_method"),
                        "quality_states": [sparse_page["quality_state"]],
                        "needs_ocr_review": True,
                        "word_count": len(words(part)),
                        "text_sha256": hashlib.sha256(part.encode("utf-8")).hexdigest(),
                        "text": part,
                        "embedding_text": "\n".join(value for value in [title, sparse_page.get("item_title"), sparse_page.get("category"), part] if value),
                    }
                )

    chunk_ids = [row["chunk_id"] for row in output]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("Chunk identifiers are not unique")
    output_path = root / "data" / "processed" / "fcs_chunks.jsonl"
    atomic_jsonl(output_path, output)
    manifest = {
        "built_at": now(),
        "scope_id": config["scope_id"],
        "config": "config/retrieval.json",
        "config_sha256": sha256_file(config_path),
        "input": config["inputs"]["pages"],
        "input_sha256": sha256_file(pages_path),
        "output": "data/processed/fcs_chunks.jsonl",
        "output_sha256": sha256_file(output_path),
        "source_documents": len(by_document),
        "source_pages": len(pages),
        "chunks": len(output),
        "chunks_requiring_ocr_review": sum(bool(row["needs_ocr_review"]) for row in output),
        "skipped_empty_pages": skipped_empty,
        "skipped_noncontent_low_text_pages": skipped_noncontent,
        "merged_sparse_pages": merged_sparse,
        "quality_states": dict(Counter(state for row in output for state in row["quality_states"])),
    }
    manifest_path = root / "data" / "metadata" / "chunk_manifest.json"
    atomic_json(manifest_path, manifest)
    report = [
        "# FCS chunking quality",
        "",
        f"Run at: {manifest['built_at']}",
        "",
        f"- Source documents: {manifest['source_documents']}",
        f"- Source pages: {manifest['source_pages']}",
        f"- Chunks: {manifest['chunks']}",
        f"- Chunks carrying an OCR-review flag: {manifest['chunks_requiring_ocr_review']}",
        f"- Empty pages excluded: {manifest['skipped_empty_pages']}",
        f"- Non-content low-text pages excluded: {manifest['skipped_noncontent_low_text_pages']}",
        f"- Sparse pages merged with following content: {manifest['merged_sparse_pages']}",
        "",
        "Every chunk retains its source document checksum and page range. No external source without an ingestible FCS-provenance record is included.",
        "",
    ]
    report_path = root / "reports" / "chunking_quality.md"
    report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {output_path} with {len(output)} chunks")
    print(f"Wrote {manifest_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
