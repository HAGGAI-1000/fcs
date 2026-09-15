#!/usr/bin/env python3
"""Classify exact external references emitted by FCS publication records."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


YOUTUBE_HOSTS = {"youtu.be", "www.youtube.com", "youtube.com", "m.youtube.com"}
EUR_LEX_HOSTS = {"eur-lex.europa.eu"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def classify(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    suffix = Path(parsed.path).suffix.lower()
    if host in EUR_LEX_HOSTS:
        return (
            "official_regulatory_web_page",
            "download_exact_html",
            "Authoritative EU legal page directly referenced by FCS",
        )
    if host in YOUTUBE_HOSTS:
        return (
            "video_landing_page",
            "metadata_only_until_transcript_strategy",
            "The HTML shell is not a reliable substitute for video or captions",
        )
    if suffix == ".pdf":
        return ("external_pdf", "download_exact_document", "Exact PDF reference")
    return ("external_web_page", "download_exact_page", "Exact public web reference")


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
    policy = json.loads((root / "config" / "crawl_policy.json").read_text(encoding="utf-8"))
    input_path = root / "data" / "metadata" / "fcs_direct_references.json"
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if payload.get("scope_id") != policy.get("scope_id"):
        raise ValueError("Direct-reference manifest does not match the active crawl policy")

    records = []
    for reference in payload.get("references", []):
        if reference.get("relationship") != "direct_fcs_publication_reference":
            raise ValueError("Reference lacks the required direct-FCS relationship")
        if not reference.get("discovered_from"):
            raise ValueError("Reference lacks FCS provenance")
        reference_type, collection_action, rationale = classify(reference.get("url", ""))
        records.append(
            {
                **reference,
                "reference_type": reference_type,
                "collection_action": collection_action,
                "classification_rationale": rationale,
            }
        )

    output = {
        "classified_at": now(),
        "scope_id": policy["scope_id"],
        "input_manifest": "data/metadata/fcs_direct_references.json",
        "input_manifest_sha256": sha256_file(input_path),
        "references": records,
    }
    output_path = root / "data" / "metadata" / "fcs_reference_classification.json"
    atomic_json(output_path, output)

    type_counts = Counter(row["reference_type"] for row in records)
    host_counts = Counter((urlparse(row["url"]).hostname or "").lower() for row in records)
    report_lines = [
        "# FCS direct-reference classification",
        "",
        f"Run at: {output['classified_at']}",
        "",
        f"- References classified: {len(records)}",
        f"- Eligible under crawl policy: {sum(bool(row.get('eligible_for_collection')) for row in records)}",
        "",
        "## Reference types",
        "",
        "| Type | Count |",
        "|---|---:|",
    ]
    report_lines.extend(f"| {name} | {count} |" for name, count in type_counts.most_common())
    report_lines.extend(["", "## Hosts", "", "| Host | Count |", "|---|---:|"])
    report_lines.extend(f"| {name} | {count} |" for name, count in host_counts.most_common())
    report_lines.extend(
        [
            "",
            "YouTube references remain metadata-only until a provenance-preserving caption or transcript strategy is implemented. EUR-Lex references are eligible for exact-page HTML snapshots.",
            "",
        ]
    )
    report_path = root / "reports" / "reference_classification.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Wrote {output_path} with {len(records)} references")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
