"""Feature 6 focused checks: interview briefing report.

Run inside the api container: docker compose exec api pytest tests -q
"""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MONGODB_DB", "mrprof")

from app.briefing import build_interview_briefing  # noqa: E402
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


def _interview_state() -> dict:
    from app.interview import PLAN_ORDER, SKILL_VERSION, TOPIC_VERSION

    return {
        "skill_version": SKILL_VERSION,
        "topic_version": TOPIC_VERSION,
        "turns": [
            {
                "turn": 1,
                "objective": PLAN_ORDER[0],
                "reason": "draft plan turn 1",
                "question": "What kinds of tasks are hardest?",
                "answer": "starting paperwork",
                "model_provider": "dummy",
                "model_name": "dummy-stub",
            }
        ],
    }


def _coverage_for(objectives_statuses: dict) -> list[dict]:
    from app.interview import PLAN_ORDER, load_topics

    topics = load_topics()
    return [
        {
            "objective": oid,
            "title": topics[oid].get("title", oid),
            "status": objectives_statuses.get(oid, "unasked"),
            "turns": [1] if oid in objectives_statuses else [],
            "note": "test",
        }
        for oid in PLAN_ORDER
    ]


def test_unit_briefing_separates_patient_from_system():
    from datetime import datetime, timezone

    from app.interview import PLAN_ORDER

    coverage = _coverage_for({PLAN_ORDER[0]: "thin"})
    content = build_interview_briefing(
        "AID12345", _interview_state(), coverage, [], [], [], 1, datetime.now(timezone.utc)
    )
    assert content["turns_answered"] == 1
    # Patient section carries verbatim Q/A only — no objectives/reasons.
    assert set(content["statements"][0]) == {"turn", "question", "answer"}
    assert content["statements"][0]["answer"] == "starting paperwork"
    # System section carries planning metadata — no answers.
    assert set(content["system_notes"][0]) == {"turn", "objective", "reason", "model_provider", "model_name"}
    assert "answer" not in content["system_notes"][0]
    # One thin topic + thirteen unasked: all fourteen are gaps.
    from app.interview import PLAN_ORDER, load_topics

    topics = load_topics()
    assert [g["area"] for g in content["gaps"]] == [topics[oid]["title"] for oid in PLAN_ORDER]
    assert content["coverage"][0]["status"] == "thin"
    assert content["coverage"][0]["turns"] == [1]
    assert all(c["status"] == "unasked" for c in content["coverage"][1:])
    assert content["contradictions"] == []
    # Per-topic section carries this topic's Q/A; no evidence passed, so none cited.
    assert [t["objective"] for t in content["topics"]] == list(PLAN_ORDER)
    assert content["topics"][0]["turns"][0]["question"] == "What kinds of tasks are hardest?"
    assert content["topics"][0]["turns"][0]["observations"] == []
    assert content["transcript"] == []
    assert content["skill_version"] == "skill-v0.4-draft"
    assert content["topic_version"] == "topics-v0.4-draft"
    # No diagnostic, probability, or severity language.
    blob = " ".join([content["banner"], content["completion_note"]]).lower()
    for banned in ("you have adhd", "probability", "severity", "mild", "moderate", "severe", "%"):
        assert banned not in blob, banned


async def _run_full_journey(client, created) -> None:
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    res = await client.post(
        f"{base}/interview/start",
        json={"base_version": 1, "idempotency_key": f"fk6-start-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200
    version = res.json()["version"]
    from app.interview import PLAN_ORDER

    for _ in range(len(PLAN_ORDER)):
        res = await client.post(
            f"{base}/interview/answer",
            json={
                "answer_text": "a few words of detail here",
                "base_version": version,
                "idempotency_key": f"fk6-ans-{uuid.uuid4().hex[:8]}",
            },
            headers=headers,
        )
        assert res.status_code == 200
        version = res.json()["version"]
    # Round 1 done: batch assessment runs, no question pending yet.
    assert res.json()["completed"] is False and res.json()["question"] is None
    assert res.json()["status"] == "assessing"

    import asyncio

    for _ in range(30):
        poll = await client.get(f"{base}/interview/assessment", headers=headers)
        assert poll.status_code == 200
        if poll.json()["status"] == "complete":
            return
        await asyncio.sleep(0.2)
    raise AssertionError("batch assessment did not complete")


async def test_briefing_lifecycle(client):
    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"

    # No briefing before the interview exists or completes.
    assert (await client.get(f"{base}/interview/report", headers=headers)).status_code == 404

    await _run_full_journey(client, created)

    first = await client.get(f"{base}/interview/report", headers=headers)
    assert first.status_code == 200
    body = first.json()
    from app.interview import PLAN_ORDER

    assert body["report_version"] == 1 and body["turns_answered"] == len(PLAN_ORDER)
    assert len(body["statements"]) == len(PLAN_ORDER) and len(body["system_notes"]) == len(PLAN_ORDER)
    assert body["gaps"] == []  # full run asks every planned objective
    assert [c["objective"] for c in body["coverage"]] == list(PLAN_ORDER)
    assert all(c["status"] == "covered" for c in body["coverage"])
    assert body["contradictions"] == []
    assert [t["objective"] for t in body["topics"]] == list(PLAN_ORDER)
    assert all(len(t["turns"]) == 1 for t in body["topics"])
    assert body["topics"][0]["turns"][0]["observations"], "expected cited observations"
    assert body["transcript"] and all("line" in s for s in body["transcript"])
    assert [s["line"] for s in body["transcript"]] == sorted(s["line"] for s in body["transcript"])
    assert body["skill_version"] == "skill-v0.4-draft"
    assert [a["key"] for a in body["areas"]] == ["functioning", "course", "impact", "context"]
    assert all(a["status"] == "covered" and a["label"] == "Reported" for a in body["areas"])
    assert sum(a["counts"].get("covered", 0) for a in body["areas"]) == len(PLAN_ORDER)
    assert body["screening"] is None  # no screening submitted on this journey
    # Reopen returns the same versioned briefing.
    second = await client.get(f"{base}/interview/report", headers=headers)
    assert second.json() == body

    # Exactly one briefing stored; replayed answers never duplicate it.
    from app.db import get_db

    assert await get_db()["reports"].count_documents({"assessment_id": created["assessment_id"], "kind": "interview"}) == 1


async def test_briefing_auth_isolation(client):
    created = await _create(client)
    other = await _create(client)
    await _run_full_journey(client, created)
    url = f"/assessments/{created['assessment_id']}/interview/report"
    assert (await client.get(url)).status_code == 401
    assert (await client.get(url, headers=_auth(other["password"]))).status_code == 401
    assert (await client.get("/assessments/a_doesnotexist/interview/report", headers=_auth("x"))).status_code == 404


def test_family_rollup_and_screening_snapshot():
    from datetime import datetime, timezone

    from app.briefing import TOPIC_STATUS_LABELS, build_interview_briefing, family_rollup
    from app.interview import FAMILIES, PLAN_ORDER

    assert set(TOPIC_STATUS_LABELS) >= {"covered", "denied", "unable", "thin", "unasked", "pending"}
    # Denial is never relabeled as a gap.
    assert TOPIC_STATUS_LABELS["denied"] != TOPIC_STATUS_LABELS["unasked"]

    coverage = [
        {"objective": oid, "title": oid, "status": "denied", "turns": [1], "note": "t"}
        for oid in PLAN_ORDER
    ]
    # functioning: 5 denied + 1 reported -> headline Reported with honest counts.
    coverage[0] = {**coverage[0], "status": "covered"}
    # course: uncertainty wins over gaps.
    coverage[6] = {**coverage[6], "status": "unable"}
    areas = family_rollup(coverage)
    assert [a["key"] for a in areas] == ["functioning", "course", "impact", "context"]
    assert [a["objectives"] for a in areas] == [list(FAMILIES[k]) for k in ("functioning", "course", "impact", "context")]
    by_key = {a["key"]: a for a in areas}
    assert by_key["functioning"]["status"] == "covered"
    assert by_key["functioning"]["counts"] == {"denied": 5, "covered": 1}
    assert by_key["functioning"]["label"] == "Reported"
    assert by_key["course"]["status"] == "unable"
    assert by_key["course"]["label"] == "Uncertain"
    assert by_key["impact"]["status"] == "denied"

    screening = {"score": 4, "scoring_method": "original-0-6", "positive": True,
                 "completed_at": datetime.now(timezone.utc)}
    content = build_interview_briefing(
        "AID12345", {"turns": [], "skill_version": "s", "topic_version": "t"},
        coverage, [], [], [], 1, datetime.now(timezone.utc), screening,
    )
    assert content["screening"]["score"] == 4
    assert content["screening"]["scoring_method"] == "original-0-6"
    assert content["screening"]["positive"] is True
    assert len(content["areas"]) == 4
    assert content["topics"][0]["label"] == "Reported"

    noscreen = build_interview_briefing(
        "AID12345", {"turns": [], "skill_version": "s", "topic_version": "t"},
        coverage, [], [], [], 1, datetime.now(timezone.utc),
    )
    assert noscreen["screening"] is None
