#!/usr/bin/env python3
"""Perform inexpensive consistency checks on the Phase 1 discovery package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project_root.resolve()
    failures: list[str] = []

    required = [
        "README.md",
        "config/crawl_policy.json",
        "config/sources.json",
        "data/README.md",
        "data/metadata/eval_questions.json",
        "data/metadata/fcs_publication_inventory.json",
        "reports/phase1_discovery.md",
        "reports/legal_source_hierarchy.md",
        "reports/source_scope_policy.md",
        "scripts/collect_sources.py",
        "scripts/discover_fcs_bundle.py",
        "scripts/collect_fcs_publications.py",
        "scripts/collect_referenced_sources.py",
        "scripts/audit_public_access.py",
    ]
    for relative in required:
        if not (root / relative).exists():
            failures.append(f"Missing {relative}")

    source_config = json.loads((root / "config" / "sources.json").read_text(encoding="utf-8"))
    policy = json.loads((root / "config" / "crawl_policy.json").read_text(encoding="utf-8"))
    ids = [source["id"] for source in source_config["sources"]]
    if len(ids) != len(set(ids)):
        failures.append("Duplicate source IDs")
    if source_config.get("scope_id") != policy.get("scope_id"):
        failures.append("Active source registry and crawl policy scope IDs differ")
    configured_urls = {source["url"] for source in source_config["sources"]}
    entrypoints = set(policy.get("entrypoints", []))
    if configured_urls != entrypoints:
        failures.append("Active source registry must contain only crawl-policy entry points")
    if len(configured_urls) != 1 or any(
        (urlparse(url).hostname or "").lower() != "fcs.health.gov.il"
        for url in configured_urls
    ):
        failures.append("The only manually configured source must be the public FCS portal")
    if "fcsportal.health.gov.il" not in {
        host.lower() for host in policy.get("denied_hosts", [])
    }:
        failures.append("Authenticated FCS portal is not denied by crawl policy")
    rules = policy.get("rules", {})
    if rules.get("manual_external_seeds_allowed") is not False:
        failures.append("Crawl policy permits manual external seeds")
    if rules.get("external_url_requires_fcs_provenance") is not True:
        failures.append("Crawl policy does not require FCS provenance for external URLs")

    run_script = (root / "run_phase1.ps1").read_text(encoding="utf-8")
    if "audit_public_access.py" in run_script or "data.gov.il" in run_script:
        failures.append("Default Phase 1 workflow still invokes an out-of-scope DataGov audit")

    required_exclusions = {
        "data/raw/access_audit",
        "data/raw/configured_sources",
        "data/metadata/open_data_candidates.json",
        "data/metadata/source_manifest.jsonl",
        "config/archived_sources_pre_fcs_only.json",
    }
    if not required_exclusions.issubset(set(policy.get("excluded_from_ingestion", []))):
        failures.append("Historical discovery paths are not all excluded from ingestion")

    fcs_downloads_path = root / "data" / "metadata" / "fcs_document_downloads.json"
    if fcs_downloads_path.exists():
        payload = json.loads(fcs_downloads_path.read_text(encoding="utf-8"))
        if payload.get("scope_id") != policy.get("scope_id"):
            failures.append("FCS document manifest has the wrong scope ID")
        for document in payload.get("documents", []):
            if document.get("source_catalogue_url") not in entrypoints:
                failures.append("FCS document lacks active catalogue provenance")
            request_host = (
                urlparse(document.get("request_url", "")).hostname or ""
            ).lower()
            if request_host not in {
                host.lower() for host in policy.get("fcs_service_hosts", [])
            }:
                failures.append("FCS document was retrieved outside the FCS service boundary")

    references_path = root / "data" / "metadata" / "fcs_direct_references.json"
    reference_ids: set[str] = set()
    if references_path.exists():
        references_payload = json.loads(references_path.read_text(encoding="utf-8"))
        if references_payload.get("scope_id") != policy.get("scope_id"):
            failures.append("Direct-reference manifest has the wrong scope ID")
        for reference in references_payload.get("references", []):
            reference_ids.add(reference.get("reference_id", ""))
            if reference.get("relationship") != "direct_fcs_publication_reference":
                failures.append("External reference lacks direct-FCS relationship")
            provenance = reference.get("discovered_from") or []
            if not provenance or any(
                row.get("source_catalogue_url") not in entrypoints for row in provenance
            ):
                failures.append("External reference lacks valid FCS provenance")
            if reference.get("eligible_for_collection"):
                parsed = urlparse(reference.get("url", ""))
                if parsed.scheme != "https" or not parsed.hostname:
                    failures.append("Eligible external reference is not a public HTTPS URL")
                if parsed.hostname.lower() in {
                    host.lower() for host in policy.get("denied_hosts", [])
                }:
                    failures.append("Eligible external reference points to a denied host")

    referenced_downloads_path = root / "data" / "metadata" / "fcs_referenced_downloads.json"
    if referenced_downloads_path.exists():
        payload = json.loads(referenced_downloads_path.read_text(encoding="utf-8"))
        if payload.get("scope_id") != policy.get("scope_id"):
            failures.append("Referenced-download manifest has the wrong scope ID")
        if payload.get("input_manifest") != "data/metadata/fcs_direct_references.json":
            failures.append("Referenced downloader did not use the FCS reference manifest")
        for source in payload.get("sources", []):
            if source.get("reference_id") not in reference_ids:
                failures.append("Referenced download was not discovered by the FCS crawler")

    question_path = root / "data" / "metadata" / "eval_questions.json"
    if question_path.exists():
        questions = json.loads(question_path.read_text(encoding="utf-8"))
        if not isinstance(questions, list):
            failures.append("Evaluation questions JSON must be an array")
            questions = []
        if len(questions) != 50:
            failures.append(f"Expected 50 evaluation questions, found {len(questions)}")
        if len({row["id"] for row in questions}) != len(questions):
            failures.append("Duplicate evaluation question IDs")
        non_hebrew_language = [
            row.get("id", "<missing-id>")
            for row in questions
            if row.get("language", "").strip().lower() != "he"
        ]
        if non_hebrew_language:
            failures.append(
                "Evaluation questions not marked as Hebrew: "
                + ", ".join(non_hebrew_language)
            )
        questions_without_hebrew = [
            row.get("id", "<missing-id>")
            for row in questions
            if not re.search(r"[\u0590-\u05FF]", row.get("question", ""))
        ]
        if questions_without_hebrew:
            failures.append(
                "Evaluation questions without Hebrew text: "
                + ", ".join(questions_without_hebrew)
            )
        if len({row.get("question", "").strip() for row in questions}) != len(questions):
            failures.append("Duplicate evaluation question text")

    manifest_path = root / "data" / "metadata" / "source_manifest.jsonl"
    if manifest_path.exists():
        for line_number, line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), 1):
            row = json.loads(line)
            if row.get("status") != "downloaded":
                continue
            path = root / row["path"]
            if not path.exists():
                failures.append(f"Manifest line {line_number} points to missing {row['path']}")
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != row.get("sha256"):
                failures.append(f"Checksum mismatch for {row['path']}")

    if failures:
        print("Phase 1 verification FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Phase 1 verification PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
