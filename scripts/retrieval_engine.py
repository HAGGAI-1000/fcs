#!/usr/bin/env python3
"""Load and query the local BM25, LlamaIndex dense, and hybrid retrievers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from llama_index.core import StorageContext, load_index_from_storage

from local_embedding import FastEmbedAdapter
from retrieval_common import BM25Index, read_jsonl, reciprocal_rank_fusion


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class RetrievalEngine:
    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve()
        self.config = json.loads((self.root / "config" / "retrieval.json").read_text(encoding="utf-8"))
        chunks_path = self.root / "data" / "processed" / "fcs_chunks.jsonl"
        self.chunks = read_jsonl(chunks_path)
        self.by_id = {row["chunk_id"]: row for row in self.chunks}
        if len(self.by_id) != len(self.chunks):
            raise ValueError("Chunk identifiers are not unique")
        self.bm25 = BM25Index(self.chunks)

        manifest = json.loads(
            (self.root / "data" / "metadata" / "index_manifest.json").read_text(encoding="utf-8")
        )
        if manifest.get("scope_id") != self.config.get("scope_id"):
            raise ValueError("Index and retrieval scopes do not match")
        if manifest.get("chunks_sha256") != sha256_file(chunks_path):
            raise ValueError("Dense index is stale relative to the chunks")
        retrieval = self.config["retrieval"]
        if manifest.get("dense_model") != retrieval["dense_model"]:
            raise ValueError("Dense index model does not match retrieval configuration")
        cache_dir = self.root / Path(retrieval["dense_model_cache"])
        embedding = FastEmbedAdapter(retrieval["dense_model"], str(cache_dir), batch_size=128)
        storage = StorageContext.from_defaults(
            persist_dir=str(self.root / Path(manifest["dense_index"]))
        )
        self.dense_index = load_index_from_storage(storage, embed_model=embedding)

    def search_bm25(self, query: str, top_k: int) -> list[tuple[dict, float]]:
        return self.bm25.search(query, top_k)

    def search_dense(self, query: str, top_k: int) -> list[tuple[dict, float]]:
        nodes = self.dense_index.as_retriever(similarity_top_k=top_k).retrieve(query)
        results = []
        for node in nodes:
            row = self.by_id.get(node.node.node_id)
            if row is not None:
                results.append((row, float(node.score or 0.0)))
        return results

    def search(self, query: str, mode: str, top_k: int | None = None) -> list[tuple[dict, float]]:
        settings = self.config["retrieval"]
        limit = int(top_k or settings["top_k"])
        candidate_k = max(limit, int(settings["fusion_candidate_k"]))
        if mode == "bm25":
            return self.search_bm25(query, limit)
        if mode == "dense":
            return self.search_dense(query, limit)
        if mode == "hybrid":
            return reciprocal_rank_fusion(
                [self.search_bm25(query, candidate_k), self.search_dense(query, candidate_k)],
                limit,
                int(settings["rrf_k"]),
            )
        raise ValueError(f"Unknown retrieval mode: {mode}")
