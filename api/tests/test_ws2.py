"""WS2-B dimension-driven follow-ups: matrix units + queue order + journey."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.assessment import build_followups
from app.briefing import coverage_detail_line
from app.extraction import TAXONOMY_VERSION
from app.interview import PLAN_ORDER, missing_dimensions, objective_dimensions
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


def _ev(turn: int, code: str, assertion: str, **fields) -> dict:
    obs = {
        "code": code,
        "assertion": assertion,
        "segment_id": f"T{turn}-A1",
        "quote": "a supporting span",
        "obs_index": 0,
        **fields,
    }
    return {
        "_id": f"t:turn:{turn}",
        "assessment_id": "t",
        "turn": turn,
        "versions": [
            {
                "version": 1,
                "taxonomy_version": TAXONOMY_VERSION,
                "extractor": {},
                "observations": [obs],
                "coverage": {},
            }
        ],
    }


def test_objective_dimensions_come_from_topics():
    assert objective_dimensions("attention-focus") == ("example", "frequency", "period", "setting")
    assert objective_dimensions("childhood-onset") == ("example", "period")
    assert objective_dimensions("persistence-course") == ("example", "period")
    assert objective_dimensions("strategies") == ("example",)


def test_missing_dimensions_matrix():
    oid = "attention-focus"
    assert missing_dimensions(oid, []) == []
    denied = [{"assertion": "explicitly-denied", "quote": "q", "segment_id": "s"}]
    assert missing_dimensions(oid, denied) == []
    uncertain = [{"assertion": "uncertain", "quote": "q", "segment_id": "s"}]
    assert missing_dimensions(oid, uncertain) == []
    present = [{"assertion": "present", "quote": "q", "segment_id": "s"}]
    assert missing_dimensions(oid, present) == ["example", "frequency", "period", "setting"]
    assert missing_dimensions(oid, present, {"detail": 0, "has_example": False}) == [
        "example", "frequency", "period", "setting",
    ]
    # Each filled field drops out; priority order holds.
    assert missing_dimensions(oid, [{**present[0], "period": "last week"}]) == [
        "example", "frequency", "setting",
    ]
    assert missing_dimensions(oid, [{**present[0], "period": "x", "setting": "y", "frequency": "z"}]) == ["example"]
    # Example via has_example or detail 3.
    assert missing_dimensions(oid, present, {"detail": 1, "has_example": True}) == [
        "frequency", "period", "setting",
    ]
    assert missing_dimensions(oid, present, {"detail": 3, "has_example": False}) == [
        "frequency", "period", "setting",
    ]
    # Course objectives only track period + example.
    assert missing_dimensions("childhood-onset", [{**present[0], "period": "age 7"}]) == ["example"]
    # Context objectives only track example.
    assert missing_dimensions("strategies", present) == ["example"]
    assert missing_dimensions("strategies", present, {"detail": 3}) == []


def test_dimension_followups_come_before_thin():
    p1, p2 = PLAN_ORDER[0], PLAN_ORDER[1]
    turns = [
        {"turn": 1, "objective": p1, "answer": "a vague but present account of losing the thread"},
        {"turn": 2, "objective": p2, "answer": "brief"},
    ]
    queue = build_followups(turns, [_ev(1, p1, "present"), _ev(2, p2, "present")], [])
    assert queue[0]["objective"] == p1
    assert queue[0]["dimension"] == "example"
    assert "recent occasion" in queue[0]["reason"]
    assert queue[1]["objective"] == p2 and "dimension" not in queue[1]


def test_denial_and_uncertainty_are_never_probed():
    f1, f2 = PLAN_ORDER[0], PLAN_ORDER[1]
    turns = [
        {"turn": 1, "objective": f1, "answer": "No, concentrating is fine for me."},
        {"turn": 2, "objective": f2, "answer": "I can't remember."},
    ]
    queue = build_followups(
        turns,
        [_ev(1, f1, "explicitly-denied"), _ev(2, f2, "uncertain")],
        [],
    )
    assert queue == []


def test_coverage_detail_line():
    oid = "attention-focus"
    present = [{"assertion": "present", "quote": "q", "segment_id": "s"}]
    assert coverage_detail_line(oid, present) == (
        "Coverage detail: example \u2014 \u00b7 frequency \u2014 \u00b7 timeframe \u2014 \u00b7 setting \u2014"
    )
    full = [{**present[0], "period": "x", "setting": "y", "frequency": "z"}]
    assert coverage_detail_line(oid, full, {"detail": 3}) == (
        "Coverage detail: example \u2713 \u00b7 frequency \u2713 \u00b7 timeframe \u2713 \u00b7 setting \u2713"
    )
    assert coverage_detail_line(oid, [{"assertion": "explicitly-denied"}]) == ""
    assert coverage_detail_line(oid, []) == ""


async def test_vague_present_answer_gets_dimension_followup(client):
    import asyncio

    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    res = await client.post(
        f"{base}/interview/start",
        json={"base_version": 1, "idempotency_key": f"ws2-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    version = res.json()["version"]
    RICH = (
        "For example, last week at work I lost track of my tasks twice; "
        "it happens every week since January."
    )
    last = None
    for i, oid in enumerate(PLAN_ORDER):
        ans = "Honestly it is mostly bills and paperwork piling up." if i == 0 else RICH
        res = await client.post(
            f"{base}/interview/answer",
            json={
                "answer_text": ans,
                "base_version": version,
                "idempotency_key": f"ws2-{uuid.uuid4().hex[:8]}",
            },
            headers=headers,
        )
        assert res.status_code == 200, res.text
        last = res.json()
        version = last["version"]
    assert last["status"] == "assessing"
    final = None
    for _ in range(30):
        poll = await client.get(f"{base}/interview/assessment", headers=headers)
        assert poll.status_code == 200
        final = poll.json()
        if final["status"] != "assessing":
            break
        await asyncio.sleep(0.2)
    # The vague (not thin) first answer earns a targeted follow-up; the old
    # code queued nothing for a covered topic.
    assert final["status"] == "followup", final
    assert final["followups_total"] >= 1
    assert final["question"] is not None
    assert final["question"]["objective"] == PLAN_ORDER[0]
