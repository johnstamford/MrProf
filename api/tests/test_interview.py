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

from app.interview import (  # noqa: E402
    FAMILIES,
    MAX_FOLLOWUPS,
    MAX_TURNS,
    PLAN_ORDER,
    SKILL_VERSION,
    TOPIC_VERSION,
    _needs_detail_invite,
    build_prompt,
    family_tensions,
    plan_next,
)
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


async def _poll_assessment(client, base: str, headers: dict, tries: int = 20) -> dict:
    """Poll GET .../interview/assessment until followup or complete.

    The batch job runs as a background task; with the dummy provider it
    finishes in milliseconds, so this returns almost immediately.
    """
    import asyncio

    for _ in range(tries):
        res = await client.get(f"{base}/interview/assessment", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        if body["status"] in ("followup", "complete"):
            return body
        await asyncio.sleep(0.2)
    raise AssertionError(f"assessment stuck at {body['status']}")


def test_unit_planner_round1_fixed_order():
    assert plan_next([])[0] == PLAN_ORDER[0] == "attention-focus"
    assert plan_next([{"objective": PLAN_ORDER[0], "answer": "x" * 40}])[0] == PLAN_ORDER[1]
    assert plan_next([{"objective": t, "answer": "y" * 40} for t in PLAN_ORDER[:5]])[0] == PLAN_ORDER[5]
    # Round 1 asks every objective once; no live probes mid-round.
    full = [{"objective": t, "turn": i + 1, "answer": "y" * 40} for i, t in enumerate(PLAN_ORDER)]
    obj, _, done, hint = plan_next(full, [])
    assert done is True and hint is None and obj == ""


def _turn(no: int, objective: str, answer: str, reason: str = "r") -> dict:
    return {"turn": no, "objective": objective, "reason": reason, "question": "q", "answer": answer}


def test_unit_planner_round2_consumes_queue():
    asked = [{"objective": t, "turn": i + 1, "answer": "y" * 40} for i, t in enumerate(PLAN_ORDER)]
    queue = [
        {"objective": "forgetfulness", "reason": "Follow up forgetfulness", "tension": "t1"},
        {"objective": "organization", "reason": "Follow up organization"},
    ]
    obj, reason, done, hint = plan_next(asked, queue)
    assert (obj, done) == ("forgetfulness", False)
    assert hint == {"kind": "followup", "tension": "t1"}
    assert "tension" in reason or "Follow up" in reason
    # After answering the first follow-up, the second is next.
    asked.append({**_turn(15, "forgetfulness", "more detail here yes indeed"), "probe": "followup"})
    obj, _, done, hint = plan_next(asked, queue)
    assert (obj, done) == ("organization", False)
    assert hint == {"kind": "followup"}
    # Queue exhausted -> complete.
    asked.append({**_turn(16, "organization", "more detail here yes indeed"), "probe": "followup"})
    obj, _, done, hint = plan_next(asked, queue)
    assert done is True and hint is None


def test_unit_tension_detection_shape():
    t1 = _turn(1, "childhood-onset", "School was never a problem for me at all, really.")
    t2 = _turn(2, "persistence-course", "Over the years it has clearly been there a long time.")
    assert family_tensions([t1, t2]) == [
        {"family": "course", "present_turn": 2, "denial_turn": 1}
    ]
    assert family_tensions([t1]) == []


def test_unit_completion_at_cap():
    turns = [
        _turn(i + 1, PLAN_ORDER[i % len(PLAN_ORDER)], "a substantive detailed answer indeed")
        for i in range(MAX_TURNS)
    ]
    _, _, done, _ = plan_next(turns, [])
    assert done is True
    assert MAX_TURNS == len(PLAN_ORDER) + MAX_FOLLOWUPS


def test_unit_coverage_from_evidence_statuses():
    from app.assessment import coverage_from_evidence

    turns = [
        _turn(1, "attention-focus", "a substantive detailed account of staying focused yes"),
        _turn(2, "organization", "No"),
        _turn(3, "task-completion", "I cannot recall any of that, sorry"),
        _turn(4, "forgetfulness", "keys"),
        _turn(5, "restlessness", "I fidget quite a lot in long meetings, honestly"),
    ]
    ev = [
        {"turn": 1, "versions": [{"observations": [{"code": "attention-focus", "assertion": "present"}]}]},
        {"turn": 2, "versions": [{"observations": [{"code": "organization", "assertion": "explicitly-denied"}]}]},
        {"turn": 3, "versions": [{"observations": [{"code": "task-completion", "assertion": "uncertain"}]}]},
        {"turn": 4, "versions": [{"observations": [{"code": "forgetfulness", "assertion": "present"}]}]},
    ]
    summary = {e["objective"]: e["status"] for e in coverage_from_evidence(turns, ev)}
    assert summary["attention-focus"] == "covered"
    assert summary["organization"] == "denied"
    assert summary["task-completion"] == "unable"
    assert summary["forgetfulness"] == "thin"  # present assertion but thin text
    assert summary["restlessness"] == "pending"  # answered, evidence missing
    assert summary["impulsivity"] == "unasked"
    assert list(summary) == list(PLAN_ORDER)


def test_unit_detail_invite_targets_thin_answers_only():
    assert _needs_detail_invite(None) is False
    assert _needs_detail_invite("") is False
    assert _needs_detail_invite("bills") is True
    assert _needs_detail_invite("dunno really") is False  # uncertainty exempt
    assert _needs_detail_invite("No, starting tasks is fine.") is False  # denial exempt
    assert _needs_detail_invite("No") is False  # bare denial still exempt
    assert _needs_detail_invite(
        "This month I missed two deadlines because I kept putting off starting."
    ) is False
    short = build_prompt(objective="impact-life", reason="r", history=[], screening=None, last_answer="bills")
    assert any("very brief" in line for line in short)
    exempt = build_prompt(objective="impact-life", reason="r", history=[], screening=None, last_answer="No")
    assert not any("very brief" in line for line in exempt)
    normal = build_prompt(
        objective="impact-life", reason="r", history=[], screening=None,
        last_answer="This month I missed two deadlines because I kept putting off starting.",
    )
    assert not any("very brief" in line for line in normal)


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


def test_unit_transient_retry(monkeypatch):
    import app.llm as llm

    calls = {"n": 0}

    async def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise llm.LLMError("timeout", "timed out", status=502)
        return ('{"question_text": "What tasks are hardest?", "reason": "why now"}', {}, {"session_id": "s"})

    monkeypatch.setattr(llm, "run_agent_text", flaky)
    import asyncio

    q, _, _ = asyncio.run(
        llm.generate_next_question(
            cfg=llm.LLMConfig(provider="openai-compatible", model="m", base_url="http://x", api_key="k"),
            instructions="i",
            prompt="p",
            objective="attention-tasks",
            reason="r",
            fallback_question="fb",
            session_id="s",
        )
    )
    assert q.question_text == "What tasks are hardest?" and calls["n"] == 2

    async def always_down(*a, **k):
        raise llm.LLMError("provider_error", "down", status=502)

    monkeypatch.setattr(llm, "run_agent_text", always_down)
    try:
        asyncio.run(
            llm.generate_next_question(
                cfg=llm.LLMConfig(provider="openai-compatible", model="m", base_url="http://x", api_key="k"),
                instructions="i",
                prompt="p",
                objective="attention-tasks",
                reason="r",
                fallback_question="fb",
                session_id="s",
            )
        )
    except llm.LLMError as exc:
        assert exc.code == "provider_error"
    else:
        raise AssertionError("expected LLMError after retried transient failure")


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
    assert "focused" in body["question"]["text"].lower()
    assert body["question"]["model_provider"] == "dummy"

    nxt = await client.get(f"{base}/interview/next", headers=headers)
    assert nxt.status_code == 200
    assert nxt.json()["question"]["text"] == body["question"]["text"]
    # Read-only resume: version unchanged.
    assert nxt.json()["version"] == 2

    version, last = 2, None
    for i in range(len(PLAN_ORDER)):
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
    # Round 1 done: batch assessment runs, no question pending yet.
    assert last["completed"] is False and last["question"] is None
    assert last["status"] == "assessing" and last["turn_answered"] == len(PLAN_ORDER)

    final = await _poll_assessment(client, base, headers)
    assert final["status"] == "complete"
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


async def test_round2_followup_flow(client):
    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    await _start(client, created, version=1)

    version = 2
    thin = {"forgetfulness", "organization"}
    for i, oid in enumerate(PLAN_ORDER):
        ans = "x" if oid in thin else f"substantive detail for turn {i} yes indeed"
        res = await client.post(
            f"{base}/interview/answer",
            json={"answer_text": ans, "base_version": version, "idempotency_key": f"fk5-r2-{uuid.uuid4().hex[:8]}"},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        version = res.json()["version"]
    assert res.json()["status"] == "assessing"

    first = await _poll_assessment(client, base, headers)
    assert first["status"] == "followup"
    assert first["followups_total"] == 2 and first["question"] is not None
    nxt = (await client.get(f"{base}/interview/next", headers=headers)).json()
    assert nxt["question"]["text"] == first["question"]["text"]

    for _ in range(2):
        res = await client.post(
            f"{base}/interview/answer",
            json={"answer_text": "now with plenty of concrete detail yes", "base_version": version, "idempotency_key": f"fk5-r2b-{uuid.uuid4().hex[:8]}"},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        version = res.json()["version"]
        if res.json()["status"] == "assessing":
            break
    final = await _poll_assessment(client, base, headers)
    assert final["status"] == "complete"
    rep = await client.get(f"{base}/interview/report", headers=headers)
    assert rep.status_code == 200
    assert rep.json()["turns_answered"] == len(PLAN_ORDER) + 2


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
