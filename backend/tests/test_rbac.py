from __future__ import annotations

from tests.conftest import auth_headers, grant_role

pytestmark = __import__("pytest").mark.asyncio(loop_scope="session")


async def test_student_cannot_create_course(client):
    _, headers = await auth_headers(client)
    resp = await client.post("/courses", json={"title": "Hacked", "slug": "hacked-course-1"}, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "authorization_error"


async def test_unauthenticated_request_is_401(client):
    resp = await client.get("/admin/dashboard")
    assert resp.status_code == 401


async def test_instructor_can_create_course_student_cannot_publish_others(client):
    instructor_email, instructor_headers = await auth_headers(client)
    await grant_role(instructor_email, "INSTRUCTOR")
    # Re-login so the JWT picks up the freshly-granted role (roles are baked
    # into the access token at issue time, by design — least-privilege until refresh).
    from tests.conftest import login
    tokens = await login(client, instructor_email)
    instructor_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = await client.post("/courses", json={"title": "Real Course", "slug": "real-course-rbac-1"}, headers=instructor_headers)
    assert resp.status_code == 201
    course_id = resp.json()["id"]

    _, student_headers = await auth_headers(client)
    forbidden = await client.post(f"/courses/{course_id}/publish", headers=student_headers)
    assert forbidden.status_code == 403

    allowed = await client.post(f"/courses/{course_id}/publish", headers=instructor_headers)
    assert allowed.status_code == 200
    assert allowed.json()["is_published"] is True


async def test_admin_permission_bypass_via_super_admin_role(client):
    email, headers = await auth_headers(client)
    await grant_role(email, "SUPER_ADMIN")
    from tests.conftest import login
    tokens = await login(client, email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = await client.get("/admin/dashboard", headers=headers)
    assert resp.status_code == 200
    assert "total_students" in resp.json()
