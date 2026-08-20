from __future__ import annotations

import uuid

from tests.conftest import auth_headers, grant_role

pytestmark = __import__("pytest").mark.asyncio(loop_scope="session")


async def test_student_cannot_create_subject(client):
    _, headers = await auth_headers(client)
    unique = uuid.uuid4().hex[:8]
    resp = await client.post("/subjects", json={"name": f"Hacked {unique}", "slug": f"hacked-{unique}"}, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "authorization_error"


async def test_unauthenticated_request_is_401(client):
    resp = await client.get("/admin/dashboard")
    assert resp.status_code == 401


async def test_instructor_can_create_question_student_cannot(client):
    admin_email, admin_headers = await auth_headers(client)
    await grant_role(admin_email, "ADMIN")
    from tests.conftest import login
    admin_tokens = await login(client, admin_email)
    admin_headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}

    unique = uuid.uuid4().hex[:8]
    subject_id = (await client.post("/subjects", json={"name": f"RBAC Subject {unique}", "slug": f"rbac-subj-{unique}"}, headers=admin_headers)).json()["id"]
    topic_id = (await client.post(f"/subjects/{subject_id}/topics", json={"name": f"RBAC Topic {unique}", "slug": f"rbac-topic-{unique}"}, headers=admin_headers)).json()["id"]

    instructor_email, instructor_headers = await auth_headers(client)
    await grant_role(instructor_email, "INSTRUCTOR")
    instructor_tokens = await login(client, instructor_email)
    instructor_headers = {"Authorization": f"Bearer {instructor_tokens['access_token']}"}

    payload = {
        "subject_id": subject_id, "topic_id": topic_id, "prompt": "Real Question?", "question_type": "single", "points": 1,
        "options": [{"text": "Right", "is_correct": True, "order_index": 0}, {"text": "Wrong", "is_correct": False, "order_index": 1}],
    }

    _, student_headers = await auth_headers(client)
    forbidden = await client.post("/questions", json=payload, headers=student_headers)
    assert forbidden.status_code == 403

    allowed = await client.post("/questions", json=payload, headers=instructor_headers)
    assert allowed.status_code == 201, allowed.text


async def test_admin_permission_bypass_via_super_admin_role(client):
    email, headers = await auth_headers(client)
    await grant_role(email, "SUPER_ADMIN")
    from tests.conftest import login
    tokens = await login(client, email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = await client.get("/admin/dashboard", headers=headers)
    assert resp.status_code == 200
    assert "total_students" in resp.json()
