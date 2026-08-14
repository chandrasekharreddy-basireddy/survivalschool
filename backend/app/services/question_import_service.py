"""Bulk question import from CSV or XLSX — instructor-facing.

Expected columns (header row required, order doesn't matter):
  prompt, question_type, points, explanation, short_answer_key,
  option_1, option_1_correct, option_2, option_2_correct,
  option_3, option_3_correct, option_4, option_4_correct

question_type is one of single|multiple|true_false|short_answer. Blank
option columns are simply skipped (a question can have 2-4 options). This
reuses the exact same per-row validation rules as the single-question
create endpoint (app/api/v1/quizzes.py::create_question) so a bulk-imported
question can never violate a rule a hand-created one couldn't.

All-or-nothing by design: import_questions() only writes to the database
when every row is valid — a partially-broken CSV should never leave a
course with half-imported garbage. Callers preview first (dry_run=True) to
show the instructor row-by-row errors before committing.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

import openpyxl
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Question, QuestionOption

VALID_TYPES = {"single", "multiple", "true_false", "short_answer"}
MAX_ROWS_PER_IMPORT = 500


@dataclass
class ParsedOption:
    text: str
    is_correct: bool


@dataclass
class ParsedRow:
    row_number: int
    prompt: str = ""
    question_type: str = ""
    points: int = 1
    explanation: str | None = None
    short_answer_key: str | None = None
    options: list[ParsedOption] = field(default_factory=list)
    error: str | None = None


def _truthy(value: str | None) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "y", "correct")


def _rows_from_dicts(raw_rows: list[dict]) -> list[ParsedRow]:
    parsed: list[ParsedRow] = []
    for i, raw in enumerate(raw_rows, start=2):  # row 1 is the header
        row = ParsedRow(row_number=i)
        prompt = str(raw.get("prompt") or "").strip()
        qtype = str(raw.get("question_type") or "").strip().lower()
        if not prompt:
            row.error = "Missing prompt."
            parsed.append(row)
            continue
        if qtype not in VALID_TYPES:
            row.error = f"Invalid question_type '{qtype}' — must be one of {sorted(VALID_TYPES)}."
            parsed.append(row)
            continue

        row.prompt = prompt
        row.question_type = qtype
        try:
            row.points = int(raw.get("points") or 1)
        except (TypeError, ValueError):
            row.error = "points must be an integer."
            parsed.append(row)
            continue
        row.explanation = (str(raw.get("explanation")).strip() or None) if raw.get("explanation") else None
        row.short_answer_key = (str(raw.get("short_answer_key")).strip() or None) if raw.get("short_answer_key") else None

        for idx in range(1, 5):
            text = raw.get(f"option_{idx}")
            if text is None or str(text).strip() == "":
                continue
            row.options.append(ParsedOption(text=str(text).strip(), is_correct=_truthy(raw.get(f"option_{idx}_correct"))))

        # Same validation rules as create_question() in app/api/v1/quizzes.py.
        if qtype in ("single", "true_false"):
            correct_count = sum(1 for o in row.options if o.is_correct)
            if correct_count != 1:
                row.error = "single/true_false questions must have exactly one correct option."
        elif qtype == "multiple":
            if sum(1 for o in row.options if o.is_correct) < 1:
                row.error = "multiple-answer questions need at least one correct option."
            if len(row.options) < 2:
                row.error = "multiple-answer questions need at least two options."
        elif qtype == "short_answer":
            if not row.short_answer_key:
                row.error = "short_answer questions need a short_answer_key."

        parsed.append(row)
    return parsed


def parse_csv(file_bytes: bytes) -> list[ParsedRow]:
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return _rows_from_dicts([dict(r) for r in reader][:MAX_ROWS_PER_IMPORT])


def parse_xlsx(file_bytes: bytes) -> list[ParsedRow]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    header = [str(h).strip().lower() if h is not None else "" for h in next(rows_iter, [])]
    raw_rows = []
    for values in rows_iter:
        if all(v is None for v in values):
            continue
        raw_rows.append({header[i]: values[i] for i in range(min(len(header), len(values)))})
    return _rows_from_dicts(raw_rows[:MAX_ROWS_PER_IMPORT])


async def commit_rows(db: AsyncSession, course_id, rows: list[ParsedRow]) -> int:
    """Only called once the caller has confirmed every row is error-free."""
    inserted = 0
    for row in rows:
        question = Question(
            course_id=course_id, prompt=row.prompt, question_type=row.question_type,
            points=row.points, explanation=row.explanation, short_answer_key=row.short_answer_key,
        )
        db.add(question)
        await db.flush()
        for opt_idx, opt in enumerate(row.options):
            db.add(QuestionOption(question_id=question.id, text=opt.text, is_correct=opt.is_correct, order_index=opt_idx))
        inserted += 1
    await db.commit()
    return inserted
