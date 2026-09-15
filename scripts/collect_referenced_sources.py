#!/usr/bin/env python3
"""Download only exact public URLs discovered in FCS publication records.

This program intentionally accepts no arbitrary URL argument. Its sole input is
the provenance-bearing fcs_direct_references.json manifest created by the FCS
browser crawler.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import mimetypes
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests


ALLOWED_CONTENT_TYPES = {
    "application/json",
    "application/pdf",
    "application/xhtml+xml",
    "text/html",
    "text/plain",
    "text/xml",
}
USER_AGENT = "FCS-RAG-DirectReferenceCollector/0.1 (+public FCS provenance)"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_public_url(url: str, denied_hosts: set[str]) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise ValueError("Only public HTTPS references are permitted")
    if parsed.username or parsed.password:
        raise ValueError("Credential-bearing URLs are not permitted")
    if host in denied_hosts or host == "localhost" or host.endswith(".local"):
        raise ValueError(f"Denied host: {host}")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValueError(f"Non-public IP address is not permitted: {host}")


def extension_for(content_type: str, url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".pdf", ".html", ".htm", ".json", ".xml", ".txt"}:
        return suffix
    return {
        "application/pdf": ".pdf",
        "application/json": ".json",
        "application/xhtml+xml": ".html",
        "text/html": ".html",
        "text/plain": ".txt",
        "text/xml": ".xml",
    }.get(content_type, mimetypes.guess_extension(content_type) or ".bin")


def download_reference(
    session: requests.Session,
    reference: dict,
    raw_dir: Path,
    denied_hosts: set[str],
    maximum_redirects: int,
    maximum_bytes: int,
) -> dict:
    if reference.get("relationship") != "direct_fcs_publication_reference":
        raise ValueError("Reference lacks the required FCS relationship")
    if not reference.get("discovered_from"):
        raise ValueError("Reference lacks FCS provenance")
    if not reference.get("eligible_for_collection"):
        return {**reference, "status": "excluded_by_policy", "checked_at": now()}

    current_url = reference["url"]
    validate_public_url(current_url, denied_hosts)
    redirects = []
    for _ in range(maximum_redirects + 1):
        response = session.get(
            current_url,
            allow_redirects=False,
            stream=True,
            timeout=(20, 120),
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("location")
            response.close()
            if not location:
                raise RuntimeError("Redirect response has no Location header")
            next_url = urljoin(current_url, location)
            validate_public_url(next_url, denied_hosts)
            redirects.append({"status": response.status_code, "from": current_url, "to": next_url})
            current_url = next_url
            continue
        break
    else:
        raise RuntimeError(f"Exceeded maximum redirect count ({maximum_redirects})")

    result = {
        **reference,
        "retrieved_at": now(),
        "http_status": response.status_code,
        "final_url": current_url,
        "redirect_chain": redirects,
        "content_type": response.headers.get("content-type", ""),
        "etag": response.headers.get("etag"),
        "last_modified": response.headers.get("last-modified"),
        "status": "error",
    }
    response.raise_for_status()
    content_type = result["content_type"].split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        response.close()
        result.update(
            {
                "status": "skipped_unsupported_content_type",
                "reason": f"Content type is not an ingestible document/page: {content_type}",
            }
        )
        return result

    advertised_length = response.headers.get("content-length")
    if advertised_length and int(advertised_length) > maximum_bytes:
        response.close()
        raise RuntimeError(f"Advertised response exceeds {maximum_bytes} bytes")

    chunks = []
    size = 0
    for chunk in response.iter_content(chunk_size=128 * 1024):
        if not chunk:
            continue
        size += len(chunk)
        if size > maximum_bytes:
            response.close()
            raise RuntimeError(f"Response exceeds {maximum_bytes} bytes")
        chunks.append(chunk)
    response.close()
    content = b"".join(chunks)
    extension = extension_for(content_type, current_url)
    destination = raw_dir / f"{reference['reference_id']}{extension}"
    destination.write_bytes(content)
    result.update(
        {
            "status": "downloaded",
            "path": destination.as_posix(),
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    )
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    root = args.project_root.resolve()
    policy = json.loads((root / "config" / "crawl_policy.json").read_text(encoding="utf-8"))
    references_payload = json.loads(
        (root / "data" / "metadata" / "fcs_direct_references.json").read_text(encoding="utf-8")
    )
    if references_payload.get("scope_id") != policy.get("scope_id"):
        raise ValueError("Reference manifest does not match the active crawl policy")
    if references_payload.get("source_catalogue_url") not in policy.get("entrypoints", []):
        raise ValueError("Reference manifest was not produced from an active FCS entry point")

    references = references_payload.get("references", [])
    if args.limit is not None:
        references = references[: args.limit]
    output_path = root / "data" / "metadata" / "fcs_referenced_downloads.json"
    raw_dir = root / "data" / "raw" / "fcs_referenced_sources"
    raw_dir.mkdir(parents=True, exist_ok=True)
    prior_by_id = {}
    if output_path.exists() and not args.refresh:
        prior = json.loads(output_path.read_text(encoding="utf-8"))
        prior_by_id = {row["reference_id"]: row for row in prior.get("sources", [])}

    rules = policy["rules"]
    denied_hosts = {host.lower() for host in policy["denied_hosts"]}
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": ", ".join(ALLOWED_CONTENT_TYPES)})
    records = []
    for reference in references:
        previous = prior_by_id.get(reference["reference_id"])
        previous_path = Path(previous["path"]) if previous and previous.get("path") else None
        if previous and previous.get("status") == "downloaded" and previous_path and previous_path.exists():
            records.append(previous)
            print(f"SKIP {reference['url']} (already downloaded)")
            continue
        print(f"GET  {reference['url']}")
        try:
            records.append(
                download_reference(
                    session,
                    reference,
                    raw_dir,
                    denied_hosts,
                    int(rules["maximum_redirects"]),
                    int(rules["maximum_download_bytes"]),
                )
            )
        except Exception as exc:
            records.append(
                {
                    **reference,
                    "retrieved_at": now(),
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    payload = {
        "collected_at": now(),
        "scope_id": policy["scope_id"],
        "input_manifest": "data/metadata/fcs_direct_references.json",
        "sources": records,
    }
    temporary = output_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output_path)
    downloaded = sum(row.get("status") == "downloaded" for row in records)
    errors = sum(row.get("status") == "error" for row in records)
    print(f"Wrote {output_path}: {downloaded} downloaded, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
