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


async def _create(client, password: str | None = None) -> dict:
    password = password or f"correct horse {uuid.uuid4().hex[:8]}"
    res = await client.post("/assessments", json={"password": password})
    assert res.status_code == 201
    body = res.json()
    assert len(body["assessment_id"]) == 8
    assert "secret" not in res.text and "password" not in body
    return {"assessment_id": body["assessment_id"], "password": password, **body}


def _auth(password: str) -> dict:
    return {"Authorization": f"Bearer {password}"}


async def test_create_rejects_short_password(client):
    res = await client.post("/assessments", json={"password": "short"})
    assert res.status_code == 422


async def test_create_and_resume(client):
    created = await _create(client)
    res = await client.get(f"/assessments/{created['assessment_id']}", headers=_auth(created["password"]))
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
        await client.get(f"/assessments/{created['assessment_id']}", headers=_auth(other["password"]))
    ).status_code == 401
    assert (await client.get("/assessments/a_doesnotexist", headers=_auth("x"))).status_code == 404


async def test_idempotent_stage_update_and_conflict(client):
    created = await _create(client)
    url = f"/assessments/{created['assessment_id']}/stage"
    headers = _auth(created["password"])
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
