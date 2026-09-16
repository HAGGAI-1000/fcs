#!/usr/bin/env python3
"""Hebrew command-line demonstration of Phase 2B retrieval."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from retrieval_engine import RetrievalEngine


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="חיפוש במקורות שירות המזון")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--query", required=True, help="שאלה בעברית")
    parser.add_argument("--mode", choices=["bm25", "dense", "hybrid"], default="hybrid")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if not re.search(r"[\u0590-\u05ff]", args.query):
        parser.error("השאילתה חייבת לכלול טקסט בעברית")

    engine = RetrievalEngine(args.project_root)
    results = engine.search(args.query, args.mode, args.top_k)
    if not results:
        print("לא נמצאו תוצאות.")
        return 0
    print(f"נמצאו {len(results)} תוצאות בשיטת {args.mode}:")
    for rank, (row, score) in enumerate(results, start=1):
        pages = str(row["page_start"]) if row["page_start"] == row["page_end"] else f"{row['page_start']}-{row['page_end']}"
        print(f"\n{rank}. {row.get('document_name') or row.get('file_name')} | עמודים {pages} | ציון {score:.4f}")
        print(row.get("text", "")[:360].replace("\n", " "))
        print(f"מקור: {row['source_catalogue_url']} | מזהה מסמך: {row['document_guid']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
