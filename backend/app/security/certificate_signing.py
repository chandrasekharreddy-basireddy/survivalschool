"""Ed25519 signing for contest certificates.

A plain "is this certificate number in our database" check means every
verifier has to trust our API and our database. Asymmetric signing lets a
third party (an employer, another platform) confirm a certificate's
authenticity purely from its printed facts plus our published public key --
no call to our server required, and no ability to forge one without our
private key even for someone with direct database access.

The signing key is derived from JWT_SECRET via HKDF (RFC 5869) rather than
stored as its own secret, so there is nothing new to provision or rotate in
any environment: JWT_SECRET's existing rotate-on-compromise story covers this
too. HKDF's purpose-scoped "info" string keeps the derived key
cryptographically independent of the JWT signing use -- compromising one
does not help forge the other.

The signature is never persisted. It is fully deterministic from the
certificate's own already-stored fields plus the server secret, so it is
recomputed on every read (verify endpoint, PDF render) rather than stored
as a column -- one less place for it to drift out of sync with the data it
attests to.
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings

settings = get_settings()

_HKDF_INFO = b"survivalschool-certificate-signing-v1"

SIGNING_ALGORITHM = "Ed25519"


def _private_key() -> Ed25519PrivateKey:
    seed = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO).derive(settings.JWT_SECRET.encode())
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key_base64() -> str:
    public_bytes = _private_key().public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(public_bytes).decode("ascii")


def signing_payload(
    *, certificate_number: str, student_id: str, contest_id: str | None,
    contest_title: str, rank: int, score_percent: int, issued_at: str,
) -> str:
    """Canonical string covering every fact a verifier relies on. Order and
    field set are part of the format (`SSCERT-v1`) -- changing either would
    invalidate every previously issued signature, so treat this as frozen
    and version-bump the prefix instead of editing it in place."""
    return "|".join([
        "SSCERT-v1", certificate_number, student_id, contest_id or "",
        contest_title, str(rank), str(score_percent), issued_at,
    ])


def sign(payload: str) -> str:
    return base64.b64encode(_private_key().sign(payload.encode())).decode("ascii")
