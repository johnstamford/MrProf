"""Feature 5 focused checks: draft-topics interview flow, real API path.

Run inside the api container: docker compose exec api pytest tests -q
Default env has no LLM credentials, so the deterministic dummy provider
exercises the full FastAPI persist/resume/idempotency path with no network.
"""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MONGODB_DB", "mrprof")

from app.interview import MAX_TURNS, PLAN_ORDER, SKILL_VERSION, TOPIC_VERSION, plan_next  # noqa: E402
from app.llm import is_dummy, load_config, parse_llm_json  # noqa: E402
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


def test_unit_planner_sequence():
    assert plan_next([])[0] == PLAN_ORDER[0] == "attention-tasks"
    assert plan_next([{"objective": PLAN_ORDER[0], "answer": "x"}])[0] == PLAN_ORDER[1]
    assert plan_next([{"objective": t, "answer": "x"} for t in PLAN_ORDER[:5]])[0] == PLAN_ORDER[5]
    assert plan_next(
        [{"objective": t, "answer": "x"} for t in PLAN_ORDER[:4]]
    )[0] == PLAN_ORDER[4]
    _, _, done_full = plan_next([{"objective": t, "answer": "x"} for t in PLAN_ORDER])
    assert done_full is True


def test_unit_dummy_config_and_strict_parse():
    cfg = load_config()
    # No credentials in test env -> dummy path, no network.
    assert is_dummy(cfg) is True
    q = parse_llm_json('{"question_text": "What tasks are hardest?", "reason": "why now"}', "attention-tasks")
    assert (q.question_text, q.objective) == ("What tasks are hardest?", "attention-tasks")
    for bad in ('not json', "[1,2]", '{"question_text": "x"}', '{"question_text": "Q?", "reason": "why"}'):
        try:
            parse_llm_json(bad, "attention-tasks")
        except Exception:
            pass
        else:
            raise AssertionError(f"expected LLMError for {bad}")


def test_unit_provider_misconfiguration_is_actionable():
    from app.llm import LLMConfig, LLMError, require_effective_provider

    assert require_effective_provider(LLMConfig(provider="dummy")) == "dummy"
    for bad in (
        LLMConfig(provider="bogus-model"),
        LLMConfig(provider="openai-compatible"),  # known but no creds
        LLMConfig(provider="openai-compatible", model="m", base_url="http://x"),  # no key
    ):
        try:
            require_effective_provider(bad)
        except LLMError as exc:
            assert exc.status in (500, 502) and exc.code in ("provider_unsupported", "provider_misconfigured")
        else:
            raise AssertionError(f"expected LLMError for {bad.provider}")


async def _start(client, created, version=1, key=None) -> dict:
    key = key or f"fk5-start-{uuid.uuid4().hex[:8]}"
    res = await client.post(
        f"/assessments/{created['assessment_id']}/interview/start",
        json={"base_version": version, "idempotency_key": key},
        headers=_auth(created["password"]),
    )
    return {"response": res, "key": key}


async def test_start_answer_resume_complete(client):
    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"

    started = await _start(client, created, version=1)
    assert started["response"].status_code == 200, started["response"].text
    body = started["response"].json()
    assert body["version"] == 2 and body["stage"] == "interview"
    assert body["question"]["turn"] == 1 and body["question"]["objective"] == PLAN_ORDER[0]
    assert "tasks" in body["question"]["text"].lower()
    assert body["question"]["model_provider"] == "dummy"

    nxt = await client.get(f"{base}/interview/next", headers=headers)
    assert nxt.status_code == 200
    assert nxt.json()["question"]["text"] == body["question"]["text"]
    # Read-only resume: version unchanged.
    assert nxt.json()["version"] == 2

    version, last = 2, None
    for i in range(MAX_TURNS):
        key = f"fk5-ans-{uuid.uuid4().hex[:8]}"
        res = await client.post(
            f"{base}/interview/answer",
            json={"answer_text": f"answer number {i} with some detail", "base_version": version, "idempotency_key": key},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        last = res.json()
        version = last["version"]
        if i == 0:
            # Topic finishes before moving on: second topic comes second.
            assert last["question"]["objective"] == PLAN_ORDER[1]
    assert last["completed"] is True and last["status"] == "complete"
    assert last["question"] is None and last["turn_answered"] == MAX_TURNS

    nxt2 = await client.get(f"{base}/interview/next", headers=headers)
    assert nxt2.json()["completed"] is True and nxt2.json()["question"] is None

    # Answering after completion is rejected, state untouched.
    res = await client.post(
        f"{base}/interview/answer",
        json={"answer_text": "late", "base_version": version, "idempotency_key": f"fk5-late-{uuid.uuid4().hex[:4]}"},
        headers=headers,
    )
    assert res.status_code == 409
    assert "secret" not in res.text and "hash" not in res.text.lower()


async def test_answer_idempotent_and_conflict(client):
    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    await _start(client, created, version=1)

    key = f"fk5-idem-{uuid.uuid4().hex[:8]}"
    first = await client.post(
        f"{base}/interview/answer",
        json={"answer_text": "I like ramen", "base_version": 2, "idempotency_key": key},
        headers=headers,
    )
    assert first.status_code == 200
    replay = await client.post(
        f"{base}/interview/answer",
        json={"answer_text": "I like ramen", "base_version": 2, "idempotency_key": key},
        headers=headers,
    )
    assert replay.status_code == 200
    assert replay.json() == {**first.json(), "replayed": True}

    from app.db import get_db

    doc = await get_db()["assessments"].find_one({"_id": created["assessment_id"]})
    assert doc["version"] == 3 and len(doc["interview"]["turns"]) == 1

    stale = await client.post(
        f"{base}/interview/answer",
        json={"answer_text": "other", "base_version": 2, "idempotency_key": f"fk5-stale-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert stale.status_code == 409
    doc2 = await get_db()["assessments"].find_one({"_id": created["assessment_id"]})
    assert len(doc2["interview"]["turns"]) == 1


async def test_validation_and_auth(client):
    created = await _create(client)
    other = await _create(client)
    base = f"/assessments/{created['assessment_id']}"
    headers = _auth(created["password"])

    assert (await client.get(f"{base}/interview/next")).status_code == 401
    assert (await client.get(f"{base}/interview/next", headers=_auth(other["password"]))).status_code == 401
    assert (await client.get("/assessments/a_doesnotexist/interview/next", headers=headers)).status_code == 404

    await _start(client, created, version=1)
    bad = await client.post(
        f"{base}/interview/answer",
        json={"answer_text": "   ", "base_version": 2, "idempotency_key": f"fk5-bad-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert bad.status_code == 422
    missing = await client.get(f"/assessments/{other['assessment_id']}/interview/next", headers=_auth(other["password"]))
    assert missing.status_code == 404
