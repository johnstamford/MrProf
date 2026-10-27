"""Feature 2 focused checks: auth isolation, resume, idempotency, conflicts.

Run inside the api container against a disposable database:
  docker compose exec api pytest tests -q
"""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

TEST_DB = f"mrprof_test_{uuid.uuid4().hex[:8]}"
os.environ["MONGODB_DB"] = TEST_DB

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    from app.db import get_db

    for name in await get_db().client.list_database_names():
        if name.startswith("mrprof_test_"):
            await get_db().client.drop_database(name)


async def _create(client) -> dict:
    res = await client.post("/assessments")
    assert res.status_code == 201
    body = res.json()
    assert body["access_secret"] and body["assessment_id"].startswith("a_")
    return body


def _auth(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


async def test_create_and_resume(client):
    created = await _create(client)
    res = await client.get(f"/assessments/{created['assessment_id']}", headers=_auth(created["access_secret"]))
    assert res.status_code == 200
    assert res.json()["version"] == 1
    # secret hash is never exposed
    assert "secret" not in res.text and "hash" not in res.text


async def test_auth_isolation(client):
    created = await _create(client)
    other = await _create(client)
    assert (await client.get(f"/assessments/{created['assessment_id']}")).status_code == 401
    assert (
        await client.get(f"/assessments/{created['assessment_id']}", headers=_auth("wrong"))
    ).status_code == 401
    # cross-assessment secret must not work
    assert (
        await client.get(f"/assessments/{created['assessment_id']}", headers=_auth(other["access_secret"]))
    ).status_code == 401
    assert (await client.get("/assessments/a_doesnotexist", headers=_auth("x"))).status_code == 404


async def test_idempotent_stage_update_and_conflict(client):
    created = await _create(client)
    url = f"/assessments/{created['assessment_id']}/stage"
    headers = _auth(created["access_secret"])
    payload = {"base_version": 1, "idempotency_key": "key-12345678", "stage": "screening"}

    first = await client.patch(url, json=payload, headers=headers)
    assert first.status_code == 200 and first.json()["version"] == 2

    replay = await client.patch(url, json=payload, headers=headers)
    assert replay.status_code == 200
    assert replay.json() == {**first.json(), "replayed": True}

    # state advanced only once: exactly one idem entry
    from app.db import get_db

    doc = await get_db()["assessments"].find_one({"_id": created["assessment_id"]})
    assert doc["version"] == 2 and len(doc["idem"]) == 1

    stale = await client.patch(
        url, json={"base_version": 1, "idempotency_key": "key-87654321", "stage": "interview"}, headers=headers
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["current_version"] == 2
