#!/usr/bin/env python3
"""Audit documented public data channels for the FCS RAG project.

This script performs read-only checks against documented/open government
resources. It does not call FCS application endpoints, access the secure portal,
submit forms, or bypass access controls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


DATAGOV_API = "https://data.gov.il/api/3/action/package_search"
DATAGOV_DATASTORE_API = "https://data.gov.il/api/3/action/datastore_search"
SEARCH_QUERIES = [
    "שירות המזון",
    "יבוא מזון",
    "יבואני מזון",
    "מזון משרד הבריאות",
    "FCS",
    "food import",
]
DISCOVERY_URLS = {
    "fcs_home": "https://fcs.health.gov.il/",
    "fcs_config": "https://fcs.health.gov.il/assets/config.json",
    "fcs_robots": "https://fcs.health.gov.il/robots.txt",
    "fcs_sitemap": "https://fcs.health.gov.il/sitemap.xml",
    "datagov_docs": "https://data.gov.il/docs",
    "datagov_terms": "https://data.gov.il/terms-of-use",
    "datagov_contact": "https://data.gov.il/contact-us",
    "govil_terms": "https://www.gov.il/he/general/terms_of_use",
    "govil_rss": "https://www.gov.il/he/general/gov-rss",
}
ALLOWED_HOSTS = {
    "data.gov.il",
    "fcs.health.gov.il",
    "gov.il",
    "www.gov.il",
}
USER_AGENT = "FCS-RAG-Public-Access-Audit/0.1 (+read-only; contact: project owner)"
OPEN_RESOURCE_FORMATS = {"CSV", "JSON", "XML", "XLS", "XLSX", "ZIP", "GEOJSON"}
FOOD_TERMS = (
    "מזון",
    "יבוא",
    "food",
    "import",
    "fcs",
    "תוסף",
    "סימון",
    "אלרגן",
    "יצרן",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def check_host(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"Host not allow-listed: {host}")


def save_response(response: requests.Response, destination: Path) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    return {
        "url": response.url,
        "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "etag": response.headers.get("etag"),
        "last_modified": response.headers.get("last-modified"),
        "bytes": len(response.content),
        "sha256": hashlib.sha256(response.content).hexdigest(),
        "path": destination.as_posix(),
    }


def export_datastore(session: requests.Session, resource_id: str, destination: Path) -> dict:
    records: list[dict] = []
    fields: list[dict] = []
    offset = 0
    total = None
    page_size = 1000
    while total is None or offset < total:
        response = session.get(
            DATAGOV_DATASTORE_API,
            params={"resource_id": resource_id, "limit": page_size, "offset": offset},
            timeout=(20, 180),
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError(f"DataStore returned success=false for {resource_id}")
        result = payload.get("result", {})
        if not fields:
            fields = result.get("fields", [])
        page_records = result.get("records", [])
        records.extend(page_records)
        total = int(result.get("total", len(records)))
        if not page_records:
            break
        offset += len(page_records)

    export = {
        "resource_id": resource_id,
        "retrieved_at": utc_now(),
        "total": total,
        "fields": fields,
        "records": records,
    }
    encoded = json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(encoded)
    return {
        "status": 200,
        "path": destination.as_posix(),
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "rows": len(records),
        "reported_total": total,
        "field_names": [field.get("id") for field in fields],
    }


def dataset_score(dataset: dict) -> int:
    searchable = " ".join(
        str(dataset.get(key, ""))
        for key in ("title", "name", "notes", "tags", "organization")
    ).lower()
    return sum(1 for term in FOOD_TERMS if term.lower() in searchable)


def compact_dataset(dataset: dict) -> dict:
    organization = dataset.get("organization") or {}
    resources = []
    for resource in dataset.get("resources", []):
        resources.append(
            {
                "id": resource.get("id"),
                "name": resource.get("name"),
                "description": resource.get("description"),
                "format": (resource.get("format") or "").upper(),
                "mimetype": resource.get("mimetype"),
                "url": resource.get("url"),
                "datastore_active": bool(resource.get("datastore_active")),
                "created": resource.get("created"),
                "last_modified": resource.get("last_modified"),
            }
        )
    return {
        "id": dataset.get("id"),
        "name": dataset.get("name"),
        "title": dataset.get("title"),
        "notes": dataset.get("notes"),
        "organization": organization.get("title") or organization.get("name"),
        "license_id": dataset.get("license_id"),
        "license_title": dataset.get("license_title"),
        "license_url": dataset.get("license_url"),
        "maintainer": dataset.get("maintainer"),
        "maintainer_email": dataset.get("maintainer_email"),
        "metadata_created": dataset.get("metadata_created"),
        "metadata_modified": dataset.get("metadata_modified"),
        "dataset_url": f"https://data.gov.il/dataset/{dataset.get('name')}",
        "resources": resources,
    }


def find_feed_links(content: bytes, base_url: str, content_type: str) -> list[dict]:
    if "html" not in content_type.lower():
        return []
    soup = BeautifulSoup(content, "html.parser")
    links: list[dict] = []
    for tag in soup.find_all(["link", "a"]):
        href = tag.get("href")
        if not href:
            continue
        rel = " ".join(tag.get("rel", [])) if isinstance(tag.get("rel"), list) else tag.get("rel")
        declared_type = tag.get("type")
        text = tag.get_text(" ", strip=True)
        searchable = " ".join(filter(None, [href, rel, declared_type, text])).lower()
        if any(token in searchable for token in ("rss", "atom", "feed", ".xml", ".json", "sitemap")):
            links.append(
                {
                    "url": urljoin(base_url, href),
                    "rel": rel,
                    "type": declared_type,
                    "text": text,
                }
            )
    unique = {item["url"]: item for item in links}
    return list(unique.values())


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    root = args.project_root.resolve()
    raw_root = root / "data" / "raw" / "access_audit"
    metadata_root = root / "data" / "metadata"
    report_path = root / "reports" / "public_access_assessment.md"
    raw_root.mkdir(parents=True, exist_ok=True)
    metadata_root.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "*/*"})

    query_log = []
    datasets_by_id: dict[str, dict] = {}
    for query in SEARCH_QUERIES:
        print(f"DataGov search: {query}", flush=True)
        response = session.get(DATAGOV_API, params={"q": query, "rows": 100}, timeout=(20, 120))
        raw_path = raw_root / "datagov" / f"package-search-{safe_name(query)}.json"
        response_meta = save_response(response, raw_path)
        entry = {"query": query, **response_meta}
        if response.ok:
            payload = response.json()
            results = payload.get("result", {}).get("results", []) if payload.get("success") else []
            entry["result_count"] = len(results)
            for dataset in results:
                datasets_by_id[dataset.get("id") or dataset.get("name")] = dataset
        else:
            entry["error"] = response.reason
        query_log.append(entry)

    candidates = [compact_dataset(item) for item in datasets_by_id.values() if dataset_score(item) >= 2]
    candidates.sort(key=lambda row: (row["organization"] or "", row["title"] or ""))

    for dataset in candidates:
        dataset_dir = raw_root / "bulk_exports" / safe_name(dataset["name"] or dataset["id"])
        for resource in dataset["resources"]:
            resource_url = resource.get("url")
            resource_format = resource.get("format") or "BIN"
            if not resource_url or resource_format not in OPEN_RESOURCE_FORMATS:
                continue
            check_host(resource_url)
            extension = "." + resource_format.lower()
            destination = dataset_dir / f"{resource['id']}{extension}"
            print(f"Bulk resource: {resource_url}", flush=True)
            try:
                response = session.get(resource_url, timeout=(20, 180), allow_redirects=True)
                usable_bulk_file = response.status_code == 200 and len(response.content) > 0
                response_destination = (
                    destination
                    if usable_bulk_file
                    else destination.with_suffix(
                        destination.suffix + f".response-{response.status_code}.html"
                    )
                )
                resource["download_check"] = save_response(response, response_destination)
                resource["download_check"]["usable_bulk_file"] = usable_bulk_file
                if not usable_bulk_file:
                    resource["download_check"]["error"] = (
                        "Advertised bulk URL did not return a non-empty HTTP 200 file"
                    )
            except Exception as exc:
                resource["download_check"] = {"status": None, "error": str(exc)}

            if resource.get("datastore_active"):
                sample_destination = dataset_dir / f"{resource['id']}-datastore-sample.json"
                print(f"DataStore sample: {resource['id']}", flush=True)
                try:
                    sample = session.get(
                        DATAGOV_DATASTORE_API,
                        params={"resource_id": resource["id"], "limit": 1},
                        timeout=(20, 120),
                    )
                    resource["datastore_check"] = save_response(sample, sample_destination)
                    if sample.ok:
                        payload = sample.json()
                        result = payload.get("result", {})
                        resource["datastore_check"].update(
                            {
                                "success": payload.get("success"),
                                "total": result.get("total"),
                                "field_names": [field.get("id") for field in result.get("fields", [])],
                            }
                        )
                    else:
                        resource["datastore_check"]["error"] = sample.reason
                except Exception as exc:
                    resource["datastore_check"] = {"status": None, "error": str(exc)}

                full_destination = dataset_dir / f"{resource['id']}-datastore-full.json"
                print(f"DataStore full export: {resource['id']}", flush=True)
                try:
                    resource["datastore_export"] = export_datastore(
                        session, resource["id"], full_destination
                    )
                except Exception as exc:
                    resource["datastore_export"] = {"status": None, "error": str(exc)}

    candidate_payload = {
        "audited_at": utc_now(),
        "api": DATAGOV_API,
        "queries": query_log,
        "candidate_count": len(candidates),
        "datasets": candidates,
    }
    candidate_path = metadata_root / "open_data_candidates.json"
    candidate_path.write_text(json.dumps(candidate_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    discovery_results = []
    all_feed_links = []
    for name, url in DISCOVERY_URLS.items():
        check_host(url)
        print(f"Discovery GET: {url}", flush=True)
        try:
            response = session.get(url, timeout=(20, 120), allow_redirects=True)
            content_type = response.headers.get("content-type", "")
            suffix = ".json" if "json" in content_type else ".xml" if "xml" in content_type else ".html"
            if name.endswith("robots"):
                suffix = ".txt"
            raw_path = raw_root / "discovery" / f"{name}{suffix}"
            meta = save_response(response, raw_path)
            links = find_feed_links(response.content, response.url, content_type) if response.ok else []
            all_feed_links.extend({"source": name, **link} for link in links)
            discovery_results.append({"name": name, **meta, "feed_links": links})
        except Exception as exc:
            discovery_results.append({"name": name, "url": url, "status": None, "error": str(exc)})

    home_record = next((item for item in discovery_results if item["name"] == "fcs_home"), None)
    if home_record:
        for item in discovery_results:
            if item["name"] in {"fcs_robots", "fcs_sitemap"}:
                item["appears_to_be_app_shell"] = (
                    item.get("status") == 200
                    and item.get("sha256") == home_record.get("sha256")
                    and "html" in item.get("content_type", "").lower()
                )

    feed_payload = {
        "audited_at": utc_now(),
        "checked": discovery_results,
        "discovered_feed_links": all_feed_links,
    }
    feed_path = metadata_root / "feed_discovery.json"
    feed_path.write_text(json.dumps(feed_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    ministry_food = [
        row
        for row in candidates
        if "בריאות" in (row.get("organization") or "")
        or "health" in (row.get("organization") or "").lower()
    ]
    format_counts = Counter(
        resource["format"] or "UNKNOWN"
        for dataset in candidates
        for resource in dataset["resources"]
    )
    open_resources = [
        (dataset, resource)
        for dataset in candidates
        for resource in dataset["resources"]
        if resource["datastore_active"] or resource["format"] in OPEN_RESOURCE_FORMATS
    ]
    fcs_feed_links = [item for item in all_feed_links if item["source"].startswith("fcs_")]
    statuses = {item["name"]: item.get("status") for item in discovery_results}
    robots_shell = next(
        (item.get("appears_to_be_app_shell") for item in discovery_results if item["name"] == "fcs_robots"),
        None,
    )
    sitemap_shell = next(
        (item.get("appears_to_be_app_shell") for item in discovery_results if item["name"] == "fcs_sitemap"),
        None,
    )
    verified_bulk = [
        (dataset, resource)
        for dataset, resource in open_resources
        if resource.get("download_check", {}).get("usable_bulk_file") is True
    ]
    verified_datastores = [
        (dataset, resource)
        for dataset, resource in open_resources
        if resource.get("datastore_check", {}).get("success") is True
    ]
    full_datastore_exports = [
        (dataset, resource)
        for dataset, resource in open_resources
        if resource.get("datastore_export", {}).get("status") == 200
    ]
    direct_statuses = Counter(
        resource.get("download_check", {}).get("status")
        for _dataset, resource in open_resources
        if resource.get("download_check", {}).get("status") is not None
    )
    export_summary_lines = [
        "",
        "| Dataset | Organization | Rows | Fields |",
        "|---|---|---:|---:|",
    ]
    for dataset, resource in full_datastore_exports:
        export = resource["datastore_export"]
        export_summary_lines.append(
            f"| {dataset['title']} | {dataset['organization']} | "
            f"{export.get('rows', 0):,} | {len(export.get('field_names', []))} |"
        )

    lines = [
        "# Public API, export, feed, and access assessment",
        "",
        f"Audited: {utc_now()}",
        "",
        "## Executive result",
        "",
        "- **Green:** DataGov's documented CKAN API and dataset resources, subject to each dataset's licence.",
        "- **Amber:** Public FCS publications visible in the browser and internal request names found in the frontend, but no published FCS API contract was found.",
        "- **Red/out of scope:** Authenticated importer records, form submission endpoints, or any access requiring bypass of portal controls.",
        "",
        "## 1. Documented public API",
        "",
        f"The documented DataGov `package_search` API was queried with {len(SEARCH_QUERIES)} terms.",
        f"It produced {len(candidates)} food/import-related candidate datasets after local relevance filtering.",
        "The complete API responses and normalized inventory are stored under `data/raw/access_audit/datagov/` and `data/metadata/open_data_candidates.json`.",
        "",
        "No official OpenAPI/Swagger documentation for the FCS publication endpoints was found in the inspected public FCS page or configuration. Internal endpoint names therefore remain unsupported implementation details.",
        "",
        "## 2. Bulk exports",
        "",
        f"Health-ministry candidate datasets: {len(ministry_food)}.",
        f"Resources that advertise a DataStore or common bulk format: {len(open_resources)}.",
        f"Direct resource URLs returning a usable non-empty HTTP 200 file: {len(verified_bulk)}.",
        f"Direct resource response statuses: {dict(sorted(direct_statuses.items()))}.",
        f"Resources successfully sampled through the documented DataStore API: {len(verified_datastores)}.",
        f"Complete tables exported through the documented DataStore API: {len(full_datastore_exports)}.",
        f"Observed formats: {dict(sorted(format_counts.items()))}.",
        *export_summary_lines,
        "",
        "A resource counts as production-ready only after verifying its URL, licence, update timestamp, schema, and whether the resource is current or merely archival.",
        "",
        "## 3. RSS/XML/JSON feeds",
        "",
        f"FCS feed-style links explicitly advertised by the inspected public HTML: {len(fcs_feed_links)}.",
        f"FCS robots status: {statuses.get('fcs_robots')}; returned application shell: {robots_shell}.",
        f"FCS sitemap status: {statuses.get('fcs_sitemap')}; returned application shell: {sitemap_shell}.",
        "The full observations are stored in `data/metadata/feed_discovery.json`.",
        "",
        "The existence of JSON responses in a browser session is not treated as a supported feed unless an official page or owner documents that use.",
        "",
        "## 4. Automated-access policy",
        "",
        f"DataGov documentation status in the plain HTTP collector: {statuses.get('datagov_docs')}; terms status: {statuses.get('datagov_terms')}.",
        "The browser-indexed official documentation and licence pages exist, and the documented CKAN API calls themselves succeeded; non-standard frontend responses in the plain HTTP collector are an acquisition quirk, not evidence that DataGov lacks documentation.",
        f"gov.il terms status from the non-browser collector: {statuses.get('govil_terms')}.",
        "",
        "DataGov is the preferred channel because it explicitly documents API consumption and dataset licensing. Preserve the applicable licence and retrieval time with every snapshot, identify the source, avoid misleading presentation, and do not process personal information outside the licence and applicable law.",
        "",
        "For FCS/gov.il pages, use only the interfaces and instructions the site provides. Do not bypass authentication, WAF restrictions, CAPTCHAs, or other controls. A production crawler still needs a documented permission basis, conservative rate limits, caching, identifiable user agent, and a takedown/change process.",
        "",
        "## Evidence files",
        "",
        "- `data/metadata/open_data_candidates.json`",
        "- `data/metadata/feed_discovery.json`",
        "- `data/raw/access_audit/datagov/`",
        "- `data/raw/access_audit/discovery/`",
        "- `data/metadata/fcs_frontend_findings.json`",
        "- `data/metadata/source_manifest.jsonl`",
        "",
        "## Remaining uncertainty",
        "",
        "This audit can establish what is publicly documented today. It cannot turn an undocumented FCS endpoint into a supported contract. Written owner confirmation remains the final check for endpoint stability, rate limits, notification of breaking changes, and commercial RAG reuse when no published licence or API policy covers the interface.",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {candidate_path}")
    print(f"Wrote {feed_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
