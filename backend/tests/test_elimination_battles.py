"""Elimination battles: the two new access-control paths added alongside
the AI Weekly Exam free-text redesign — invites are now connections-gated,
and a shareable room code/QR lets anyone join without an invite at all
(the "custom match, invite by room code" request)."""
from __future__ import annotations

import uuid as uuid_mod

import pytest

from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _make_admin(client):
    from tests.conftest import grant_role, login
    email, headers = await auth_headers(client)
    await grant_role(email, "ADMIN")
    tokens = await login(client, email)
    return email, {"Authorization": f"Bearer {tokens['access_token']}"}


async def _seed_topic(client, admin_headers):
    unique = uuid_mod.uuid4().hex[:8]
    subject_id = (await client.post("/subjects", json={"name": f"Subject {unique}", "slug": f"subj-{unique}"}, headers=admin_headers)).json()["id"]
    topic_id = (await client.post(f"/subjects/{subject_id}/topics", json={"name": f"Topic {unique}", "slug": f"topic-{unique}"}, headers=admin_headers)).json()["id"]
    return topic_id


async def _connect(client, headers_a, id_a, headers_b, id_b):
    req = await client.post("/follows/requests", json={"target_id": id_b}, headers=headers_a)
    assert req.status_code == 201, req.text
    accept = await client.post(f"/follows/requests/{req.json()['id']}/accept", headers=headers_b)
    assert accept.status_code == 200, accept.text


async def test_invite_requires_an_accepted_connection(client):
    _, admin = await _make_admin(client)
    topic_id = await _seed_topic(client, admin)

    host_email, host = await auth_headers(client)
    host_id = (await client.get("/auth/me", headers=host)).json()["id"]
    stranger_email, stranger = await auth_headers(client)
    stranger_id = (await client.get("/auth/me", headers=stranger)).json()["id"]

    battle = (await client.post("/elimination/battles", json={"title": "Friends Only", "topic_id": topic_id}, headers=host)).json()

    # Not connected — invite must be refused.
    forbidden = await client.post(f"/elimination/battles/{battle['id']}/invite", json={"invitee_id": stranger_id}, headers=host)
    assert forbidden.status_code == 403, forbidden.text

    await _connect(client, host, host_id, stranger, stranger_id)

    allowed = await client.post(f"/elimination/battles/{battle['id']}/invite", json={"invitee_id": stranger_id}, headers=host)
    assert allowed.status_code == 201, allowed.text


async def test_join_by_room_code_bypasses_connections_requirement(client):
    """The whole point of the code/QR path: strangers can join with just
    the code, no follow relationship needed."""
    _, admin = await _make_admin(client)
    topic_id = await _seed_topic(client, admin)

    _, host = await auth_headers(client)
    battle = (await client.post("/elimination/battles", json={"title": "Room Code Match", "topic_id": topic_id}, headers=host)).json()
    assert len(battle["join_code"]) == 6

    _, stranger = await auth_headers(client)
    joined = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=stranger)
    assert joined.status_code == 201, joined.text
    assert joined.json()["id"] == battle["id"]

    participants = (await client.get(f"/elimination/battles/{battle['id']}/participants", headers=host)).json()
    assert len(participants) == 2


async def test_join_by_room_code_is_case_insensitive_and_idempotent(client):
    _, admin = await _make_admin(client)
    topic_id = await _seed_topic(client, admin)

    _, host = await auth_headers(client)
    battle = (await client.post("/elimination/battles", json={"title": "Case Test", "topic_id": topic_id}, headers=host)).json()

    _, joiner = await auth_headers(client)
    first = await client.post("/elimination/battles/join", json={"code": battle["join_code"].lower()}, headers=joiner)
    assert first.status_code == 201, first.text
    second = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=joiner)
    assert second.status_code == 201, second.text

    participants = (await client.get(f"/elimination/battles/{battle['id']}/participants", headers=host)).json()
    assert len(participants) == 2  # not duplicated


async def test_join_by_invalid_code_is_not_found(client):
    _, user = await auth_headers(client)
    resp = await client.post("/elimination/battles/join", json={"code": "ZZZZZZ"}, headers=user)
    assert resp.status_code == 404


async def test_join_by_code_rejects_once_battle_has_started(client):
    from tests.conftest import grant_role, login

    _, admin = await _make_admin(client)
    unique = uuid_mod.uuid4().hex[:8]
    subject_id = (await client.post("/subjects", json={"name": f"S {unique}", "slug": f"s-{unique}"}, headers=admin)).json()["id"]
    topic_id = (await client.post(f"/subjects/{subject_id}/topics", json={"name": f"T {unique}", "slug": f"t-{unique}"}, headers=admin)).json()["id"]

    instructor_email, _ = await auth_headers(client)
    await grant_role(instructor_email, "INSTRUCTOR")
    instr_tokens = await login(client, instructor_email)
    instructor = {"Authorization": f"Bearer {instr_tokens['access_token']}"}
    await client.post("/questions", json={
        "subject_id": subject_id, "topic_id": topic_id, "prompt": "Q?", "question_type": "single", "points": 1,
        "options": [{"text": "Right", "is_correct": True, "order_index": 0}, {"text": "Wrong", "is_correct": False, "order_index": 1}],
    }, headers=instructor)

    _, host = await auth_headers(client)
    battle = (await client.post("/elimination/battles", json={"title": "Started Already", "topic_id": topic_id}, headers=host)).json()

    _, second_player = await auth_headers(client)
    join1 = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=second_player)
    assert join1.status_code == 201, join1.text

    started = await client.post(f"/elimination/battles/{battle['id']}/start", headers=host)
    assert started.status_code == 200, started.text

    _, late_joiner = await auth_headers(client)
    late = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=late_joiner)
    assert late.status_code == 409, late.text
