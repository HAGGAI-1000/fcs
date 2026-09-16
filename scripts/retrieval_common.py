#!/usr/bin/env python3
"""Shared deterministic retrieval utilities for the Phase 2B pipeline."""

from __future__ import annotations

import gzip
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


TOKEN_PATTERN = re.compile(r"[\w\u0590-\u05ff\u0600-\u06ff]+", re.UNICODE)


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
    return rows


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def atomic_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def normalize_for_search(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    return " ".join(TOKEN_PATTERN.findall(value))


def tokenize(value: str) -> list[str]:
    return normalize_for_search(value).split()


class BM25Index:
    """Small Unicode-aware BM25 implementation with no language stemmer assumptions."""

    def __init__(self, rows: list[dict], k1: float = 1.5, b: float = 0.75) -> None:
        self.rows = rows
        self.k1 = k1
        self.b = b
        self.doc_lengths: list[int] = []
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        document_frequency: Counter[str] = Counter()
        for index, row in enumerate(rows):
            tokens = tokenize(row.get("embedding_text") or row.get("text", ""))
            frequencies = Counter(tokens)
            self.doc_lengths.append(len(tokens))
            for token, frequency in frequencies.items():
                self.postings[token].append((index, frequency))
                document_frequency[token] += 1
        self.average_length = (
            sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0.0
        )
        count = len(rows)
        self.idf = {
            token: math.log(1.0 + (count - frequency + 0.5) / (frequency + 0.5))
            for token, frequency in document_frequency.items()
        }

    def search(self, query: str, top_k: int) -> list[tuple[dict, float]]:
        if not self.rows or self.average_length == 0:
            return []
        scores: dict[int, float] = defaultdict(float)
        for token in set(tokenize(query)):
            idf = self.idf.get(token)
            if idf is None:
                continue
            for index, frequency in self.postings[token]:
                length = self.doc_lengths[index]
                denominator = frequency + self.k1 * (
                    1.0 - self.b + self.b * length / self.average_length
                )
                scores[index] += idf * frequency * (self.k1 + 1.0) / denominator
        ranked = sorted(scores.items(), key=lambda item: (-item[1], self.rows[item[0]]["chunk_id"]))
        return [(self.rows[index], score) for index, score in ranked[:top_k]]


def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[dict, float]]], top_k: int, rrf_k: int
) -> list[tuple[dict, float]]:
    scores: dict[str, float] = defaultdict(float)
    rows: dict[str, dict] = {}
    for ranked in ranked_lists:
        for rank, (row, _score) in enumerate(ranked, start=1):
            chunk_id = row["chunk_id"]
            rows[chunk_id] = row
            scores[chunk_id] += 1.0 / (rrf_k + rank)
    ordered = sorted(scores, key=lambda key: (-scores[key], key))[:top_k]
    return [(rows[key], scores[key]) for key in ordered]


def save_bm25_summary(path: Path, index: BM25Index, chunks_sha256: str) -> None:
    """Persist reproducibility metadata; the index itself is rebuilt safely from JSONL."""
    payload = {
        "implementation": "unicode_bm25",
        "k1": index.k1,
        "b": index.b,
        "documents": len(index.rows),
        "terms": len(index.postings),
        "average_document_length": index.average_length,
        "chunks_sha256": chunks_sha256,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
