"""WS5 friction fixes: skip polarity, correction endpoint, coverage integration."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.interview import PLAN_ORDER, coverage_summary, polarity
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


async def _start(client, base, headers, version=1) -> dict:
    res = await client.post(
        f"{base}/interview/start",
        json={"base_version": version, "idempotency_key": f"ws5-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


async def _answer(client, base, headers, text, version) -> dict:
    res = await client.post(
        f"{base}/interview/answer",
        json={
            "answer_text": text,
            "base_version": version,
            "idempotency_key": f"ws5-{uuid.uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_skip_answers_classify_uncertain():
    for text in (
        "I'd rather skip this one.",
        "I would rather skip this one",
        "Skip this one.",
        "skip",
        "Pass",
        "I would rather not answer.",
    ):
        assert polarity(text) == "uncertain-like", text
    # A substantive answer that merely mentions skipping is unaffected.
    assert (
        polarity("I skip steps when I am rushed and then have to redo them at work")
        == "present-like"
    )
    assert polarity("I can't remember.") == "uncertain-like"


def test_correction_drives_coverage():
    turns = [{"objective": "attention-focus", "turn": 1, "answer": "bills pile up"}]
    statuses = {e["objective"]: e["status"] for e in coverage_summary(turns)}
    assert statuses["attention-focus"] == "thin"
    turns[0]["correction"] = {"text": "No, starting tasks is honestly fine for me."}
    statuses = {e["objective"]: e["status"] for e in coverage_summary(turns)}
    assert statuses["attention-focus"] == "denied"
    # A skip-out correction closes the topic as unable, never probed.
    turns[0]["correction"] = {"text": "I'd rather skip this one."}
    statuses = {e["objective"]: e["status"] for e in coverage_summary(turns)}
    assert statuses["attention-focus"] == "unable"


async def test_skip_and_cant_remember_close_topics_without_probes(client):
    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    started = await _start(client, base, headers)
    version = started["version"]

    first = await _answer(client, base, headers, "I'd rather skip this one.", version)
    assert first["question"] is not None
    assert first["question"]["objective"] == PLAN_ORDER[1], "skip must not trigger an inline probe"
    version = first["version"]

    second = await _answer(client, base, headers, "I can't remember.", version)
    assert second["question"] is not None
    assert second["question"]["objective"] == PLAN_ORDER[2]


async def test_correct_last_answer_lifecycle(client):
    import asyncio

    from app.assessment import extract_corrected_turn
    from app.db import get_db

    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    aid = created["assessment_id"]
    started = await _start(client, base, headers)
    version = started["version"]

    original = "Honestly it is mostly bills and paperwork piling up on the counter."
    answered = await _answer(client, base, headers, original, version)
    version = answered["version"]
    assert answered["turn_answered"] == 1

    # Only the most recent answer can be corrected.
    res = await client.post(
        f"{base}/interview/correct",
        json={
            "corrects_turn": 99,
            "answer_text": "other text",
            "base_version": version,
            "idempotency_key": f"ws5-{uuid.uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert res.status_code == 422

    correction = "What I meant: the bills are fine, it is email I never get round to."
    key = f"ws5-{uuid.uuid4().hex[:8]}"
    res = await client.post(
        f"{base}/interview/correct",
        json={
            "corrects_turn": 1,
            "answer_text": correction,
            "base_version": version,
            "idempotency_key": key,
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["corrects_turn"] == 1 and body["replayed"] is False
    version = body["version"]

    # Idempotent replay: same key returns the stored version, no duplicate.
    res = await client.post(
        f"{base}/interview/correct",
        json={
            "corrects_turn": 1,
            "answer_text": correction,
            "base_version": version - 1,
            "idempotency_key": key,
        },
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json() == {"assessment_id": aid, "version": version, "corrects_turn": 1, "replayed": True}

    # A second, distinct correction of the same turn is rejected.
    res = await client.post(
        f"{base}/interview/correct",
        json={
            "corrects_turn": 1,
            "answer_text": "another try",
            "base_version": version,
            "idempotency_key": f"ws5-{uuid.uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert res.status_code == 409

    # Stale versions conflict.
    res = await client.post(
        f"{base}/interview/correct",
        json={
            "corrects_turn": 1,
            "answer_text": correction,
            "base_version": version - 1,
            "idempotency_key": f"ws5-{uuid.uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert res.status_code == 409

    # Original answer preserved verbatim; correction stored as new C-segments.
    t = await client.get(f"{base}/interview/transcript", headers=headers)
    assert t.status_code == 200
    segs = t.json()["segments"]
    a_segs = [s for s in segs if s["turn"] == 1 and s["role"] == "A"]
    c_segs = [s for s in segs if s["turn"] == 1 and s["role"] == "C"]
    assert a_segs and " ".join(s["text"] for s in a_segs) == original
    assert " ".join(s["text"] for s in c_segs) == correction

    # Re-extraction versions the evidence; the original version is untouched.
    for _ in range(25):
        ev = await client.get(f"{base}/interview/evidence", headers=headers)
        if ev.json()["turns"]:
            break
        await asyncio.sleep(0.2)
    assert ev.json()["turns"], "background extraction never stored turn 1"
    db = get_db()
    before = await db["evidence"].find_one({"_id": f"{aid}:turn:1"})
    n_before = len(before["versions"])
    out = await extract_corrected_turn(db, aid, 1)
    assert out is not None
    after = await db["evidence"].find_one({"_id": f"{aid}:turn:1"})
    assert len(after["versions"]) == n_before + 1
    assert after["versions"][0] == before["versions"][0]
    assert after["versions"][-1]["correction_of"] == n_before

    # Finish the journey; the briefing quotes the correction against its topic.
    for oid in PLAN_ORDER[1:]:
        nxt = await client.get(f"{base}/interview/next", headers=headers)
        state = nxt.json()
        assert state["question"] is not None, state
        done = await _answer(
            client, base, headers,
            f"For example, last week at work {oid} slipped twice; it happens every week since January.",
            state["version"],
        )
        version = done["version"]
        if done["status"] == "assessing":
            break
    for _ in range(30):
        poll = await client.get(f"{base}/interview/assessment", headers=headers)
        assert poll.status_code == 200
        if poll.json()["status"] == "review":
            break
        # Round-2 follow-ups (e.g. a dimension follow-up for the corrected
        # turn): answer with dimension-complete detail until done.
        state = (await client.get(f"{base}/interview/next", headers=headers)).json()
        if state["completed"] or state["question"] is None:
            await asyncio.sleep(0.2)
            continue
        done = await _answer(
            client, base, headers,
            f"For example, last week at work {state['question']['objective']} slipped twice; it happens every week since January.",
            state["version"],
        )
        version = done["version"]
    else:
        raise AssertionError("batch assessment did not complete")
    # WS1: confirm the review step so the briefing is generated.
    nxt = (await client.get(f"{base}/interview/next", headers=headers)).json()
    assert nxt["status"] == "review"
    res = await client.post(
        f"{base}/interview/review/confirm",
        json={"base_version": nxt["version"], "idempotency_key": f"ws5-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    rep = await client.get(f"{base}/interview/report", headers=headers)
    assert rep.status_code == 200, rep.text
    topic = next(t for t in rep.json()["topics"] if t["objective"] == PLAN_ORDER[0])
    assert topic["turns"][0]["answer"] == original
    assert topic["turns"][0]["correction"] == correction

    # No corrections once the interview is complete.
    final_state = (await client.get(f"{base}/interview/next", headers=headers)).json()
    assert final_state["completed"] is True
    res = await client.post(
        f"{base}/interview/correct",
        json={
            "corrects_turn": final_state["turns_answered"],
            "answer_text": "too late",
            "base_version": version,
            "idempotency_key": f"ws5-{uuid.uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert res.status_code == 409
