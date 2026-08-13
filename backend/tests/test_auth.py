from __future__ import annotations

from tests.conftest import VALID_PASSWORD, register_and_verify, unique_email

pytestmark = __import__("pytest").mark.asyncio(loop_scope="session")


async def test_register_rejects_weak_password(client):
    resp = await client.post("/auth/register", json={
        "email": unique_email(), "password": "weak", "full_name": "Weak Pw",
    })
    assert resp.status_code == 422


async def test_register_login_verify_flow(client):
    email = unique_email()
    resp = await client.post("/auth/register", json={"email": email, "password": VALID_PASSWORD, "full_name": "Flow User"})
    assert resp.status_code == 201
    assert resp.json()["is_email_verified"] is False

    # Unverified users can register/login but must not be treated as verified.
    login_resp = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    assert login_resp.status_code == 200
    access = login_resp.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.json()["is_email_verified"] is False


async def test_duplicate_registration_conflicts(client):
    email = unique_email()
    await client.post("/auth/register", json={"email": email, "password": VALID_PASSWORD, "full_name": "Dup"})
    resp = await client.post("/auth/register", json={"email": email, "password": VALID_PASSWORD, "full_name": "Dup"})
    assert resp.status_code == 409


async def test_login_wrong_password_is_generic(client):
    email = await register_and_verify(client)
    resp = await client.post("/auth/login", json={"email": email, "password": "WrongPassword1!"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_account_locks_after_repeated_failures(client):
    email = await register_and_verify(client)
    for _ in range(5):
        await client.post("/auth/login", json={"email": email, "password": "WrongPassword1!"})
    resp = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "account_locked"


async def test_refresh_token_rotation_and_reuse_detection(client):
    email = await register_and_verify(client)
    login_resp = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    refresh_token = login_resp.json()["refresh_token"]

    first = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert first.status_code == 200
    new_access = first.json()["access_token"]

    # Reusing the now-rotated-away token must fail and revoke the session.
    second = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "token_reuse_detected"

    # The access token minted from that now-revoked session must also stop working.
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    assert me.status_code == 401


async def test_logout_all_revokes_sessions(client):
    email = await register_and_verify(client)
    login_resp = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    access = login_resp.json()["access_token"]
    refresh = login_resp.json()["refresh_token"]

    logout_resp = await client.post("/auth/logout-all", headers={"Authorization": f"Bearer {access}"})
    assert logout_resp.status_code == 200

    refresh_resp = await client.post("/auth/refresh", json={"refresh_token": refresh})
    assert refresh_resp.status_code == 401


async def test_password_reset_revokes_existing_sessions(client):
    from tests.conftest import _last_token_for

    email = await register_and_verify(client)
    login_resp = await client.post("/auth/login", json={"email": email, "password": VALID_PASSWORD})
    old_access = login_resp.json()["access_token"]

    await client.post("/auth/forgot-password", json={"email": email})
    reset_token = _last_token_for(email, "password_reset")
    new_password = "Br4nd$NewPassword1"
    reset_resp = await client.post("/auth/reset-password", json={"token": reset_token, "new_password": new_password})
    assert reset_resp.status_code == 200

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {old_access}"})
    assert me.status_code == 401

    relogin = await client.post("/auth/login", json={"email": email, "password": new_password})
    assert relogin.status_code == 200
