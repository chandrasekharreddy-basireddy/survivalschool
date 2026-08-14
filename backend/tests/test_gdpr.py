from __future__ import annotations

import pytest

from tests.conftest import VALID_PASSWORD, auth_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_export_requires_auth(client):
    resp = await client.get("/users/me/export")
    assert resp.status_code == 401


async def test_export_returns_downloadable_json_with_account_data(client):
    email, headers = await auth_headers(client)
    resp = await client.get("/users/me/export", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    assert "attachment;" in resp.headers["content-disposition"]

    body = resp.json()
    assert body["account"]["email"] == email
    assert "export_generated_at" in body
    for key in (
        "enrollments", "quiz_attempts", "exam_attempts", "certificates",
        "contest_attempts", "points_ledger", "achievements", "practice_sessions",
        "discussion_threads_authored", "chat_messages_sent", "notifications",
        "ai_conversations", "audit_log_as_actor",
    ):
        assert key in body
        assert isinstance(body[key], list)


async def test_delete_requires_auth(client):
    resp = await client.post("/users/me/delete-account", json={"password": "x", "confirm": "DELETE"})
    assert resp.status_code == 401


async def test_delete_requires_typed_confirmation(client):
    _, headers = await auth_headers(client)
    resp = await client.post("/users/me/delete-account", headers=headers, json={"password": VALID_PASSWORD, "confirm": "delete"})
    assert resp.status_code == 422

    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200  # account still exists


async def test_delete_requires_correct_password(client):
    _, headers = await auth_headers(client)
    resp = await client.post("/users/me/delete-account", headers=headers, json={"password": "WrongPassword1!", "confirm": "DELETE"})
    assert resp.status_code == 401

    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200


async def test_delete_account_removes_user_and_invalidates_session(client):
    email, headers = await auth_headers(client)

    resp = await client.post("/users/me/delete-account", headers=headers, json={"password": VALID_PASSWORD, "confirm": "DELETE"})
    assert resp.status_code == 200, resp.text

    # The access token that just deleted the account must no longer work.
    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 401

    # And the email is free to register again.
    register_resp = await client.post("/auth/register", json={"email": email, "password": VALID_PASSWORD, "full_name": "Reused Email"})
    assert register_resp.status_code == 201


async def test_delete_account_succeeds_even_after_profile_was_created(client):
    """Regression test: SQLAlchemy's unit-of-work defaults to
    disassociating a loaded one-to-one child (UPDATE profiles SET user_id =
    NULL ...) before deleting the parent, which fails outright because
    profiles.user_id is NOT NULL — the DB's own ON DELETE CASCADE is meant
    to handle this instead (see the passive_deletes=True comment on
    User.profile in app/models/user.py). Any real user who has ever loaded
    their profile (GET /users/me/profile, e.g. from a settings page) would
    hit this — so this test loads the profile first, exactly like a real
    frontend would, before deleting."""
    _, headers = await auth_headers(client)

    profile_resp = await client.get("/users/me/profile", headers=headers)
    assert profile_resp.status_code == 200

    resp = await client.post("/users/me/delete-account", headers=headers, json={"password": VALID_PASSWORD, "confirm": "DELETE"})
    assert resp.status_code == 200, resp.text

    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 401


async def test_deleted_account_data_is_actually_gone_from_export_path(client):
    """Sanity check that deletion isn't a soft no-op: re-registering the
    same email starts with a fresh, empty export, not the old account's
    history."""
    from tests.conftest import login, register_and_verify

    email = await register_and_verify(client)
    tokens = await login(client, email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    await client.post("/users/me/delete-account", headers=headers, json={"password": VALID_PASSWORD, "confirm": "DELETE"})

    new_email = await register_and_verify(client, email=email)
    assert new_email == email
    new_tokens = await login(client, email)
    new_headers = {"Authorization": f"Bearer {new_tokens['access_token']}"}
    export = await client.get("/users/me/export", headers=new_headers)
    assert export.status_code == 200
    assert export.json()["enrollments"] == []
    assert export.json()["points_ledger"] == []
