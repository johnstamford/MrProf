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


def test_unit_briefing_separates_patient_from_system():
    from datetime import datetime, timezone

    content = build_interview_briefing("AID12345", _interview_state(), 1, datetime.now(timezone.utc))
    assert content["turns_answered"] == 1
    # Patient section carries verbatim Q/A only — no objectives/reasons.
    assert set(content["statements"][0]) == {"turn", "question", "answer"}
    assert content["statements"][0]["answer"] == "starting paperwork"
    # System section carries planning metadata — no answers.
    assert set(content["system_notes"][0]) == {"turn", "objective", "reason", "model_provider", "model_name"}
    assert "answer" not in content["system_notes"][0]
    # One planned topic touched with a thin answer: the rest are unasked gaps.
    from app.interview import PLAN_ORDER, load_topics

    topics = load_topics()
    assert [g["area"] for g in content["gaps"]] == [topics[oid]["title"] for oid in PLAN_ORDER]
    assert content["coverage"][0]["status"] == "thin"
    assert content["coverage"][0]["turns"] == [1]
    assert all(c["status"] == "unasked" for c in content["coverage"][1:])
    assert content["contradictions"] == []
    assert content["skill_version"] == "skill-v0.3-draft"
    assert content["topic_version"] == "topics-v0.3-draft"
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
    from app.interview import MAX_TURNS

    for _ in range(MAX_TURNS):
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
        if res.json()["completed"]:
            break
    assert res.json()["completed"] is True


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
    assert body["skill_version"] == "skill-v0.3-draft"
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
