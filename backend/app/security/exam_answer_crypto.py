"""Encryption at rest for in-progress (ungraded) exam answers.

Autosaved answers are stored as ciphertext, not plaintext, so that anyone
with read access to the database (a backup, a read replica, a compromised
analytics export, an insider with SQL access but not application/env
access) cannot see a student's in-progress answers on a still-open exam
before it closes -- a real fairness concern distinct from normal
attempt-ownership checks, which only stop other USERS from reading them
through the API.

Same key-derivation pattern as app.security.certificate_signing: derive a
purpose-scoped key from JWT_SECRET via HKDF rather than provisioning a new
secret, so there's nothing extra to configure in any environment.
"""
from __future__ import annotations

import base64
import json
import uuid

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings

settings = get_settings()

_HKDF_INFO = b"survivalschool-exam-answer-autosave-v1"

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(settings.JWT_SECRET.encode())
        _fernet = Fernet(base64.urlsafe_b64encode(key))
    return _fernet


def encrypt_answers(data: dict) -> str:
    return _get_fernet().encrypt(json.dumps(data).encode()).decode("ascii")


def decrypt_answers(ciphertext: str) -> dict:
    return json.loads(_get_fernet().decrypt(ciphertext.encode()).decode())


def get_saved_answer(ciphertext: str | None, question_id: uuid.UUID) -> tuple[list[str], str | None] | None:
    """Used when force-finalizing an attempt (integrity-violation cap, or the
    contest window closing on a still-in-progress attempt) so a question the
    student genuinely autosaved an answer for -- just never clicked final
    submit on -- is graded on that answer rather than as blank. Returns None
    if there's nothing saved for this question (or no autosave at all)."""
    if not ciphertext:
        return None
    saved = decrypt_answers(ciphertext).get(str(question_id))
    if saved is None:
        return None
    return [str(o) for o in saved.get("selected_option_ids") or []], saved.get("text_answer")
