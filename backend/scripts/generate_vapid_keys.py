#!/usr/bin/env python
"""Generate a real VAPID (Voluntary Application Server Identification) keypair
for Web Push — no third-party push provider account (Firebase, APNs, OneSignal,
etc.) is required. VAPID is part of the open Web Push standard (RFC 8292); the
browser vendors' own push services (Chrome/Firefox/Edge) accept any
self-generated keypair presented this way.

Run this ONCE per environment/deployment and paste the output into that
environment's real `.env` file (never into `.env.example` or git — the
private key is a real secret, exactly like a JWT signing key or a TLS
private key, and must be generated per-deployment rather than shared).

Usage:
    backend/.venv/bin/python backend/scripts/generate_vapid_keys.py
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid


def generate() -> tuple[str, str]:
    vapid = Vapid()
    vapid.generate_keys()

    raw_public = vapid.public_key.public_bytes(
        encoding=Encoding.X962, format=PublicFormat.UncompressedPoint
    )
    public_b64 = base64.urlsafe_b64encode(raw_public).rstrip(b"=").decode()

    private_value = vapid.private_key.private_numbers().private_value
    raw_private = private_value.to_bytes(32, "big")
    private_b64 = base64.urlsafe_b64encode(raw_private).rstrip(b"=").decode()

    return public_b64, private_b64


if __name__ == "__main__":
    pub, priv = generate()
    print("Generated a new VAPID keypair (RFC 8292). Add these to your real")
    print("environment's .env file — do NOT commit them:\n")
    print(f"VAPID_PUBLIC_KEY={pub}")
    print(f"VAPID_PRIVATE_KEY={priv}")
    print("VAPID_SUBJECT=mailto:admin@example.com  # contact URI, change to a real one\n")
    print("The frontend needs the PUBLIC key too (safe to expose to the browser):")
    print(f"NEXT_PUBLIC_VAPID_PUBLIC_KEY={pub}")
