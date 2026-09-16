#!/usr/bin/env python3
"""Synchronize the static reviewer question data with the canonical JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.project_root.resolve()
    rows = json.loads(
        (root / "data" / "metadata" / "eval_questions.json").read_text(encoding="utf-8")
    )
    if not isinstance(rows, list):
        raise ValueError("The canonical evaluation-question JSON must be an array")
    if len(rows) != 50 or len({row["id"] for row in rows}) != 50:
        raise ValueError("The reviewer application requires 50 unique evaluation questions")
    if any(row.get("language") != "he" or not re.search(r"[\u0590-\u05ff]", row["question"]) for row in rows):
        raise ValueError("Every reviewer question must be Hebrew")
    payload = [
        {
            "id": row["id"],
            "question": row["question"],
            "category": row["category"],
            "risk_level": row["risk_level"],
        }
        for row in rows
    ]
    output = root / "review_app" / "questions.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output} with {len(payload)} questions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
