from __future__ import annotations

from pydantic import BaseModel


class ImportRowOut(BaseModel):
    row_number: int
    prompt: str
    question_type: str
    error: str | None = None


class ImportPreviewOut(BaseModel):
    total_rows: int
    valid_rows: int
    error_rows: int
    rows: list[ImportRowOut]
    committed: bool
    inserted_count: int = 0
