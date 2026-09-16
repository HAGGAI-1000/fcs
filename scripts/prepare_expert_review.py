#!/usr/bin/env python3
"""Create Hebrew, GUID-free relevance-review files for a domain expert."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path


QUESTION_FIELDS = [
    "שאלה",
    "תוצאת_הבדיקה",
    "תשובת_ייחוס_בעברית",
    "הערות_בדיקה",
    "סטטוס_בדיקה",
]
SOURCE_FIELDS = [
    "שאלה",
    "שם_המסמך_באתר_FCS",
    "עמודים_רלוונטיים",
    "תאריך_פרסום_או_עדכון",
    "כתובת_FCS",
    "הערות_מקור",
]

OUTCOME_NOT_REVIEWED = "טרם נבדק"
OUTCOME_FOUND = "נמצא מקור מתאים"
OUTCOME_NOT_FOUND = "לא נמצא מקור לאחר חיפוש"
OUTCOME_OUTSIDE = "נדרש מקור מחוץ לאתר FCS"
OUTCOME_UNCERTAIN = "לא ודאי"
ALLOWED_OUTCOMES = {
    OUTCOME_NOT_REVIEWED,
    OUTCOME_FOUND,
    OUTCOME_NOT_FOUND,
    OUTCOME_OUTSIDE,
    OUTCOME_UNCERTAIN,
}

STATUS_PENDING = "ממתין"
STATUS_APPROVED = "מאושר"
ALLOWED_STATUSES = {STATUS_PENDING, STATUS_APPROVED}


INSTRUCTIONS_HE = """הנחיות למילוי קובצי הערכת הרלוונטיות

מטרת הבדיקה
יש לענות על 50 השאלות באמצעות חיפוש עצמאי באתר FCS ובמסמכי ה-PDF המוצגים בו. אין להשתמש ברשימת תוצאות שהופקה על ידי מערכת האחזור בשלב הבדיקה הראשון.

קובץ השאלות: eval_relevance_expert_he.csv
1. אין לשנות את נוסח השאלות ואין למחוק שורות.
2. בעמודה "תוצאת_הבדיקה" יש לבחור אחת מהאפשרויות: "נמצא מקור מתאים", "לא נמצא מקור לאחר חיפוש", "נדרש מקור מחוץ לאתר FCS", "לא ודאי" או "טרם נבדק".
3. "לא נמצא מקור לאחר חיפוש" אינו זהה ל"נדרש מקור מחוץ לאתר FCS". אין לקבוע שהשאלה מחוץ לתחום רק מפני שלא נמצא מסמך.
4. בעמודה "תשובת_ייחוס_בעברית" יש לכתוב תשובה קצרה ומדויקת בעברית ולציין בה עמודים או אסמכתאות.
5. בעמודה "הערות_בדיקה" יש לציין אי-בהירות, סתירות, תלות בתאריך או מידע נוסף הנדרש מן המשתמש.
6. יש לשנות את "סטטוס_בדיקה" ל"מאושר" רק לאחר השלמת הבדיקה. שאלה שסומנה "לא נמצא מקור לאחר חיפוש" או "לא ודאי" נשארת במצב "ממתין" עד להכרעה נוספת.

קובץ המקורות: eval_relevance_expert_sources_he.csv
7. לכל מקור מתאים יש למלא שורה נפרדת עם נוסח השאלה המלא, שם המסמך בדיוק כפי שהוא מופיע באתר FCS, העמודים הרלוונטיים, תאריך הפרסום או העדכון אם הוא מוצג, וכתובת ה-FCS המלאה.
8. אם יש כמה מקורות לאותה שאלה, יש להעתיק את השורה ולהשאיר את נוסח השאלה זהה לחלוטין בכל השורות.
9. אין צורך למצוא או לרשום GUID. לאחר החזרת הקבצים, הסקריפט ממפה את שם המסמך והפרטים הנלווים ל-GUID הפנימי. התאמה חסרה או דו-משמעית נעצרת לבדיקה ידנית ואינה מנוחשת.
10. יש לשמור את שני הקבצים בפורמט CSV ובקידוד UTF-8 בלי לשנות את שמות העמודות.

בדיקה משלימה
רק לאחר השלמת הבדיקה העצמאית אפשר להשתמש בקובץ eval_candidate_review.csv כבדיקת שלמות. הקובץ מציג מאגר מועמדים ללא דירוג וללא ציון שיטת האחזור. הוא אינו מקור אמת.
"""


def read_questions(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 50:
        raise ValueError(f"Expected 50 evaluation questions, found {len(rows)}")
    if any(row.get("language") != "he" or not re.search(r"[\u0590-\u05ff]", row.get("question", "")) for row in rows):
        raise ValueError("Every evaluation question must contain Hebrew and language=he")
    return rows


def write_csv(path: Path, fields: list[str], rows: list[dict], force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing review file without --force: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--force", action="store_true", help="Replace existing blank reviewer templates")
    args = parser.parse_args()
    root = args.project_root.resolve()
    questions = read_questions(root / "data" / "metadata" / "eval_questions.csv")

    question_rows = [
        {
            "שאלה": row["question"],
            "תוצאת_הבדיקה": OUTCOME_NOT_REVIEWED,
            "תשובת_ייחוס_בעברית": "",
            "הערות_בדיקה": "",
            "סטטוס_בדיקה": STATUS_PENDING,
        }
        for row in questions
    ]
    source_rows = [{"שאלה": row["question"]} for row in questions]
    metadata = root / "data" / "metadata"
    write_csv(metadata / "eval_relevance_expert_he.csv", QUESTION_FIELDS, question_rows, args.force)
    write_csv(metadata / "eval_relevance_expert_sources_he.csv", SOURCE_FIELDS, source_rows, args.force)
    instructions = metadata / "eval_relevance_instructions_he.txt"
    if instructions.exists() and not args.force:
        raise FileExistsError(f"Refusing to overwrite instructions without --force: {instructions}")
    instructions.write_text("\ufeff" + INSTRUCTIONS_HE, encoding="utf-8")
    print("Created GUID-free Hebrew expert-review files for 50 questions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
