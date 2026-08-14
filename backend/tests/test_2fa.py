from __future__ import annotations

import pyotp
import pytest

from tests.conftest import VALID_PASSWORD, auth_headers, login

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _enable_2fa(client, headers: dict) -> tuple[str, list[str]]:
    """Runs the full setup -> confirm flow and returns (secret, backup_codes)."""
    setup_resp = await client.post("/auth/2fa/setup", headers=headers)
    assert setup_resp.status_code == 200, setup_resp.text
    body = setup_resp.json()
    assert body["secret"]
    assert body["otpauth_url"].startswith("otpauth://totp/")
    assert body["qr_code_data_uri"].startswith("data:image/png;base64,")

    secret = body["secret"]
    code = pyotp.TOTP(secret).now()
    confirm_resp = await client.post("/auth/2fa/confirm", headers=headers, json={"code": code})
    assert confirm_resp.status_code == 200, confirm_resp.text
    backup_codes = confirm_resp.json()["backup_codes"]
    assert len(backup_codes) == 8
    assert len(set(backup_codes)) == 8
    return secret, backup_codes


async def test_setup_requires_auth(client):
    resp = await client.post("/auth/2fa/setup")
    assert resp.status_code == 401


async def test_full_enroll_flow_and_me_reflects_enabled(client):
    email, headers = await auth_headers(client)
    await _enable_2fa(client, headers)

    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["totp_enabled"] is True


async def test_confirm_rejects_wrong_code(client):
    email, headers = await auth_headers(client)
    setup_resp = await client.post("/auth/2fa/setup", headers=headers)
    assert setup_resp.status_code == 200

    bad_resp = await client.post("/auth/2fa/confirm", headers=headers, json={"code": "000000"})
    assert bad_resp.status_code == 422

    me = await client.get("/auth/me", headers=headers)
    assert me.json()["totp_enabled"] is False


async def test_confirm_without_setup_rejected(client):
    _, headers = await auth_headers(client)
    resp = await client.post("/auth/2fa/confirm", headers=headers, json={"code": "123456"})
    assert resp.status_code == 422


async def test_setup_twice_conflicts_once_enabled(client):
    _, headers = await auth_headers(client)
    await _enable_2fa(client, headers)

    resp = await client.post("/auth/2fa/setup", headers=headers)
    assert resp.status_code == 409


async def test_login_with_2fa_enabled_returns_mfa_challenge_not_tokens(client):
    email, headers = await auth_headers(client)
    await _enable_2fa(client, headers)

    login_resp = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    assert login_resp.status_code == 200
    body = login_resp.json()
    assert body.get("mfa_required") is True
    assert body.get("mfa_token")
    assert "access_token" not in body


async def test_verify_login_with_valid_totp_code_issues_tokens(client):
    email, headers = await auth_headers(client)
    secret, _ = await _enable_2fa(client, headers)

    login_resp = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    mfa_token = login_resp.json()["mfa_token"]

    code = pyotp.TOTP(secret).now()
    verify_resp = await client.post("/auth/2fa/verify-login", json={"mfa_token": mfa_token, "code": code})
    assert verify_resp.status_code == 200, verify_resp.text
    tokens = verify_resp.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == email


async def test_verify_login_with_wrong_code_rejected(client):
    email, headers = await auth_headers(client)
    await _enable_2fa(client, headers)

    login_resp = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    mfa_token = login_resp.json()["mfa_token"]

    resp = await client.post("/auth/2fa/verify-login", json={"mfa_token": mfa_token, "code": "000000"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_2fa_code"


async def test_verify_login_with_garbage_mfa_token_rejected(client):
    resp = await client.post("/auth/2fa/verify-login", json={"mfa_token": "not-a-real-jwt", "code": "123456"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "mfa_session_expired"


async def test_mfa_pending_token_cannot_be_used_as_bearer_token(client):
    """The mfa_pending JWT must be rejected by get_current_user's
    type != 'access' check -- it must never work as a real access token
    anywhere else in the API, even though it's a validly-signed JWT."""
    email, headers = await auth_headers(client)
    await _enable_2fa(client, headers)

    login_resp = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    mfa_token = login_resp.json()["mfa_token"]

    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {mfa_token}"})
    assert resp.status_code == 401


async def test_backup_code_consumed_on_use_and_cannot_be_reused(client):
    email, headers = await auth_headers(client)
    _, backup_codes = await _enable_2fa(client, headers)
    one_code = backup_codes[0]

    login_resp = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    mfa_token = login_resp.json()["mfa_token"]

    first_use = await client.post("/auth/2fa/verify-login", json={"mfa_token": mfa_token, "code": one_code})
    assert first_use.status_code == 200, first_use.text

    # Same backup code must not work a second time, even against a fresh
    # mfa_token from a new login attempt.
    login_resp2 = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    mfa_token2 = login_resp2.json()["mfa_token"]
    second_use = await client.post("/auth/2fa/verify-login", json={"mfa_token": mfa_token2, "code": one_code})
    assert second_use.status_code == 401
    assert second_use.json()["error"]["code"] == "invalid_2fa_code"


async def test_backup_code_case_and_whitespace_insensitive(client):
    email, headers = await auth_headers(client)
    _, backup_codes = await _enable_2fa(client, headers)
    one_code = backup_codes[0]

    login_resp = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    mfa_token = login_resp.json()["mfa_token"]

    messy_code = f" {one_code.lower()} "
    resp = await client.post("/auth/2fa/verify-login", json={"mfa_token": mfa_token, "code": messy_code})
    assert resp.status_code == 200, resp.text


async def test_disable_requires_correct_password(client):
    _, headers = await auth_headers(client)
    await _enable_2fa(client, headers)

    resp = await client.post("/auth/2fa/disable", headers=headers, json={"password": "WrongPassword1!"})
    assert resp.status_code == 401

    me = await client.get("/auth/me", headers=headers)
    assert me.json()["totp_enabled"] is True


async def test_disable_with_correct_password_turns_off_2fa_and_login_returns_tokens_again(client):
    email, headers = await auth_headers(client)
    await _enable_2fa(client, headers)

    resp = await client.post("/auth/2fa/disable", headers=headers, json={"password": VALID_PASSWORD})
    assert resp.status_code == 200

    me = await client.get("/auth/me", headers=headers)
    assert me.json()["totp_enabled"] is False

    tokens = await login(client, email, VALID_PASSWORD)
    assert tokens["access_token"]


async def test_disabled_backup_codes_do_not_survive_re_enrollment(client):
    """After disable, totp_backup_codes is cleared -- a code from a prior
    enrollment must not work against a freshly re-enabled 2FA setup."""
    email, headers = await auth_headers(client)
    _, old_backup_codes = await _enable_2fa(client, headers)

    await client.post("/auth/2fa/disable", headers=headers, json={"password": VALID_PASSWORD})
    await _enable_2fa(client, headers)

    login_resp = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    mfa_token = login_resp.json()["mfa_token"]

    resp = await client.post("/auth/2fa/verify-login", json={"mfa_token": mfa_token, "code": old_backup_codes[0]})
    assert resp.status_code == 401
