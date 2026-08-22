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


async def test_join_by_code_rejects_once_battle_is_full(client, monkeypatch):
    import app.services.elimination_service as elimination_service
    monkeypatch.setattr(elimination_service, "MAX_INVITEES_PER_BATTLE", 1)  # cap = host + 1

    _, host = await auth_headers(client)
    battle = await _create_battle(client, host, "Small Room")
    _, first = await auth_headers(client)
    joined = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=first)
    assert joined.status_code == 201, joined.text

    _, second = await auth_headers(client)
    full = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=second)
    assert full.status_code == 409, full.text


async def test_accepting_an_invitation_also_rejects_once_battle_is_full(client, monkeypatch):
    """respond_to_invitation used to add the accepting user as a participant
    with no capacity check at all — a battle already filled up to the cap
    via room-code joins could still be pushed past it by a late invite
    accept. Same cap enforced on both paths now."""
    import app.services.elimination_service as elimination_service
    monkeypatch.setattr(elimination_service, "MAX_INVITEES_PER_BATTLE", 1)  # cap = host + 1

    host_email, host = await auth_headers(client)
    host_id = (await client.get("/auth/me", headers=host)).json()["id"]
    invitee_email, invitee = await auth_headers(client)
    invitee_id = (await client.get("/auth/me", headers=invitee)).json()["id"]
    await _connect(client, host, host_id, invitee, invitee_id)

    battle = await _create_battle(client, host, "Small Room Invite")
    invited = await client.post(f"/elimination/battles/{battle['id']}/invite", json={"invitee_id": invitee_id}, headers=host)
    assert invited.status_code == 201, invited.text
    invitation_id = invited.json()["id"]

    # Fill the battle to the cap via room code before the invitee gets to it.
    _, filler = await auth_headers(client)
    filled = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=filler)
    assert filled.status_code == 201, filled.text

    accept = await client.post(f"/elimination/invitations/{invitation_id}/accept", headers=invitee)
    assert accept.status_code == 409, accept.text

    participants = (await client.get(f"/elimination/battles/{battle['id']}/participants", headers=host)).json()
    assert len(participants) == 2  # host + filler only — invitee was never added


async def test_starting_with_no_questions_yet_is_retryable_not_a_permanent_cancellation(client, monkeypatch):
    """Regression test for a real production failure: generation for a full
    elimination-battle question pool is batched to fit Sarvam's account
    token cap (see ai_provider.py) and confirmed live to take 60-190s —
    comfortably past _wait_for_questions's 18s wait, which is the ordinary
    case for a host starting soon after creating a battle, not a rare one.
    start_battle must NOT fall through to _activate_battle's hard-cancel
    path in that case (that used to turn "still generating" into
    permanently dead with no retry possible) — it must return a retryable
    error and leave the battle in "lobby" so a retry once generation lands
    can still succeed. No battle.started/battle.cancelled broadcast should
    fire either, since activation never actually starts."""
    from sqlalchemy import delete

    import app.services.elimination_service as elimination_service
    from app.database import AsyncSessionLocal
    from app.models.assessment import Question, QuestionOption
    from app.models.exam_platform import Subject, Topic

    # Keep the wait short so this test doesn't need the real 18s.
    monkeypatch.setattr(elimination_service, "_QUESTION_GENERATION_WAIT_SECONDS", 0.2)
    monkeypatch.setattr(elimination_service, "_QUESTION_GENERATION_POLL_INTERVAL_SECONDS", 0.05)

    broadcasts: list[dict] = []
    orig_broadcast = elimination_service.ws_manager.broadcast

    async def _spy_broadcast(room_id, message, **kwargs):
        broadcasts.append(message)
        return await orig_broadcast(room_id, message, **kwargs)

    monkeypatch.setattr(elimination_service.ws_manager, "broadcast", _spy_broadcast)

    _, host = await auth_headers(client)
    battle = await _create_battle(client, host, "Slow-Generating Battle")
    _, second_player = await auth_headers(client)
    joined = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=second_player)
    assert joined.status_code == 201, joined.text

    async with AsyncSessionLocal() as db:
        await db.execute(delete(Question).where(Question.topic_id == battle["topic_id"]))
        await db.commit()

    started = await client.post(f"/elimination/battles/{battle['id']}/start", headers=host)
    assert started.status_code == 422, started.text

    check = await client.get(f"/elimination/battles/{battle['id']}", headers=host)
    assert check.json()["status"] == "lobby", check.json()

    events = [b["event"] for b in broadcasts if b.get("battle_id") == battle["id"]]
    assert events == []

    # And once generation actually lands, a retry succeeds normally —
    # confirms this really is retryable, not just "doesn't crash".
    async with AsyncSessionLocal() as db:
        topic_row = await db.get(Topic, uuid_mod.UUID(battle["topic_id"]))
        subject_row = await db.get(Subject, topic_row.subject_id)
        question = Question(
            subject_id=subject_row.id, topic_id=topic_row.id, prompt="Q1", question_type="single",
            is_ai_generated=False, is_validated=True,
        )
        db.add(question)
        await db.flush()
        db.add(QuestionOption(question_id=question.id, text="A", is_correct=True, order_index=0))
        db.add(QuestionOption(question_id=question.id, text="B", is_correct=False, order_index=1))
        await db.commit()

    retried = await client.post(f"/elimination/battles/{battle['id']}/start", headers=host)
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "active"


async def test_sweep_loop_auto_start_still_cancels_and_broadcasts_when_truly_out_of_questions(client, monkeypatch):
    """The manual-host path (start_battle, tested above) now retries instead
    of cancelling when generation just hasn't finished yet — but the sweep
    loop's scheduled auto-start (_sweep_once -> _activate_battle, no host
    request to return a retryable error to) still needs to fail closed for
    a topic that genuinely has no questions, and still needs to tell every
    connected participant via a battle.cancelled broadcast, not just flip a
    DB column only the sweep loop itself sees."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import delete

    import app.services.elimination_service as elimination_service
    from app.database import AsyncSessionLocal
    from app.models.assessment import Question
    from app.services.elimination_service import _sweep_once

    broadcasts: list[dict] = []
    orig_broadcast = elimination_service.ws_manager.broadcast

    async def _spy_broadcast(room_id, message, **kwargs):
        broadcasts.append(message)
        return await orig_broadcast(room_id, message, **kwargs)

    monkeypatch.setattr(elimination_service.ws_manager, "broadcast", _spy_broadcast)

    _, host = await auth_headers(client)
    subject_name, topic_name = _unique_subject_topic()
    resp = await client.post("/elimination/battles", json={
        "title": "Scheduled Doomed Battle", "subject_name": subject_name, "topic_name": topic_name,
        "scheduled_start_at": (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
    }, headers=host)
    assert resp.status_code == 201, resp.text
    battle = resp.json()

    _, second_player = await auth_headers(client)
    joined = await client.post("/elimination/battles/join", json={"code": battle["join_code"]}, headers=second_player)
    assert joined.status_code == 201, joined.text

    async with AsyncSessionLocal() as db:
        await db.execute(delete(Question).where(Question.topic_id == battle["topic_id"]))
        await db.commit()

    import asyncio
    await asyncio.sleep(1.5)
    await _sweep_once()

    check = await client.get(f"/elimination/battles/{battle['id']}", headers=host)
    assert check.json()["status"] == "cancelled", check.json()

    events = [b["event"] for b in broadcasts if b.get("battle_id") == battle["id"]]
    assert events == ["battle.started", "battle.cancelled"]


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
