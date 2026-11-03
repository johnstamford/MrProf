"""Provisional sketch: deterministic mapping, hard limits, env gating."""

import os

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.provisional import build_provisional_sketch, sketch_mode


def _cov(statuses: dict) -> list[dict]:
    return [
        {"objective": oid, "title": oid, "status": st, "note": "t", "turns": [1]}
        for oid, st in statuses.items()
    ]


def test_sketch_never_diagnoses():
    coverage = _cov({f"o{i}": "covered" for i in range(6)})
    out = build_provisional_sketch(
        coverage, {"score": 6, "positive": True, "scoring_method": "original-0-6"}
    )
    assert out["experimental"] is True
    assert "not a medical conclusion" in out["headline"]
    blob = " ".join(out["lines"]).lower()
    for banned in ("you have adhd", "probability", "severity", "mild", "moderate", "severe", "%"):
        assert banned not in blob, banned
    assert "clinician" in blob
    # Below threshold: no condition pointed at.
    out2 = build_provisional_sketch(
        coverage, {"score": 1, "positive": False, "scoring_method": "original-0-6"}
    )
    blob2 = " ".join(out2["lines"]).lower()
    assert "adhd assessment" not in blob2
    assert "does not exclude" in blob2
    # Denials and uncertainty stay distinct; nothing invented.
    mixed = _cov({"a": "covered", "b": "denied", "c": "unable", "d": "thin", "e": "unasked"})
    out3 = build_provisional_sketch(mixed, None)
    assert out3["reported"] == 1 and out3["denied"] == 1 and out3["uncertain"] == 1
    assert out3["thin_or_missing"] == 2
    assert "No screening was taken" in " ".join(out3["lines"])


def test_sketch_mode_defaults_demo_only(monkeypatch):
    monkeypatch.delenv("PROVISIONAL_SKETCH", raising=False)
    assert sketch_mode() == "demo-only"
    monkeypatch.setenv("PROVISIONAL_SKETCH", "bogus")
    assert sketch_mode() == "demo-only"
    monkeypatch.setenv("PROVISIONAL_SKETCH", "on")
    assert sketch_mode() == "on"


@pytest.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    from app.db import get_db

    for name in await get_db().client.list_database_names():
        if name.startswith("mrprof_test_"):
            await get_db().client.drop_database(name)


async def test_confirm_omits_sketch_by_default(client, monkeypatch):
    import uuid

    monkeypatch.setenv("PROVISIONAL_SKETCH", "demo-only")
    password = f"correct horse {uuid.uuid4().hex[:8]}"
    res = await client.post("/assessments", json={"password": password})
    assert res.status_code == 201
    body = res.json()
    base = f"/assessments/{body['assessment_id']}"
    headers = {"Authorization": f"Bearer {password}"}
    res = await client.post(
        f"{base}/interview/start",
        json={"base_version": 1, "idempotency_key": f"sk-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    version = res.json()["version"]
    for _ in range(14):
        res = await client.post(
            f"{base}/interview/answer",
            json={
                "answer_text": "For example, last week at work I lost track twice; it happens every week since January.",
                "base_version": version,
                "idempotency_key": f"sk-{uuid.uuid4().hex[:8]}",
            },
            headers=headers,
        )
        assert res.status_code == 200, res.text
        version = res.json()["version"]
    import asyncio

    for _ in range(30):
        poll = await client.get(f"{base}/interview/assessment", headers=headers)
        if poll.json()["status"] == "review":
            break
        await asyncio.sleep(0.2)
    nxt = await client.get(f"{base}/interview/next", headers=headers)
    res = await client.post(
        f"{base}/interview/review/confirm",
        json={"base_version": nxt.json()["version"], "idempotency_key": f"sk-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    rep = await client.get(f"{base}/interview/report", headers=headers)
    assert rep.json()["provisional_sketch"] is None
