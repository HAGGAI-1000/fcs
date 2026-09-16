#!/usr/bin/env python3
"""Create the canonical GUID-free JSON template for domain review."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


REVIEW_SCHEMA_VERSION = 2

INSTRUCTIONS_HE = """הנחיות לבדיקת הרלוונטיות

מטרת הבדיקה
יש לענות על 50 השאלות באמצעות חיפוש עצמאי באתר FCS ובמסמכי ה-PDF המוצגים בו. אין להשתמש ברשימת תוצאות שהופקה על ידי מערכת האחזור בשלב הבדיקה הראשון.

השימוש ביישום
1. יש למלא את הבדיקה ביישום העברי שפורסם ב-GitHub Pages.
2. לכל שאלה יש לבחור תוצאה, לכתוב תשובת ייחוס בעברית ולהוסיף הערות לפי הצורך.
3. לכל מקור מתאים יש להוסיף רשומת מקור נפרדת עם שם המסמך בדיוק כפי שהוא מופיע באתר FCS, העמודים הרלוונטיים, תאריך הפרסום או העדכון אם הוא מוצג, וכתובת ה-FCS המלאה.
4. אין צורך למצוא או לרשום GUID. לאחר החזרת הקובץ, הסקריפט ממפה את שם המסמך והפרטים הנלווים ל-GUID הפנימי. התאמה חסרה או דו-משמעית נעצרת לבדיקה ידנית ואינה מנוחשת.
5. "לא נמצא מקור לאחר חיפוש" אינו זהה ל"נדרש מקור מחוץ לאתר FCS". אין לקבוע שהשאלה מחוץ לתחום רק מפני שלא נמצא מסמך.
6. יש לסמן שאלה כ"מאושר" רק לאחר השלמת הבדיקה. שאלה שסומנה "לא נמצא מקור לאחר חיפוש" או "לא ודאי" נשארת במצב "ממתין" עד להכרעה נוספת.
7. הנתונים נשמרים בדפדפן המקומי בלבד. מומלץ לייצא את הקובץ במהלך העבודה.
8. בסיום יש לשלוח קובץ אחד בלבד: eval_relevance_expert.json. אותו קובץ משמש גם לגיבוי וגם להעברת התוצאה.

בדיקה משלימה
רק לאחר השלמת הבדיקה העצמאית אפשר להשתמש בקובץ eval_candidate_review.csv כבדיקת שלמות. הקובץ מציג מאגר מועמדים ללא דירוג וללא ציון שיטת האחזור. הוא אינו מקור אמת.
"""


def read_questions(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 50:
        raise ValueError(f"Expected 50 evaluation questions, found {len(rows)}")
    if any(
        row.get("language") != "he"
        or not re.search(r"[\u0590-\u05ff]", row.get("question", ""))
        for row in rows
    ):
        raise ValueError("Every evaluation question must contain Hebrew and language=he")
    return rows


def build_review(questions: list[dict]) -> dict:
    return {
        "schema_version": REVIEW_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "question_count": len(questions),
        "reviews": [
            {
                "question_id": row["id"],
                "question_text_he": row["question"],
                "outcome": "not_reviewed",
                "review_status": "pending",
                "reference_answer_he": "",
                "review_notes": "",
                "sources": [],
            }
            for row in questions
        ],
    }


def write_text(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing review file without --force: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--force", action="store_true", help="Replace the existing blank reviewer template")
    args = parser.parse_args()
    root = args.project_root.resolve()
    questions = read_questions(root / "data" / "metadata" / "eval_questions.csv")
    metadata = root / "data" / "metadata"
    write_text(
        metadata / "eval_relevance_expert.json",
        json.dumps(build_review(questions), ensure_ascii=False, indent=2) + "\n",
        args.force,
    )
    write_text(
        metadata / "eval_relevance_instructions_he.txt",
        "\ufeff" + INSTRUCTIONS_HE,
        args.force,
    )
    print("Created one GUID-free expert-review JSON file for 50 questions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
