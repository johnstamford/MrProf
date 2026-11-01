"""F13-min: consent/config, invite gate, delete cascade, rate limits."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.consent import CONSENT_VERSION
from app.main import app
from app.ratelimit import reset_rate_limits


@pytest.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    from app.db import get_db

    for name in await get_db().client.list_database_names():
        if name.startswith("mrprof_test_"):
            await get_db().client.drop_database(name)


async def _create(client, password: str | None = None, extra: dict | None = None) -> dict:
    password = password or f"correct horse {uuid.uuid4().hex[:8]}"
    payload = {"password": password, **(extra or {})}
    res = await client.post("/assessments", json=payload)
    assert res.status_code == 201, res.text
    body = res.json()
    return {"assessment_id": body["assessment_id"], "password": password, **body}


def _auth(password: str) -> dict:
    return {"Authorization": f"Bearer {password}"}


async def test_public_consent_and_config(client):
    res = await client.get("/consent")
    assert res.status_code == 200
    body = res.json()
    assert body["version"] == CONSENT_VERSION
    headings = [s["heading"] for s in body["sections"]]
    assert any("collect" in h.lower() for h in headings)
    assert any("monitor" in h.lower() for h in headings)
    assert any("retention" in h.lower() or "deletion" in h.lower() for h in headings)
    assert "model" in body and "provider" in body

    res = await client.get("/config")
    assert res.status_code == 200
    assert res.json()["consent_version"] == CONSENT_VERSION


async def test_consent_gate(client, monkeypatch):
    monkeypatch.setenv("REQUIRE_CONSENT", "1")
    bad = await client.post("/assessments", json={"password": f"correct horse {uuid.uuid4().hex[:8]}"})
    assert bad.status_code == 422
    wrong = await client.post(
        "/assessments",
        json={"password": f"correct horse {uuid.uuid4().hex[:8]}", "consent_accepted": True, "consent_version": "old"},
    )
    assert wrong.status_code == 422
    created = await _create(
        client, extra={"consent_accepted": True, "consent_version": CONSENT_VERSION}
    )
    assert created["consent_version"] == CONSENT_VERSION


async def test_invite_gate(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_INVITE_CODE", "opening-day")
    pw = lambda: f"correct horse {uuid.uuid4().hex[:8]}"  # noqa: E731
    res = await client.post("/assessments", json={"password": pw()})
    assert res.status_code == 403
    res = await client.post("/assessments", json={"password": pw(), "invite_code": "wrong"})
    assert res.status_code == 403
    res = await client.post("/assessments", json={"password": pw(), "invite_code": "opening-day"})
    assert res.status_code == 201


async def test_delete_cascades_across_linked_records(client):
    import asyncio

    created = await _create(
        client, extra={"consent_accepted": True, "consent_version": CONSENT_VERSION}
    )
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    res = await client.post(
        f"{base}/screening",
        json={
            "answers": ["sometimes"] * 6,
            "base_version": 1,
            "idempotency_key": f"del-scr-{uuid.uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert res.status_code == 200
    version = res.json()["version"]
    res = await client.post(
        f"{base}/interview/start",
        json={"base_version": version, "idempotency_key": f"del-st-{uuid.uuid4().hex[:8]}", "mode": "taster"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    version = res.json()["version"]
    for i in range(6):
        res = await client.post(
            f"{base}/interview/answer",
            json={
                "answer_text": f"delete-cascade detailed answer {i} with an example",
                "base_version": version,
                "idempotency_key": f"del-{uuid.uuid4().hex[:8]}",
            },
            headers=headers,
        )
        assert res.status_code == 200, res.text
        version = res.json()["version"]
    # Let the batch job finish so evidence + briefing exist before delete.
    for _ in range(30):
        res = await client.get(f"{base}/interview/assessment", headers=headers)
        if res.json()["status"] == "complete":
            break
        await asyncio.sleep(0.2)

    from app.db import get_db

    db = get_db()
    aid = created["assessment_id"]
    assert await db["evidence"].count_documents({"assessment_id": aid}) >= 6
    assert await db["reports"].count_documents({"assessment_id": aid}) >= 2

    res = await client.delete(base, headers=headers)
    assert res.status_code == 200, res.text
    deleted = res.json()["deleted"]
    assert deleted["assessments"] == 1 and deleted["transcripts"] == 1
    assert deleted["evidence"] >= 6 and deleted["reports"] >= 2

    assert await db["evidence"].count_documents({"assessment_id": aid}) == 0
    assert await db["reports"].count_documents({"assessment_id": aid}) == 0
    assert await db["transcripts"].find_one({"_id": aid}) is None

    # Everything behind the same authorization is gone too.
    assert (await client.get(base, headers=headers)).status_code == 404
    assert (await client.get(f"{base}/interview/report", headers=headers)).status_code == 404
    assert (await client.delete(base, headers=headers)).status_code == 404


async def test_delete_auth_isolation(client):
    created = await _create(client)
    other = await _create(client)
    base = f"/assessments/{created['assessment_id']}"
    assert (await client.delete(base)).status_code == 401
    assert (await client.delete(base, headers=_auth(other["password"]))).status_code == 401
    # Owner can still delete afterwards.
    assert (await client.delete(base, headers=_auth(created["password"]))).status_code == 200


async def test_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    reset_rate_limits()
    try:
        for _ in range(3):
            res = await client.post(
                "/assessments", json={"password": f"correct horse {uuid.uuid4().hex[:8]}"}
            )
            assert res.status_code == 201, res.text
        res = await client.post(
            "/assessments", json={"password": f"correct horse {uuid.uuid4().hex[:8]}"}
        )
        assert res.status_code == 429
        assert res.json()["error"] == "rate_limited"
    finally:
        reset_rate_limits()
