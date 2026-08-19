"""Shared CSV/XLSX row-parsing for bulk import features (attendance rosters,
external campus timetable sync). Both need the same thing: accept a real
uploaded file, tolerate messy real-world headers (case, whitespace, common
synonyms), and hand back plain dict rows keyed by lowercased header text
instead of forcing every caller to reimplement header matching.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time

import openpyxl

from app.core.exceptions import ValidationAppError


def parse_tabular_file(filename: str, content: bytes) -> list[dict[str, str]]:
    lower = (filename or "").lower()
    if lower.endswith(".csv"):
        rows = _parse_csv(content)
    elif lower.endswith(".xlsx"):
        rows = _parse_xlsx(content)
    else:
        raise ValidationAppError("Unsupported file type — upload a .csv or .xlsx file.")
    if not rows:
        raise ValidationAppError("The file has no data rows.")
    return rows


def _parse_csv(content: bytes) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k} for raw in reader]


def _parse_xlsx(content: bytes) -> list[dict[str, str]]:
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:
        raise ValidationAppError("Couldn't read this file as an Excel workbook.") from e
    ws = wb.worksheets[0]
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return []
    headers = [str(h).strip().lower() if h is not None else "" for h in header_row]
    out = []
    for raw in rows_iter:
        if raw is None or all(v is None for v in raw):
            continue
        row = {headers[i]: ("" if v is None else str(v).strip()) for i, v in enumerate(raw) if i < len(headers) and headers[i]}
        out.append(row)
    return out


def find_column(row: dict[str, str], candidates: list[str]) -> str | None:
    """First non-empty value among a list of acceptable header-name synonyms."""
    for c in candidates:
        if c in row and row[c]:
            return row[c]
    return None


_DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y")
_TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p", "%Y-%m-%d %H:%M:%S")


def parse_flexible_date(value: str) -> date:
    value = (value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date: {value!r}")


def parse_flexible_time(value: str) -> time:
    value = (value or "").strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized time: {value!r}")
