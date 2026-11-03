"""F11-min: reviewer accept/amend/reject on stored evidence."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

UID = uuid.uuid4().hex[:8]


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


async def _poll(client, base, headers, tries: int = 30) -> dict:
    import asyncio

    for _ in range(tries):
        res = await client.get(f"{base}/interview/assessment", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        if body["status"] in ("followup", "review", "complete"):
            return body
        await asyncio.sleep(0.2)
    raise AssertionError("assessment stuck")


@pytest.fixture(scope="session")
async def finished(client):
    """A completed full journey with evidence + briefing stored."""
    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    res = await client.post(
        f"{base}/interview/start",
        json={"base_version": 1, "idempotency_key": f"rev-start-{UID}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    version = res.json()["version"]
    for i in range(14):
        res = await client.post(
            f"{base}/interview/answer",
            json={
                "answer_text": f"For example, last week at work area {i} slipped twice; it happens every week since January.",
                "base_version": version,
                "idempotency_key": f"rev-{UID}-{i}-{uuid.uuid4().hex[:4]}",
            },
            headers=headers,
        )
        assert res.status_code == 200, res.text
        version = res.json()["version"]
    final = await _poll(client, base, headers)
    assert final["status"] == "review", final
    # WS1: confirm the review step so the briefing (and evidence) exists.
    nxt = await client.get(f"{base}/interview/next", headers=headers)
    res = await client.post(
        f"{base}/interview/review/confirm",
        json={"base_version": nxt.json()["version"], "idempotency_key": f"rev-{UID}-{uuid.uuid4().hex[:4]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return {**created, "headers": headers, "base": base}


def _url(finished, turn=1, idx=0):
    return f"{finished['base']}/interview/evidence/{turn}/observations/{idx}"


async def test_review_accept_and_replay(client, finished):
    headers = finished["headers"]
    res = await client.get(f"{finished['base']}/interview/evidence", headers=headers)
    assert res.status_code == 200
    first = res.json()["turns"][0]
    version = first["version"]
    assert first["observations"][0]["review_status"] == "pending"

    before_t = await client.get(f"{finished['base']}/interview/transcript", headers=headers)
    screening = {"answers": ["never"] * 6}  # screening untouched by review (no screening taken here)
    _ = screening

    res = await client.patch(
        _url(finished), json={"action": "accept", "expected_version": version}, headers=headers
    )
    assert res.status_code == 200, res.text
    assert res.json()["review_status"] == "accepted" and res.json()["replayed"] is False

    replay = await client.patch(
        _url(finished), json={"action": "accept", "expected_version": version}, headers=headers
    )
    assert replay.status_code == 200 and replay.json()["replayed"] is True

    after = await client.get(f"{finished['base']}/interview/evidence", headers=headers)
    assert after.json()["turns"][0]["observations"][0]["review_status"] == "accepted"

    # Transcript verbatim text unchanged by review.
    after_t = await client.get(f"{finished['base']}/interview/transcript", headers=headers)
    assert after_t.json() == before_t.json()


async def test_review_amend_requires_note_and_reject(client, finished):
    headers = finished["headers"]
    res = await client.get(f"{finished['base']}/interview/evidence", headers=headers)
    version = res.json()["turns"][0]["version"]

    bad = await client.patch(
        _url(finished), json={"action": "amend", "expected_version": version}, headers=headers
    )
    assert bad.status_code == 422

    res = await client.patch(
        _url(finished),
        json={"action": "amend", "note": "actually describes planning, not focus", "expected_version": version},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["review_status"] == "amended"

    res = await client.patch(
        _url(finished), json={"action": "reject", "note": "quote is small talk", "expected_version": version},
        headers=headers,
    )
    assert res.status_code == 200 and res.json()["review_status"] == "rejected"

    # Stored briefing mirrors the review (derived report, not originals).
    rep = await client.get(f"{finished['base']}/interview/report", headers=headers)
    assert rep.status_code == 200
    first_topic = rep.json()["topics"][0]
    obs = [o for t in first_topic["turns"] for o in t["observations"]]
    assert obs and obs[0]["review_status"] == "rejected"
    assert obs[0]["review_note"] == "quote is small talk"


async def test_review_conflicts_and_not_found(client, finished):
    headers = finished["headers"]
    res = await client.patch(
        _url(finished), json={"action": "accept", "expected_version": 999}, headers=headers
    )
    assert res.status_code == 409

    res = await client.patch(
        f"{finished['base']}/interview/evidence/1/observations/99",
        json={"action": "accept", "expected_version": 1},
        headers=headers,
    )
    assert res.status_code == 404

    res = await client.patch(
        f"{finished['base']}/interview/evidence/99/observations/0",
        json={"action": "accept", "expected_version": 1},
        headers=headers,
    )
    assert res.status_code == 404

    res = await client.patch(
        _url(finished), json={"action": "endorse", "expected_version": 1}, headers=headers
    )
    assert res.status_code == 422


async def test_review_auth_isolation(client, finished):
    other = await _create(client)
    res = await client.patch(
        _url(finished), json={"action": "accept", "expected_version": 1}, headers=_auth(other["password"])
    )
    assert res.status_code == 401
    res = await client.patch(_url(finished), json={"action": "accept", "expected_version": 1})
    assert res.status_code == 401
