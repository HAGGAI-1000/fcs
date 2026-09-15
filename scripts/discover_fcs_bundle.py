#!/usr/bin/env python3
"""Snapshot and inspect the public FCS frontend without invoking application actions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests


HOME_URL = "https://fcs.health.gov.il/"
CONFIG_URL = urljoin(HOME_URL, "assets/config.json")
USER_AGENT = "FCS-RAG-Discovery/0.1 (+public frontend inventory)"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def download(session: requests.Session, url: str, destination: Path, refresh: bool) -> bytes:
    if destination.exists() and not refresh:
        return destination.read_bytes()
    response = session.get(url, timeout=(15, 120))
    response.raise_for_status()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    return response.content


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    root = args.project_root.resolve()
    raw_dir = root / "data" / "raw" / "fcs_frontend"
    metadata_dir = root / "data" / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    homepage = download(session, HOME_URL, raw_dir / "index.html", args.refresh)
    config_bytes = download(session, CONFIG_URL, raw_dir / "config.json", args.refresh)

    html = homepage.decode("utf-8", errors="replace")
    bundle_match = re.search(r'<script[^>]+src="([^"]*main\.[^"]+\.js)"', html, flags=re.I)
    if not bundle_match:
        raise RuntimeError("Could not locate the hashed Angular main bundle")
    bundle_url = urljoin(HOME_URL, bundle_match.group(1))
    bundle_name = Path(bundle_url).name
    bundle = download(session, bundle_url, raw_dir / bundle_name, args.refresh)
    bundle_text = bundle.decode("utf-8", errors="replace")

    api_endpoints = sorted(set(re.findall(r'"(/Api/FCS/[A-Za-z0-9_-]+)"', bundle_text)))
    routes = sorted(set(re.findall(r'path:"([A-Za-z0-9_:/ -]+)"', bundle_text)))
    config = json.loads(config_bytes.decode("utf-8-sig"))

    findings = {
        "observed_at": now(),
        "home_url": HOME_URL,
        "config_url": CONFIG_URL,
        "bundle_url": bundle_url,
        "bundle_sha256": hashlib.sha256(bundle).hexdigest(),
        "frontend": "Angular single-page application",
        "configuration": config,
        "candidate_fcs_api_endpoints": api_endpoints,
        "candidate_routes": routes,
        "confirmed_public_route": "/publicationsCategories/0",
        "publication_request_shapes_from_bundle": {
            "categories": {"certificateTypeCode": 26, "functionCode": 94},
            "items": {
                "certificateTypeCode": 26,
                "functionCode": 95,
                "certificateNum": "<subjectCode>",
            },
            "document": {"endpoint": "/Api/FCS/GetSpecificDocument", "docType": 26, "docId": "<guid>"},
        },
        "warning": (
            "Endpoint names are implementation details, not a supported public API contract. "
            "Use the browser-rendered public collector unless the Ministry confirms API use."
        ),
    }

    output = metadata_dir / "fcs_frontend_findings.json"
    output.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output}")
    print(f"Found {len(api_endpoints)} candidate FCS endpoints and {len(routes)} routes")
    return 0


if __name__ == "__main__":
    sys.exit(main())

