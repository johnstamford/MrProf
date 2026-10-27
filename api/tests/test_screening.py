"""Feature 3 focused checks: deterministic original 0-6 scoring, validation,
auth isolation, persistence/resume, idempotency + conflicts.

Run inside the api container: docker compose exec api pytest tests -q
"""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MONGODB_DB", "mrprof")

from app.asrs import (  # noqa: E402
    INSTRUMENT,
    SCORING_METHOD,
    score_answers,
)
from app.main import app  # noqa: E402


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


def test_unit_boundaries_and_thresholds():
    # All negative -> 0, not positive.
    assert score_answers(["never"] * 6) == (0, False, [False] * 6)
    # All very often -> 6, positive.
    assert score_answers(["very_often"] * 6) == (6, True, [True] * 6)
    # Exactly 3 positive -> below cutoff.
    score, positive, _ = score_answers(
        ["sometimes", "sometimes", "sometimes", "never", "never", "never"]
    )
    assert (score, positive) == (3, False)
    # Exactly 4 positive -> positive screen.
    score, positive, _ = score_answers(
        ["sometimes", "sometimes", "sometimes", "often", "never", "never"]
    )
    assert (score, positive) == (4, True)
    # Question-specific edges: Q1 Sometimes counts, Rarely does not.
    assert score_answers(["sometimes", "never", "never", "never", "never", "never"])[0] == 1
    assert score_answers(["rarely", "never", "never", "never", "never", "never"])[0] == 0
    # Q4 Sometimes does NOT count, Often does.
    assert score_answers(["never", "never", "never", "sometimes", "never", "never"])[0] == 0
    assert score_answers(["never", "never", "never", "often", "never", "never"])[0] == 1
    # Missing / invalid rejected, never scored as zero.
    for bad in (["never"] * 5, ["never"] * 7, ["never"] * 5 + ["occasionally"], []):
        try:
            score_answers(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {bad}")


async def test_submit_validation(client):
    created = await _create(client)
    url = f"/assessments/{created['assessment_id']}/screening"
    headers = _auth(created["password"])
    # Too few answers -> 422 (missing is not zero).
    res = await client.post(
        url, json={"answers": ["never"] * 5, "base_version": 1, "idempotency_key": "fk3-valid-0001"},
        headers=headers,
    )
    assert res.status_code == 422
    # Unknown label -> 422.
    res = await client.post(
        url,
        json={"answers": ["never"] * 5 + ["occasionally"], "base_version": 1, "idempotency_key": "fk3-valid-0002"},
        headers=headers,
    )
    assert res.status_code == 422


async def test_submit_and_resume(client):
    created = await _create(client)
    url = f"/assessments/{created['assessment_id']}/screening"
    headers = _auth(created["password"])
    answers = ["sometimes", "often", "never", "often", "rarely", "very_often"]
    res = await client.post(
        url, json={"answers": answers, "base_version": 1, "idempotency_key": "fk3-resume-0001"},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    # sometimes(Q1)+often(Q2)+often(Q4)+very_often(Q6) = 4 -> positive.
    assert body["score"] == 4 and body["positive"] is True and body["version"] == 2

    fetched = await client.get(url, headers=headers)
    assert fetched.status_code == 200
    data = fetched.json()
    assert data["instrument"] == INSTRUMENT
    assert data["scoring_method"] == SCORING_METHOD
    assert data["scoring_version"]
    assert data["answers"] == answers
    assert data["per_question_positive"] == [True, True, False, True, False, True]
    assert data["score"] == 4 and data["positive"] is True
    assert data["completed_at"]
    assert "secret" not in fetched.text and "hash" not in fetched.text


async def test_auth_isolation(client):
    created = await _create(client)
    other = await _create(client)
    url = f"/assessments/{created['assessment_id']}/screening"
    payload = {"answers": ["never"] * 6, "base_version": 1, "idempotency_key": "fk3-auth-0001"}
    assert (await client.post(url, json=payload)).status_code == 401
    assert (await client.post(url, json=payload, headers=_auth("wrong"))).status_code == 401
    assert (await client.post(url, json=payload, headers=_auth(other["password"]))).status_code == 401
    assert (await client.get(url)).status_code == 401
    assert (await client.get("/assessments/a_doesnotexist/screening", headers=_auth("x"))).status_code == 404


async def test_idempotent_submit_and_conflict(client):
    created = await _create(client)
    url = f"/assessments/{created['assessment_id']}/screening"
    headers = _auth(created["password"])
    payload = {"answers": ["never"] * 6, "base_version": 1, "idempotency_key": "fk3-idem-0001"}

    first = await client.post(url, json=payload, headers=headers)
    assert first.status_code == 200 and first.json()["version"] == 2

    replay = await client.post(url, json=payload, headers=headers)
    assert replay.status_code == 200
    assert replay.json() == {**first.json(), "replayed": True}

    from app.db import get_db

    doc = await get_db()["assessments"].find_one({"_id": created["assessment_id"]})
    assert doc["version"] == 2
    assert doc["screening"]["score"] == 0 and doc["screening"]["positive"] is False

    stale = await client.post(
        url,
        json={"answers": ["never"] * 6, "base_version": 1, "idempotency_key": "fk3-idem-0002"},
        headers=headers,
    )
    assert stale.status_code == 409
