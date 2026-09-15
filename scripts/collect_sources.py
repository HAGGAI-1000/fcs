#!/usr/bin/env python3
"""Snapshot only the configured FCS crawl entry point.

External sources are not accepted here. They must first be discovered in a
public FCS publication and then be handled by collect_referenced_sources.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests


USER_AGENT = "FCS-RAG-Discovery/0.1 (+public-source inventory; no authenticated access)"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def extension_for(content_type: str, url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".pdf", ".html", ".htm", ".json", ".xml", ".txt"}:
        return suffix
    clean_type = content_type.split(";", 1)[0].strip().lower()
    return {
        "application/pdf": ".pdf",
        "application/json": ".json",
        "text/html": ".html",
        "application/xhtml+xml": ".html",
        "text/plain": ".txt",
    }.get(clean_type, mimetypes.guess_extension(clean_type) or ".bin")


def extract_html_title(content: bytes) -> str | None:
    sample = content[:500_000].decode("utf-8", errors="replace")
    match = re.search(r"<title[^>]*>(.*?)</title>", sample, flags=re.I | re.S)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


def validate_fcs_url(url: str, service_hosts: set[str], denied_hosts: set[str]) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise ValueError(f"Only HTTPS URLs are permitted: {url}")
    if host in denied_hosts:
        raise ValueError(f"Denied host: {host}")
    if host not in service_hosts:
        raise ValueError(f"Host is outside the FCS service boundary: {host}")


def fetch_source(
    session: requests.Session,
    source: dict,
    raw_dir: Path,
    entrypoints: set[str],
    service_hosts: set[str],
    denied_hosts: set[str],
) -> dict:
    url = source["url"]
    if url not in entrypoints:
        raise ValueError(f"Manual source is not a configured FCS entry point: {url}")
    validate_fcs_url(url, service_hosts, denied_hosts)

    record = {
        **source,
        "retrieved_at": utc_now(),
        "status": "error",
    }
    try:
        response = session.get(url, timeout=(15, 90), allow_redirects=True)
        for hop in [*response.history, response]:
            validate_fcs_url(hop.url, service_hosts, denied_hosts)
        record.update(
            {
                "http_status": response.status_code,
                "final_url": response.url,
                "content_type": response.headers.get("content-type", ""),
                "etag": response.headers.get("etag"),
                "last_modified": response.headers.get("last-modified"),
            }
        )
        response.raise_for_status()
        content = response.content
        extension = extension_for(record["content_type"], response.url)
        destination = raw_dir / f"{source['id']}{extension}"
        destination.write_bytes(content)
        record.update(
            {
                "status": "downloaded",
                "path": destination.relative_to(raw_dir.parents[2]).as_posix(),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
        if extension in {".html", ".htm"}:
            record["html_title"] = extract_html_title(content)
    except Exception as exc:  # manifesting a failed source is intentional
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    root = args.project_root.resolve()
    config_path = root / "config" / "sources.json"
    raw_dir = root / "data" / "raw" / "fcs_entrypoint"
    metadata_dir = root / "data" / "metadata"
    raw_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    policy_path = root / config["policy_file"]
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if config.get("scope_id") != policy.get("scope_id"):
        raise ValueError("Source registry and crawl policy scope IDs do not match")
    entrypoints = set(policy["entrypoints"])
    service_hosts = {host.lower() for host in policy["fcs_service_hosts"]}
    denied_hosts = {host.lower() for host in policy["denied_hosts"]}
    manifest_path = metadata_dir / "fcs_entrypoint_manifest.jsonl"
    existing: dict[str, dict] = {}
    if manifest_path.exists() and not args.refresh:
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                existing[row["id"]] = row

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})

    records = []
    for source in config["sources"]:
        prior = existing.get(source["id"])
        prior_path = root / prior["path"] if prior and prior.get("path") else None
        if prior and prior.get("status") == "downloaded" and prior_path and prior_path.exists():
            records.append(prior)
            print(f"SKIP {source['id']} (already downloaded)")
            continue
        print(f"GET  {source['id']} -> {source['url']}")
        records.append(
            fetch_source(
                session,
                source,
                raw_dir,
                entrypoints,
                service_hosts,
                denied_hosts,
            )
        )

    temp_path = manifest_path.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    temp_path.replace(manifest_path)

    downloaded = sum(row["status"] == "downloaded" for row in records)
    print(f"Manifest: {manifest_path}")
    print(f"Downloaded: {downloaded}/{len(records)}")
    return 0 if downloaded else 1


if __name__ == "__main__":
    sys.exit(main())
