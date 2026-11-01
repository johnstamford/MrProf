"""F10a slices 2-4: taster mode, risk signpost, latency stats."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.assessment import build_followups
from app.briefing import build_interview_briefing, latency_summary
from app.interview import (
    PLAN_ORDER,
    TASTER_OBJECTIVES,
    coverage_summary,
    plan_next,
    round1_objectives,
)
from app.main import app
from app.risk import RISK_SIGNPOST


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


def test_taster_objectives_are_a_prefix_flag():
    assert TASTER_OBJECTIVES == PLAN_ORDER[:6]
    assert round1_objectives("taster") == PLAN_ORDER[:6]
    assert round1_objectives("full") == PLAN_ORDER
    # Six taster turns complete round 1 (no follow-ups queued here).
    turns = [
        {"objective": t, "turn": i + 1, "answer": "a substantive detailed answer indeed"}
        for i, t in enumerate(TASTER_OBJECTIVES)
    ]
    obj, _, done, _ = plan_next(turns, [], mode="taster")
    assert done is True
    # Same six turns in full mode still have eight objectives to go.
    obj, _, done, _ = plan_next(turns, [], mode="full")
    assert (done, obj) == (False, PLAN_ORDER[6])


def test_taster_coverage_marks_rest_as_gaps():
    turns = [
        {"objective": t, "turn": i + 1, "answer": "a substantive detailed answer indeed"}
        for i, t in enumerate(TASTER_OBJECTIVES)
    ]
    statuses = {e["objective"]: e["status"] for e in coverage_summary(turns)}
    assert all(statuses[t] == "covered" for t in TASTER_OBJECTIVES)
    assert all(statuses[t] == "unasked" for t in PLAN_ORDER[6:])


def test_taster_followup_cap():
    tensions = [
        {"family": "functioning", "present_turn": 1, "denial_turn": 2},
        {"family": "course", "present_turn": 7, "denial_turn": 8},
        {"family": "impact", "present_turn": 9, "denial_turn": 10},
    ]
    assert len(build_followups([], [], tensions, mode="taster")) <= 2
    assert len(build_followups([], [], tensions, mode="full")) <= 6


def test_risk_signpost_is_static_and_non_monitored():
    lowered = RISK_SIGNPOST.lower()
    assert "no one monitors" in lowered or "no one reviews" in lowered
    assert "real time" in lowered
    assert not any(w in lowered for w in ("we will contact you", "we monitor", "tracked live"))
    assert any(n in RISK_SIGNPOST for n in ("112", "911", "999"))


def test_latency_summary_percentiles():
    turns = [{"turn": i + 1, "phrase_ms": float(i * 10)} for i in range(10)]
    s = latency_summary(turns)
    assert s["count"] == 10 and s["max_ms"] == 90
    assert s["p50_ms"] == 45.0
    assert 0 < s["p95_ms"] <= 90
    assert latency_summary([]) == {"count": 0, "p50_ms": 0, "p95_ms": 0, "max_ms": 0}


async def _poll(client, base, headers, tries: int = 20) -> dict:
    import asyncio

    for _ in range(tries):
        res = await client.get(f"{base}/interview/assessment", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        if body["status"] in ("followup", "complete"):
            return body
        await asyncio.sleep(0.2)
    raise AssertionError("assessment stuck")


async def test_taster_journey_completes_with_gaps_and_latency(client):
    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"

    res = await client.post(
        f"{base}/interview/start",
        json={"base_version": 1, "idempotency_key": f"t-tas-{uuid.uuid4().hex[:8]}", "mode": "taster"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["mode"] == "taster"

    version = res.json()["version"]
    for i in range(len(TASTER_OBJECTIVES)):
        res = await client.post(
            f"{base}/interview/answer",
            json={
                "answer_text": f"taster detail answer {i} with concrete example",
                "base_version": version,
                "idempotency_key": f"t-tas-{uuid.uuid4().hex[:8]}",
            },
            headers=headers,
        )
        assert res.status_code == 200, res.text
        version = res.json()["version"]
        assert res.json()["mode"] == "taster"
    last = res.json()
    assert last["status"] == "assessing" and last["question"] is None

    final = await _poll(client, base, headers)
    assert final["status"] in ("followup", "complete")
    nxt = await client.get(f"{base}/interview/next", headers=headers)
    assert nxt.json()["mode"] == "taster"

    # Drive to completion through any follow-ups.
    for _ in range(6):
        state = (await client.get(f"{base}/interview/next", headers=headers)).json()
        if state["completed"]:
            break
        if state["question"] is None:
            final = await _poll(client, base, headers)
            if final["status"] == "complete":
                break
            state = (await client.get(f"{base}/interview/next", headers=headers)).json()
            if state["completed"] or state["question"] is None:
                break
        res = await client.post(
            f"{base}/interview/answer",
            json={
                "answer_text": "follow-up detail with a concrete example at work",
                "base_version": state["version"],
                "idempotency_key": f"t-tas-{uuid.uuid4().hex[:8]}",
            },
            headers=headers,
        )
        assert res.status_code == 200, res.text
    rep = await client.get(f"{base}/interview/report", headers=headers)
    assert rep.status_code == 200, rep.text
    body = rep.json()
    assert body["mode"] == "taster"
    assert body["latency_summary"]["count"] >= len(TASTER_OBJECTIVES)
    assert body["latency_summary"]["p95_ms"] >= body["latency_summary"]["p50_ms"] >= 0
    assert "no one monitors" in body["support_note"].lower()
    gap_titles = {g["area"] for g in body["gaps"]}
    assert len(body["gaps"]) >= 8  # the eight unasked objectives stay visible
    assert len(gap_titles) >= 8


async def test_start_rejects_unknown_mode(client):
    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    res = await client.post(
        f"{base}/interview/start",
        json={"base_version": 1, "idempotency_key": f"t-bad-{uuid.uuid4().hex[:8]}", "mode": "marathon"},
        headers=headers,
    )
    assert res.status_code == 422
