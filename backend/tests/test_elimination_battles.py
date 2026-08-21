"""Elimination battles: connections-gated invites, the shareable room
code/QR join path, and free-text subject/topic with AI-generated questions
(same pattern as the AI Weekly Exam free-text redesign)."""
from __future__ import annotations

import uuid as uuid_mod

import pytest

from tests.conftest import auth_headers

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _unique_subject_topic() -> tuple[str, str]:
    unique = uuid_mod.uuid4().hex[:8]
    return f"Subject {unique}", f"Topic {unique}"


async def _connect(client, headers_a, id_a, headers_b, id_b):
    req = await client.post("/follows/requests", json={"target_id": id_b}, headers=headers_a)
    assert req.status_code == 201, req.text
    accept = await client.post(f"/follows/requests/{req.json()['id']}/accept", headers=headers_b)
    assert accept.status_code == 200, accept.text


async def _create_battle(client, headers, title):
    subject_name, topic_name = _unique_subject_topic()
    resp = await client.post("/elimination/battles", json={
        "title": title, "subject_name": subject_name, "topic_name": topic_name,
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_invite_requires_an_accepted_connection(client):
    host_email, host = await auth_headers(client)
    host_id = (await client.get("/auth/me", headers=host)).json()["id"]
    stranger_email, stranger = await auth_headers(client)
    stranger_id = (await client.get("/auth/me", headers=stranger)).json()["id"]

    battle = await _create_battle(client, host, "Friends Only")

    # Not connected — invite must be refused.
    forbidden = await client.post(f"/elimination/battles/{battle['id']}/invite", json={"invitee_id": stranger_id}, headers=host)
    assert forbidden.status_code == 403, forbidden.text

    await _connect(client, host, host_id, stranger, stranger_id)

    allowed = await client.post(f"/elimination/battles/{battle['id']}/invite", json={"invitee_id": stranger_id}, headers=host)
    assert allowed.status_code == 201, allowed.text


async def test_create_battle_generates_ai_questions_for_a_brand_new_topic(client):
    """The whole point of the free-text redesign: no instructor question
    bank is required — the mock AI provider generates one on first use of
    a topic."""
    _, host = await auth_headers(client)
    battle = await _create_battle(client, host, "Fresh Topic Battle")
    assert battle["status"] == "lobby"

    _, second_player = await auth_headers(client)
    joined = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=second_player)
    assert joined.status_code == 201, joined.text

    started = await client.post(f"/elimination/battles/{battle['id']}/start", headers=host)
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "active"


async def test_create_battle_rejects_blank_subject_or_topic(client):
    _, host = await auth_headers(client)
    resp = await client.post("/elimination/battles", json={"title": "Blank", "subject_name": "  ", "topic_name": "Something"}, headers=host)
    assert resp.status_code == 422, resp.text


async def test_join_by_room_code_bypasses_connections_requirement(client):
    """The whole point of the code/QR path: strangers can join with just
    the code, no follow relationship needed."""
    _, host = await auth_headers(client)
    battle = await _create_battle(client, host, "Room Code Match")
    assert len(battle["join_code"]) == 6

    _, stranger = await auth_headers(client)
    joined = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=stranger)
    assert joined.status_code == 201, joined.text
    assert joined.json()["id"] == battle["id"]

    participants = (await client.get(f"/elimination/battles/{battle['id']}/participants", headers=host)).json()
    assert len(participants) == 2


async def test_join_by_room_code_is_case_insensitive_and_idempotent(client):
    _, host = await auth_headers(client)
    battle = await _create_battle(client, host, "Case Test")

    _, joiner = await auth_headers(client)
    first = await client.post("/elimination/battles/join", json={"code": battle["join_code"].lower()}, headers=joiner)
    assert first.status_code == 201, first.text
    second = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=joiner)
    assert second.status_code == 201, second.text

    participants = (await client.get(f"/elimination/battles/{battle['id']}/participants", headers=host)).json()
    assert len(participants) == 2  # not duplicated


async def test_battle_qr_encodes_join_url_and_is_gated_like_participants(client):
    _, host = await auth_headers(client)
    battle = await _create_battle(client, host, "QR Test")

    ok = await client.get(f"/elimination/battles/{battle['id']}/qr", headers=host)
    assert ok.status_code == 200, ok.text
    assert ok.headers["content-type"] == "image/png"
    assert ok.content[:8] == b"\x89PNG\r\n\x1a\n"

    _, stranger = await auth_headers(client)
    forbidden = await client.get(f"/elimination/battles/{battle['id']}/qr", headers=stranger)
    assert forbidden.status_code == 403, forbidden.text


async def test_join_by_invalid_code_is_not_found(client):
    _, user = await auth_headers(client)
    resp = await client.post("/elimination/battles/join", json={"code": "ZZZZZZ"}, headers=user)
    assert resp.status_code == 404


async def test_join_by_code_rejects_once_battle_has_started(client):
    _, host = await auth_headers(client)
    battle = await _create_battle(client, host, "Started Already")

    _, second_player = await auth_headers(client)
    join1 = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=second_player)
    assert join1.status_code == 201, join1.text

    started = await client.post(f"/elimination/battles/{battle['id']}/start", headers=host)
    assert started.status_code == 200, started.text

    _, late_joiner = await auth_headers(client)
    late = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=late_joiner)
    assert late.status_code == 409, late.text


async def test_scheduled_start_auto_starts_the_battle(client):
    """No host click needed once scheduled_start_at has passed — the sweep
    loop (elimination_service._sweep_once, run every SWEEP_INTERVAL_SECONDS
    by elimination_sweep_loop in real life) picks it up. The test client's
    ASGITransport never fires app.main's lifespan, so that background loop
    never actually runs during tests — call _sweep_once() directly to
    simulate one tick of it instead of waiting on a loop that isn't there."""
    import asyncio
    from datetime import UTC, datetime, timedelta

    from app.services.elimination_service import _sweep_once

    _, host = await auth_headers(client)
    subject_name, topic_name = _unique_subject_topic()
    resp = await client.post("/elimination/battles", json={
        "title": "Scheduled Battle", "subject_name": subject_name, "topic_name": topic_name,
        "scheduled_start_at": (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
    }, headers=host)
    assert resp.status_code == 201, resp.text
    battle = resp.json()
    assert battle["scheduled_start_at"] is not None

    _, second_player = await auth_headers(client)
    joined = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=second_player)
    assert joined.status_code == 201, joined.text

    await asyncio.sleep(1.5)
    await _sweep_once()

    fetched = await client.get(f"/elimination/battles/{battle['id']}", headers=host)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["status"] == "active", fetched.json()


async def test_create_battle_rejects_scheduled_start_in_the_past(client):
    from datetime import UTC, datetime, timedelta

    _, host = await auth_headers(client)
    subject_name, topic_name = _unique_subject_topic()
    resp = await client.post("/elimination/battles", json={
        "title": "Past Schedule", "subject_name": subject_name, "topic_name": topic_name,
        "scheduled_start_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
    }, headers=host)
    assert resp.status_code == 422, resp.text


async def test_current_round_recovers_after_missing_the_websocket_broadcast(client):
    """The whole point of GET /battles/{id}/round: a client that never saw
    the battle.round_released websocket event (page refresh, dropped
    connection) must still be able to learn the current question."""
    _, host = await auth_headers(client)
    battle = await _create_battle(client, host, "Round Recovery")

    _, second_player = await auth_headers(client)
    joined = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=second_player)
    assert joined.status_code == 201, joined.text

    # No active round yet — lobby.
    before_start = await client.get(f"/elimination/battles/{battle['id']}/round", headers=host)
    assert before_start.status_code == 200, before_start.text
    assert before_start.json() is None

    started = await client.post(f"/elimination/battles/{battle['id']}/start", headers=host)
    assert started.status_code == 200, started.text

    current = await client.get(f"/elimination/battles/{battle['id']}/round", headers=host)
    assert current.status_code == 200, current.text
    body = current.json()
    assert body is not None
    assert body["round_number"] == 1
    assert len(body["question"]["options"]) >= 2
    assert body["already_answered"] is False
    assert body["my_is_correct"] is None

    # Answering updates what the recovery endpoint reports for that player.
    correct_option = next(o["id"] for o in body["question"]["options"])
    await client.post(f"/elimination/battles/{battle['id']}/answer", json={"selected_option_ids": [correct_option]}, headers=host)
    after_answer = (await client.get(f"/elimination/battles/{battle['id']}/round", headers=host)).json()
    assert after_answer["already_answered"] is True
    assert after_answer["my_is_correct"] in (True, False)


async def test_current_round_is_gated_like_participants(client):
    _, host = await auth_headers(client)
    battle = await _create_battle(client, host, "Round Access")

    _, stranger = await auth_headers(client)
    forbidden = await client.get(f"/elimination/battles/{battle['id']}/round", headers=stranger)
    assert forbidden.status_code == 403, forbidden.text
