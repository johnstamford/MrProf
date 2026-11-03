"""WS1 review-and-confirm step: the user checks and confirms before any briefing."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.interview import PLAN_ORDER
from app.main import app


@pytest.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    from app.db import get_db

    for name in await get_db().client.list_database_names():
        if name.startswith("mrprof_test_"):
            await get_db().client.drop_database(name)


async def _create(client, password: str | None = None) -> dict:
    password = password or f"correct horse {uuid.uuid4().hex[:8]}"
    res = await client.post("/assessments", json={"password": password})
    assert res.status_code == 201
    body = res.json()
    return {"assessment_id": body["assessment_id"], "password": password, **body}


def _auth(password: str) -> dict:
    return {"Authorization": f"Bearer {password}"}


RICH = (
    "For example, last week at work I lost track of my tasks twice; "
    "it happens every week since January."
)


async def _answer(client, base, headers, text, version) -> dict:
    res = await client.post(
        f"{base}/interview/answer",
        json={
            "answer_text": text,
            "base_version": version,
            "idempotency_key": f"ws1-{uuid.uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


async def _poll(client, base, headers, tries: int = 30) -> dict:
    import asyncio

    for _ in range(tries):
        res = await client.get(f"{base}/interview/assessment", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        if body["status"] in ("review", "complete"):
            return body
        if body["status"] not in ("assessing", "processing", "followup"):
            raise AssertionError(f"unexpected status {body['status']}")
        await asyncio.sleep(0.2)
    raise AssertionError("assessment stuck")


async def _drive_to_review(client, created) -> tuple[dict, dict]:
    """Full round-1 journey; returns (headers, base). Ends at review."""
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    res = await client.post(
        f"{base}/interview/start",
        json={"base_version": 1, "idempotency_key": f"ws1-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    version = res.json()["version"]
    for _ in PLAN_ORDER:
        nxt = await client.get(f"{base}/interview/next", headers=headers)
        state = nxt.json()
        assert state["question"] is not None, state
        done = await _answer(client, base, headers, RICH, state["version"])
        version = done["version"]
        if done["status"] == "assessing":
            break
    final = await _poll(client, base, headers)
    assert final["status"] == "review", final
    return headers, base


async def _confirm(client, base, headers) -> dict:
    nxt = await client.get(f"{base}/interview/next", headers=headers)
    version = nxt.json()["version"]
    res = await client.post(
        f"{base}/interview/review/confirm",
        json={"base_version": version, "idempotency_key": f"ws1-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


async def test_no_briefing_before_confirm(client):
    created = await _create(client)
    headers, base = await _drive_to_review(client, created)
    # Direct report GET before confirm → 404.
    assert (await client.get(f"{base}/interview/report", headers=headers)).status_code == 404
    # Review state resumes read-only across requests (no in-memory session).
    nxt = await client.get(f"{base}/interview/next", headers=headers)
    assert nxt.json()["status"] == "review" and nxt.json()["question"] is None
    rev = await client.get(f"{base}/interview/review", headers=headers)
    assert rev.status_code == 200
    assert len(rev.json()["topics"]) == len(PLAN_ORDER)
    assert all(t["observations"] for t in rev.json()["topics"])


async def test_addition_correction_and_idempotent_confirm(client):
    import asyncio

    from app.db import get_db

    created = await _create(client)
    headers, base = await _drive_to_review(client, created)
    aid = created["assessment_id"]

    before_t = await client.get(f"{base}/interview/transcript", headers=headers)
    before_a = [s["text"] for s in before_t.json()["segments"] if s["turn"] == 1 and s["role"] == "A"]

    # Per-topic addition lands as a new verbatim addendum turn.
    nxt = await client.get(f"{base}/interview/next", headers=headers)
    version = nxt.json()["version"]
    addition = "One more thing: the morning school run is the worst part of my day."
    key1 = f"ws1-{uuid.uuid4().hex[:8]}"
    res = await client.post(
        f"{base}/interview/review/add",
        json={
            "objective": "forgetfulness",
            "answer_text": addition,
            "base_version": version,
            "idempotency_key": key1,
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    version = res.json()["version"]
    turn1 = res.json()["turn"]
    assert res.json()["objective"] == "forgetfulness"

    # Replay: same key returns the stored result, no duplicate turn.
    res = await client.post(
        f"{base}/interview/review/add",
        json={
            "objective": "forgetfulness",
            "answer_text": addition,
            "base_version": version - 1,
            "idempotency_key": key1,
        },
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json() == {
        "assessment_id": aid,
        "version": version,
        "turn": turn1,
        "objective": "forgetfulness",
        "replayed": True,
    }
    # A fresh key appends another addendum (additions are never merged).
    res = await client.post(
        f"{base}/interview/review/add",
        json={
            "objective": "forgetfulness",
            "answer_text": addition,
            "base_version": version,
            "idempotency_key": f"ws1-{uuid.uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    version = res.json()["version"]
    assert res.json()["turn"] != turn1

    # Per-observation correction: stored on the observation, original untouched.
    rev = await client.get(f"{base}/interview/review", headers=headers)
    first_obs_topic = next(t for t in rev.json()["topics"] if t["observations"])
    obs = first_obs_topic["observations"][0]
    res = await client.post(
        f"{base}/interview/review/correct",
        json={
            "turn": obs["turn"],
            "obs_index": obs["obs_index"],
            "answer_text": "What I meant: it is the noise, not the people.",
            "base_version": version,
            "idempotency_key": f"ws1-{uuid.uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    version = res.json()["version"]

    # Double correction with a fresh key is rejected; originals byte-identical.
    res = await client.post(
        f"{base}/interview/review/correct",
        json={
            "turn": obs["turn"],
            "obs_index": obs["obs_index"],
            "answer_text": "another try",
            "base_version": version,
            "idempotency_key": f"ws1-{uuid.uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert res.status_code == 409
    after_t = await client.get(f"{base}/interview/transcript", headers=headers)
    after_a = [s["text"] for s in after_t.json()["segments"] if s["turn"] == 1 and s["role"] == "A"]
    assert after_a == before_a
    assert any(addition in s["text"] for s in after_t.json()["segments"])

    # Confirm is idempotent: replay yields one briefing version.
    body = await _confirm(client, base, headers)
    assert body["report_version"] == 1 and body["replayed"] is False
    rep = await client.get(f"{base}/interview/report", headers=headers)
    assert rep.status_code == 200, rep.text
    briefing = rep.json()
    assert briefing["report_version"] == 1
    assert briefing["user_confirmed_at"] is not None
    topic = next(t for t in briefing["topics"] if t["objective"] == "forgetfulness")
    assert any(turn.get("correction") is None for turn in topic["turns"])  # originals kept
    assert any(addition in (turn.get("answer") or "") for turn in topic["turns"])
    corr_topic = next(t for t in briefing["topics"] if t["objective"] == first_obs_topic["objective"])
    assert any(
        o.get("user_correction") == "What I meant: it is the noise, not the people."
        for turn in corr_topic["turns"]
        for o in turn["observations"]
    )

    # Second confirm with a fresh key: already complete.
    nxt = await client.get(f"{base}/interview/next", headers=headers)
    res = await client.post(
        f"{base}/interview/review/confirm",
        json={"base_version": nxt.json()["version"], "idempotency_key": f"ws1-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 409

    # Exactly one briefing stored.
    db = get_db()
    assert await db["reports"].count_documents({"assessment_id": aid, "kind": "interview"}) == 1
    # Review endpoints close after completion.
    assert (await client.get(f"{base}/interview/review", headers=headers)).status_code == 404


async def test_topups_target_thinnest_areas(client):
    created = await _create(client)
    headers, base = await _drive_to_review(client, created)
    res = await client.post(f"{base}/interview/review/topups", headers=headers)
    assert res.status_code == 200, res.text
    # Rich answers leave nothing thin: no top-ups offered.
    assert res.json()["topups"] == []


async def test_taster_continue_to_full_and_briefing_v2(client):
    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    res = await client.post(
        f"{base}/interview/start",
        json={"base_version": 1, "idempotency_key": f"ws1-{uuid.uuid4().hex[:8]}", "mode": "taster"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    for _ in range(6):
        nxt = await client.get(f"{base}/interview/next", headers=headers)
        state = nxt.json()
        assert state["question"] is not None, state
        await _answer(client, base, headers, RICH, state["version"])
    final = await _poll(client, base, headers)
    assert final["status"] == "review", final
    body = await _confirm(client, base, headers)
    assert body["report_version"] == 1
    rep = await client.get(f"{base}/interview/report", headers=headers)
    assert rep.json()["mode"] == "taster"

    # Continue to the full interview on the same assessment.
    nxt = await client.get(f"{base}/interview/next", headers=headers)
    res = await client.post(
        f"{base}/interview/continue",
        json={"base_version": nxt.json()["version"], "idempotency_key": f"ws1-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["mode"] == "full"
    assert res.json()["question"] is not None

    # Answer the 8 remaining objectives, then confirm briefing v2.
    for _ in range(8):
        nxt = await client.get(f"{base}/interview/next", headers=headers)
        state = nxt.json()
        if state.get("completed") or state.get("question") is None:
            break
        await _answer(client, base, headers, RICH, state["version"])
    import asyncio

    for _ in range(30):
        poll = await client.get(f"{base}/interview/assessment", headers=headers)
        assert poll.status_code == 200
        if poll.json()["status"] == "review":
            break
        if poll.json()["status"] == "followup":
            nxt = await client.get(f"{base}/interview/next", headers=headers)
            state = nxt.json()
            await _answer(client, base, headers, RICH, state["version"])
        await asyncio.sleep(0.2)
    body = await _confirm(client, base, headers)
    assert body["report_version"] == 2
    rep = await client.get(f"{base}/interview/report", headers=headers)
    assert rep.json()["report_version"] == 2 and rep.json()["mode"] == "full"
    # Briefing v1 retained.
    from app.db import get_db

    assert await get_db()["reports"].count_documents({"assessment_id": created["assessment_id"], "kind": "interview"}) == 2
