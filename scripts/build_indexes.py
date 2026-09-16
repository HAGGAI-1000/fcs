#!/usr/bin/env python3
"""Build a local LlamaIndex vector index and reproducible BM25 metadata."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from llama_index.core import VectorStoreIndex
from llama_index.core.schema import TextNode

from local_embedding import FastEmbedAdapter
from retrieval_common import BM25Index, atomic_json, read_jsonl, save_bm25_summary


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_child(root: Path, value: Path) -> Path:
    resolved_root = root.resolve()
    resolved = value.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"Index path escapes its configured root: {resolved}")
    return resolved


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--force", action="store_true", help="Rebuild even when the current index manifest matches")
    args = parser.parse_args()

    root = args.project_root.resolve()
    config = json.loads((root / "config" / "retrieval.json").read_text(encoding="utf-8"))
    chunks_path = root / "data" / "processed" / "fcs_chunks.jsonl"
    chunk_manifest_path = root / "data" / "metadata" / "chunk_manifest.json"
    chunk_manifest = json.loads(chunk_manifest_path.read_text(encoding="utf-8"))
    chunks_hash = sha256_file(chunks_path)
    if chunk_manifest.get("output_sha256") != chunks_hash:
        raise ValueError("Chunk manifest checksum is stale")
    if chunk_manifest.get("scope_id") != config.get("scope_id"):
        raise ValueError("Chunk and retrieval scopes do not match")

    retrieval = config["retrieval"]
    index_root = safe_child(root, root / Path(retrieval["dense_index"]))
    version = chunks_hash[:12]
    persist_dir = safe_child(index_root, index_root / version)
    manifest_path = root / "data" / "metadata" / "index_manifest.json"
    if manifest_path.exists() and persist_dir.is_dir() and not args.force:
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        if prior.get("chunks_sha256") == chunks_hash and prior.get("dense_model") == retrieval["dense_model"]:
            print(f"Index already current at {persist_dir}")
            return 0
    if persist_dir.exists():
        raise ValueError(f"Versioned index path already exists; remove it explicitly before --force: {persist_dir}")
    persist_dir.mkdir(parents=True)

    chunks = read_jsonl(chunks_path)
    if len(chunks) != int(chunk_manifest["chunks"]):
        raise ValueError("Chunk count does not match chunk manifest")
    nodes = []
    metadata_keys = [
        "scope_id",
        "document_guid",
        "document_name",
        "category",
        "issue_date",
        "page_start",
        "page_end",
        "source_catalogue_url",
        "source_path",
        "source_sha256",
        "quality_states",
        "needs_ocr_review",
    ]
    for row in chunks:
        metadata = {key: row.get(key) for key in metadata_keys}
        nodes.append(
            TextNode(
                id_=row["chunk_id"],
                text=row["embedding_text"],
                metadata=metadata,
                excluded_embed_metadata_keys=list(metadata),
                excluded_llm_metadata_keys=list(metadata),
            )
        )

    cache_dir = safe_child(root, root / Path(retrieval["dense_model_cache"]))
    cache_dir.mkdir(parents=True, exist_ok=True)
    embedding = FastEmbedAdapter(
        model_name=retrieval["dense_model"], cache_dir=str(cache_dir), batch_size=128
    )
    print(f"Building LlamaIndex vector index for {len(nodes)} chunks", flush=True)
    index = VectorStoreIndex(
        nodes,
        embed_model=embedding,
        insert_batch_size=256,
        show_progress=True,
    )
    index.storage_context.persist(persist_dir=str(persist_dir))

    print("Building Unicode BM25 baseline metadata", flush=True)
    bm25 = BM25Index(chunks)
    bm25_path = persist_dir / "bm25_summary.json.gz"
    save_bm25_summary(bm25_path, bm25, chunks_hash)
    probe_dimension = len(embedding.get_query_embedding("בדיקת ממד וקטור"))
    manifest = {
        "built_at": now(),
        "scope_id": config["scope_id"],
        "chunks": len(chunks),
        "chunks_path": "data/processed/fcs_chunks.jsonl",
        "chunks_sha256": chunks_hash,
        "dense_model": retrieval["dense_model"],
        "dense_dimension": probe_dimension,
        "dense_index": persist_dir.relative_to(root).as_posix(),
        "bm25_summary": bm25_path.relative_to(root).as_posix(),
        "llama_index_core_version": importlib.metadata.version("llama-index-core"),
        "fastembed_version": importlib.metadata.version("fastembed"),
    }
    atomic_json(manifest_path, manifest)
    print(f"Wrote {manifest_path}")
    print(f"Persisted index at {persist_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
