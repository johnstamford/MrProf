"""Feature 4 focused checks: deterministic report, safe copy, reopen, handoff.

Run inside the api container: docker compose exec api pytest tests -q
"""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MONGODB_DB", "mrprof")

from app.main import app  # noqa: E402

BANNED = ["diagnos", "probab", "%", "severe", "severity", "mild", "moderate", "rules out", "rule out"]


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


async def _submit(client, created: dict, answers: list[str], key: str, base: int = 1):
    url = f"/assessments/{created['assessment_id']}/screening"
    res = await client.post(
        url,
        json={"answers": answers, "base_version": base, "idempotency_key": key},
        headers=_auth(created["password"]),
    )
    assert res.status_code == 200, res.text
    return res.json()


async def _report(client, created: dict, expect: int = 200):
    url = f"/assessments/{created['assessment_id']}/screening/report"
    res = await client.get(url, headers=_auth(created["password"]))
    assert res.status_code == expect, res.text
    return res.json() if expect == 200 else None


def _assert_safe(report: dict, positive: bool) -> None:
    assert report["scoring_method"] == "original-0-6"
    assert report["cutoff"] == 4
    assert report["positive"] is positive
    assert len(report["answers"]) == 6
    assert report["interview_offer"]["offered"] is True
    assert report["interview_offer"]["next_stage"] == "interview"
    assert len(report["next_section"]["topics"]) == 6
    text = (report["explanation"] + report["interview_offer"]["note"]).lower()
    for word in BANNED:
        assert word not in text, f"banned language in report: {word}"
    if positive:
        assert "further assessment may be useful" in report["explanation"]
    else:
        assert "does not exclude" in report["explanation"]


async def test_report_missing_before_screening(client):
    created = await _create(client)
    await _report(client, created, expect=404)


async def test_positive_report(client):
    created = await _create(client)
    answers = ["sometimes", "often", "never", "often", "rarely", "very_often"]
    await _submit(client, created, answers, "fk4-positive-0001")
    report = await _report(client, created)
    assert report["report_version"] == 1
    _assert_safe(report, True)
    assert report["score"] == 4
    assert [a["answer"] for a in report["answers"]] == [
        "Sometimes", "Often", "Never", "Often", "Rarely", "Very often",
    ]


async def test_below_threshold_report_and_reopen(client):
    created = await _create(client)
    await _submit(client, created, ["never"] * 6, "fk4-below-0001")
    first = await _report(client, created)
    _assert_safe(first, False)
    assert first["score"] == 0
    # Reopen returns the same versioned report.
    second = await _report(client, created)
    assert second == first


async def test_report_auth_isolation(client):
    created = await _create(client)
    await _submit(client, created, ["never"] * 6, "fk4-iso-0001")
    url = f"/assessments/{created['assessment_id']}/screening/report"
    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers=_auth("wrong-password-x"))).status_code == 401


async def test_resubmit_versions_report(client):
    created = await _create(client)
    await _submit(client, created, ["never"] * 6, "fk4-ver-0001")
    assert (await _report(client, created))["report_version"] == 1
    await _submit(
        client,
        created,
        ["sometimes", "often", "sometimes", "often", "often", "often"],
        "fk4-ver-0002",
        base=2,
    )
    updated = await _report(client, created)
    assert updated["report_version"] == 2
    assert updated["score"] == 6 and updated["positive"] is True
