"""Unit tests for the timing-attack mitigation in app/security/passwords.py.

A test that compares two live timing measurements against each other (dummy
path vs. real path) would be flaky under CI scheduler jitter — that's an
anti-pattern, not a real test. Instead this asserts the actual guarantee that
matters: verify_password_dummy() performs genuine Argon2id work rather than
being a no-op or fast-path shortcut, which is what makes it a valid stand-in
for the real hashing cost on the login "user not found" branch.
"""
from __future__ import annotations

import time

from app.security.passwords import _DUMMY_HASH, hash_password, verify_password_dummy


def test_dummy_hash_is_a_real_argon2id_hash():
    assert _DUMMY_HASH.startswith("$argon2id$"), (
        "the timing-safety dummy hash must be a genuine Argon2id hash — a "
        "plain string or a different (cheaper) algorithm would defeat the "
        "point of paying the same cost as a real verify"
    )


def test_verify_password_dummy_performs_real_hash_work():
    start = time.perf_counter()
    verify_password_dummy()
    elapsed = time.perf_counter() - start
    # The configured Argon2id cost (time_cost=3, memory_cost=64MiB) takes tens
    # of milliseconds on ordinary hardware. 5ms is a deliberately generous
    # floor — comfortably below what real hashing costs even on fast/loaded
    # CI, but high enough that a no-op or short-circuited implementation
    # would fail it. This checks an absolute floor, not a comparison between
    # two live measurements, so it isn't subject to relative-timing jitter.
    assert elapsed > 0.005, (
        f"verify_password_dummy() returned in {elapsed*1000:.2f}ms — too fast "
        "to be doing real Argon2id work, which defeats its purpose"
    )


def test_verify_password_dummy_is_same_order_of_magnitude_as_a_real_hash():
    # Sanity check using the *cost of hashing itself* (always genuinely slow,
    # no branching involved) as the yardstick, rather than comparing two
    # verify() calls against each other end-to-end.
    start = time.perf_counter()
    hash_password("some-real-looking-password-1A!")
    hash_elapsed = time.perf_counter() - start

    start = time.perf_counter()
    verify_password_dummy()
    dummy_elapsed = time.perf_counter() - start

    # verify() and hash() pay the same Argon2id cost function, so they should
    # be within a generous factor of each other — this guards against
    # verify_password_dummy() being accidentally wired to something far
    # cheaper than a real verify.
    assert dummy_elapsed > hash_elapsed * 0.3, (
        f"dummy verify ({dummy_elapsed*1000:.2f}ms) is suspiciously faster than "
        f"a real hash ({hash_elapsed*1000:.2f}ms) — it may not be doing real work"
    )
