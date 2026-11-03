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
    INLINE_PROBE_BUDGET,
    MAX_FOLLOWUPS,
    MAX_TURNS,
    PLAN_ORDER,
    SKILL_VERSION,
    TOPIC_VERSION,
    _needs_detail_invite,
    build_prompt,
    detail_score,
    family_tensions,
    needs_effort_nudge,
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
    """Poll GET .../interview/assessment until followup, review, or complete.

    The batch job runs as a background task; with the dummy provider it
    finishes in milliseconds, so this returns almost immediately.
    """
    import asyncio

    for _ in range(tries):
        res = await client.get(f"{base}/interview/assessment", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        if body["status"] in ("followup", "review", "complete"):
            return body
        await asyncio.sleep(0.2)
    raise AssertionError(f"assessment stuck at {body['status']}")


async def _confirm(client, base: str, headers: dict) -> dict:
    """WS1: confirm the review step so the briefing is generated."""
    nxt = await client.get(f"{base}/interview/next", headers=headers)
    assert nxt.status_code == 200, nxt.text
    res = await client.post(
        f"{base}/interview/review/confirm",
        json={"base_version": nxt.json()["version"], "idempotency_key": f"fk5-cfm-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_unit_planner_round1_fixed_order():
    assert plan_next([])[0] == PLAN_ORDER[0] == "background-goals"
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


def test_unit_inline_probe_thin_answer():
    asked = [_turn(1, PLAN_ORDER[0], "bills")]
    obj, reason, done, hint = plan_next(asked, [])
    assert (obj, done) == (PLAN_ORDER[0], False)
    assert hint == {"kind": "inline"}
    assert "concrete detail" in reason


def test_unit_inline_probe_exemptions():
    # Denials, uncertainty, and substantive answers move on — never probed.
    for ans in ("No", "I cannot recall any of that, sorry", "a substantive detailed answer indeed"):
        asked = [_turn(1, PLAN_ORDER[0], ans)]
        obj, _, done, hint = plan_next(asked, [])
        assert (obj, done, hint) == (PLAN_ORDER[1], False, None)


def test_unit_inline_probe_once_per_objective_and_budget():
    asked = [
        _turn(1, PLAN_ORDER[0], "bills"),
        {**_turn(2, PLAN_ORDER[0], "still short"), "probe": "inline"},
        _turn(3, PLAN_ORDER[1], "x"),
    ]
    # PLAN_ORDER[0] already probed; PLAN_ORDER[1] thin and unprobed -> probe it.
    # (Three consecutive thin answers also trip the effort nudge, which rides along.)
    obj, _, done, hint = plan_next(asked, [])
    assert (obj, done, hint) == (PLAN_ORDER[1], False, {"kind": "inline", "effort_nudge": True})

    asked = []
    for i in range(3):
        asked.append(_turn(len(asked) + 1, PLAN_ORDER[i], "thin"))
        asked.append({**_turn(len(asked) + 1, PLAN_ORDER[i], "more detail here yes"), "probe": "inline"})
    asked.append(_turn(len(asked) + 1, PLAN_ORDER[3], "thin"))
    # Budget (3) exhausted -> move on even for thin answers.
    obj, _, done, hint = plan_next(asked, [])
    assert (obj, done, hint) == (PLAN_ORDER[4], False, None)


def test_unit_inline_probe_suppressed_in_round2():
    asked = [_turn(i + 1, t, "y" * 40) for i, t in enumerate(PLAN_ORDER)]
    asked[-1] = _turn(len(PLAN_ORDER), PLAN_ORDER[-1], "x")  # thin last answer
    queue = [{"objective": "forgetfulness", "reason": "Follow up"}]
    obj, _, done, hint = plan_next(asked, queue)
    assert (obj, done, hint) == ("forgetfulness", False, {"kind": "followup"})


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
    assert MAX_TURNS == len(PLAN_ORDER) + INLINE_PROBE_BUDGET + MAX_FOLLOWUPS


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


def test_unit_reasoning_effort_options():
    from app.llm import LLMConfig, chat_options, load_config

    assert load_config().reasoning_effort == "minimal"
    assert chat_options(LLMConfig(), "minimal")["reasoning"] == {"effort": "minimal"}
    assert "reasoning" not in chat_options(LLMConfig(), None)
    assert "reasoning" not in chat_options(LLMConfig(), "off")
    assert chat_options(LLMConfig(json_mode="off"), "minimal") == {"reasoning": {"effort": "minimal"}}


def test_unit_answer_quality_parse():
    from app.llm import AnswerQuality, parse_llm_json

    good = parse_llm_json(
        '{"question_text": "What tasks are hardest?", "reason": "why now", '
        '"answer_quality": {"detail": 2, "has_example": true, "has_context": false}}',
        "attention-focus",
    )
    assert good.answer_quality == AnswerQuality(detail=2, has_example=True, has_context=False)
    # Absent quality degrades to None; the question still parses.
    assert parse_llm_json('{"question_text": "What is hardest?", "reason": "why"}', "attention-focus").answer_quality is None
    # Malformed quality degrades to None; the question still parses.
    for raw in ('{"detail": 9}', '{"detail": "lots"}', "[1]", '"high"'):
        q = parse_llm_json(
            '{"question_text": "What is hardest?", "reason": "why", "answer_quality": ' + raw + "}", "attention-focus"
        )
        assert q.answer_quality is None, raw
    # A bad question still fails loudly even with good quality.
    try:
        parse_llm_json('{"question_text": "x", "answer_quality": {"detail": 2}}', "attention-focus")
    except Exception:
        pass
    else:
        raise AssertionError("expected LLMError for short question_text")


def test_unit_detail_score_levels():
    from app.llm import AnswerQuality

    assert detail_score("") == 0
    assert detail_score("meh") == 0
    # Denials and uncertainty are complete answers: level 1, never 0.
    assert detail_score("No") == 1
    assert detail_score("I cannot recall any of that, sorry") == 1
    assert detail_score("A substantive detailed answer indeed yes") == 2
    # Advisory LLM rating can lift a longer vague answer, capped at 2.
    assert detail_score("meh", AnswerQuality(detail=0)) == 0
    assert detail_score("No", AnswerQuality(detail=0)) == 1
    assert detail_score("meh meh meh meh meh meh!", AnswerQuality(detail=2)) == 2
    # Extractor-confirmed context lifts to grounded; claims alone never do.
    assert detail_score("A substantive detailed answer indeed yes", AnswerQuality(detail=2), 0) == 2
    assert detail_score("A substantive detailed answer indeed yes", AnswerQuality(detail=2), 2) == 3
    assert detail_score("A substantive detailed answer indeed yes", None, 5) == 3
    # Stored dict form (as persisted on turns) works too.
    assert detail_score("meh meh meh meh meh meh!", {"detail": 2}, 0) == 2
    assert detail_score("anything", {"detail": 9}, 0) == 2


def test_unit_effort_nudge_rule():
    def _t(ans):
        return {"objective": PLAN_ORDER[0], "answer": ans}

    assert needs_effort_nudge([_t("meh"), _t("meh")]) is False  # streak too short
    assert needs_effort_nudge([_t("meh")] * 3) is True
    assert needs_effort_nudge([_t("meh")] * 3, nudge_shown=True) is False  # once per round
    assert needs_effort_nudge([_t("meh"), _t("meh"), _t("No")]) is False  # denial breaks chain
    assert needs_effort_nudge([_t("meh"), _t("meh"), _t("I cannot recall, sorry")]) is False  # uncertainty breaks chain
    assert needs_effort_nudge([_t("a substantive detailed answer indeed")] * 3) is False

    obj, _, done, hint = plan_next([_t("meh")] * 3, [])
    assert done is False and (hint or {}).get("effort_nudge") is True
    assert obj == PLAN_ORDER[0] and hint.get("kind") == "inline"  # nudge rides along; planning is unchanged
    _, _, _, hint2 = plan_next([_t("meh")] * 3, [], nudge_shown=True)
    assert not (hint2 or {}).get("effort_nudge")
    _, _, _, hint3 = plan_next([_t("a substantive detailed answer indeed")] * 3, [])
    assert not (hint3 or {}).get("effort_nudge")


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
    assert "brings you" in body["question"]["text"].lower()
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
            json={"answer_text": f"For example, last week at work task {i} slipped twice; it happens every week since January.", "base_version": version, "idempotency_key": key},
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
    assert final["status"] == "review"
    assert final["extract_total"] == len(PLAN_ORDER) and final["extracted"] == len(PLAN_ORDER)
    # WS1: the briefing waits for the review confirmation.
    assert (await client.get(f"{base}/interview/report", headers=headers)).status_code == 404
    await _confirm(client, base, headers)
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


async def test_assess_progress_writer(client):
    from app.assessment import write_assess_progress
    from app.db import get_db

    created = await _create(client)
    await _start(client, created, version=1)
    await write_assess_progress(get_db(), created["assessment_id"], 3, 14)
    doc = await get_db()["assessments"].find_one({"_id": created["assessment_id"]})
    assert doc["interview"]["assess_progress"] == {"done": 3, "total": 14}

    headers = _auth(created["password"])
    res = await client.get(
        f"/assessments/{created['assessment_id']}/interview/assessment", headers=headers
    )
    assert res.status_code == 200
    assert res.json()["extracted"] == 3 and res.json()["extract_total"] == 14


async def test_extract_single_turn_writes_and_dedupes(client):
    from app.assessment import extract_single_turn
    from app.db import get_db

    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    await _start(client, created, version=1)
    res = await client.post(
        f"{base}/interview/answer",
        json={"answer_text": "a substantive answer with concrete detail", "base_version": 2, "idempotency_key": f"fk5-ext-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text

    db = get_db()
    first = await extract_single_turn(db, created["assessment_id"], 1)
    assert first is not None and first["turn"] == 1
    obs = first["versions"][-1]["observations"][0]
    tdoc = await db["transcripts"].find_one({"_id": created["assessment_id"]})
    seg_text = next(s["text"] for s in tdoc["segments"] if s["id"] == obs["segment_id"])
    assert obs["quote"] and obs["quote"] in seg_text

    # Idempotent: second call returns the stored doc, no duplicate.
    second = await extract_single_turn(db, created["assessment_id"], 1)
    assert second["_id"] == first["_id"] and second["versions"] == first["versions"]
    assert await db["evidence"].count_documents({"assessment_id": created["assessment_id"]}) == 1

    # Unknown turn: nothing to extract, never raises.
    assert await extract_single_turn(db, created["assessment_id"], 99) is None


async def test_preextracted_turns_skip_batch_redo(client):
    from app.assessment import extract_single_turn
    from app.db import get_db

    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    await _start(client, created, version=1)

    # Answer two turns, pre-extract both like the background task would.
    version = 2
    for i in range(2):
        res = await client.post(
            f"{base}/interview/answer",
            json={"answer_text": f"For example, last week at work item {i} slipped twice; it happens every week since January.", "base_version": version, "idempotency_key": f"fk5-pre-{uuid.uuid4().hex[:8]}"},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        version = res.json()["version"]
    db = get_db()
    for tn in (1, 2):
        assert await extract_single_turn(db, created["assessment_id"], tn) is not None
    assert await db["evidence"].count_documents({"assessment_id": created["assessment_id"]}) == 2

    # Finish round 1; the batch must reuse the pre-extracted docs and complete.
    for i in range(2, len(PLAN_ORDER)):
        res = await client.post(
            f"{base}/interview/answer",
            json={"answer_text": f"For example, last week at work task {i} slipped twice; it happens every week since January.", "base_version": version, "idempotency_key": f"fk5-pre-{uuid.uuid4().hex[:8]}"},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        version = res.json()["version"]
    final = await _poll_assessment(client, base, headers)
    assert final["status"] in ("followup", "review", "complete")
    assert final["extract_total"] == len(PLAN_ORDER) and final["extracted"] == len(PLAN_ORDER)


async def _set_prefetch(client, created, prefetch: dict | None) -> None:
    from app.db import get_db

    await get_db()["assessments"].update_one(
        {"_id": created["assessment_id"]}, {"$set": {"interview.prefetch": prefetch}}
    )


def _marker_prefetch(for_turn: int, objective: str, text: str = "PREFETCHED MARKER QUESTION") -> dict:
    return {
        "for_turn": for_turn,
        "objective": objective,
        "reason": "prefetch test",
        "question": text,
        "answer": None,
        "probe": None,
        "model_provider": "dummy",
        "model_name": "dummy-stub",
        "skill_version": "skill-v0.4-draft",
        "topic_version": TOPIC_VERSION,
        "session": {"session_id": "test"},
    }


async def test_prefetch_consumed_instantly(client):
    from app.db import get_db
    from app.interview import PLAN_ORDER

    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    await _start(client, created, version=1)
    await _set_prefetch(client, created, _marker_prefetch(2, PLAN_ORDER[1]))

    res = await client.post(
        f"{base}/interview/answer",
        json={"answer_text": "a substantive answer with detail", "base_version": 2, "idempotency_key": f"fk5-pre-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["question"]["text"] == "PREFETCHED MARKER QUESTION"
    assert body["question"]["objective"] == PLAN_ORDER[1]
    doc = await get_db()["assessments"].find_one({"_id": created["assessment_id"]})
    # Consumed. A background prefetch for the question after next (turn 3)
    # may or may not have landed yet — either is correct.
    pre = doc["interview"]["prefetch"]
    assert pre is None or (pre["for_turn"] == 3 and pre["objective"] == PLAN_ORDER[2])


async def test_prefetch_mismatch_falls_back_live(client):
    from app.interview import PLAN_ORDER

    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    await _start(client, created, version=1)
    await _set_prefetch(client, created, _marker_prefetch(2, "wrong-objective"))

    res = await client.post(
        f"{base}/interview/answer",
        json={"answer_text": "a substantive answer with detail", "base_version": 2, "idempotency_key": f"fk5-pre-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["question"]["objective"] == PLAN_ORDER[1]
    assert body["question"]["text"] != "PREFETCHED MARKER QUESTION"


async def test_prefetch_task_writes_next(client):
    from app.db import get_db
    from app.interview import PLAN_ORDER
    from app.routes.interview import _prefetch_task

    created = await _create(client)
    await _start(client, created, version=1)
    await _set_prefetch(client, created, None)
    await _prefetch_task(created["assessment_id"], 0, 1)
    doc = await get_db()["assessments"].find_one({"_id": created["assessment_id"]})
    pre = doc["interview"]["prefetch"]
    assert pre["for_turn"] == 2 and pre["objective"] == PLAN_ORDER[1]
    assert pre["question"]


async def test_prefetch_trigger_endpoint(client):
    from app.interview import PLAN_ORDER

    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    await _start(client, created, version=1)

    assert (await client.post(f"{base}/interview/prefetch")).status_code == 401
    await _set_prefetch(client, created, _marker_prefetch(2, PLAN_ORDER[1]))
    res = await client.post(f"{base}/interview/prefetch", headers=headers)
    assert res.status_code == 200 and res.json() == {"scheduled": False}
    await _set_prefetch(client, created, None)
    res = await client.post(f"{base}/interview/prefetch", headers=headers)
    assert res.status_code == 200 and res.json() == {"scheduled": True}


async def test_round2_followup_flow(client):
    from app.db import get_db

    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    await _start(client, created, version=1)

    version = 2
    thin_targets = {"forgetfulness", "organization"}
    probed = set()
    last = None
    # Round 1: answer whatever is pending. Thin once per target (probe
    # answers stay thin too, so the batch still queues round-2 follow-ups
    # and the one-probe-per-objective rule is exercised).
    for _ in range(30):
        nxt = (await client.get(f"{base}/interview/next", headers=headers)).json()
        if nxt["completed"] or nxt["question"] is None:
            break
        oid = nxt["question"]["objective"]
        if oid in thin_targets and oid not in probed:
            ans = "x"
            probed.add(oid)
        elif oid in thin_targets:
            ans = "y"
        else:
            ans = f"For example, last week at work {oid} slipped twice; it happens every week since January."
        res = await client.post(
            f"{base}/interview/answer",
            json={"answer_text": ans, "base_version": version, "idempotency_key": f"fk5-r2-{uuid.uuid4().hex[:8]}"},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        last = res.json()
        version = last["version"]
        if last["status"] == "assessing":
            break
    assert last is not None and last["status"] == "assessing"

    doc = await get_db()["assessments"].find_one({"_id": created["assessment_id"]})
    inline_objectives = {t["objective"] for t in doc["interview"]["turns"] if (t.get("probe") or "") == "inline"}
    assert thin_targets <= inline_objectives  # both thin answers probed immediately

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
    assert final["status"] == "review"
    await _confirm(client, base, headers)
    rep = await client.get(f"{base}/interview/report", headers=headers)
    assert rep.status_code == 200
    assert rep.json()["turns_answered"] == len(PLAN_ORDER) + 4  # 14 + 2 inline + 2 follow-up


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


def _parse_sse(text: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for part in text.split("\n\n"):
        part = part.strip()
        if not part:
            continue
        name, data = "message", ""
        for line in part.splitlines():
            if line.startswith("event:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data += line.split(":", 1)[1].strip()
        events.append((name, data))
    return events


async def test_answer_stream_staged_events_and_done(client):
    import json

    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    await _start(client, created, version=1)

    # Live path: no prefetch stored, so the question is phrased inline.
    await _set_prefetch(client, created, None)
    key = f"fk5-stream-{uuid.uuid4().hex[:8]}"
    res = await client.post(
        f"{base}/interview/answer/stream",
        json={"answer_text": "streamed answer with detail", "base_version": 2, "idempotency_key": key},
        headers={**headers, "Accept": "text/event-stream"},
    )
    assert res.status_code == 200, res.text
    assert "text/event-stream" in res.headers.get("content-type", "")
    events = _parse_sse(res.text)
    names = [n for n, _ in events]
    assert names[0] == "received"
    assert "phrasing" in names and names[-1] == "done"
    done = json.loads(events[-1][1])
    assert done["turn_answered"] == 1 and done["question"] is not None
    assert "secret" not in res.text.lower() or "secret" not in done.get("question", {}).get("text", "")

    # Prefetch path: a matching prefetch is consumed with no phrasing event.
    from app.interview import PLAN_ORDER

    await _set_prefetch(client, created, _marker_prefetch(3, PLAN_ORDER[2], text="STREAM PREFETCH MARKER"))
    key2 = f"fk5-stream-{uuid.uuid4().hex[:8]}"
    res2 = await client.post(
        f"{base}/interview/answer/stream",
        json={"answer_text": "second streamed answer with detail", "base_version": done["version"], "idempotency_key": key2},
        headers={**headers, "Accept": "text/event-stream"},
    )
    assert res2.status_code == 200, res2.text
    events2 = _parse_sse(res2.text)
    names2 = [n for n, _ in events2]
    assert names2[0] == "received" and names2[-1] == "done"
    assert "phrasing" not in names2
    assert json.loads(events2[-1][1])["question"]["text"] == "STREAM PREFETCH MARKER"


async def test_answer_stream_replay_and_conflict(client):
    import json

    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    await _start(client, created, version=1)

    key = f"fk5-stream-idem-{uuid.uuid4().hex[:8]}"
    first = await client.post(
        f"{base}/interview/answer/stream",
        json={"answer_text": "first streamed answer", "base_version": 2, "idempotency_key": key},
        headers=headers,
    )
    assert first.status_code == 200
    replay = await client.post(
        f"{base}/interview/answer/stream",
        json={"answer_text": "first streamed answer", "base_version": 2, "idempotency_key": key},
        headers=headers,
    )
    assert replay.status_code == 200
    first_done = json.loads(_parse_sse(first.text)[-1][1])
    replay_done = json.loads(_parse_sse(replay.text)[-1][1])
    assert replay_done == {**first_done, "replayed": True}

    stale = await client.post(
        f"{base}/interview/answer/stream",
        json={"answer_text": "stale", "base_version": 2, "idempotency_key": f"fk5-stream-stale-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert stale.status_code == 200
    names = [n for n, _ in _parse_sse(stale.text)]
    assert names[-1] == "error"

    bad = await client.post(
        f"{base}/interview/answer/stream",
        json={"answer_text": "   ", "base_version": 3, "idempotency_key": f"fk5-stream-bad-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert bad.status_code == 422
    assert (await client.post(f"{base}/interview/answer/stream", json={"answer_text": "x", "base_version": 3, "idempotency_key": "k-12345678"})).status_code == 401


async def test_effort_nudge_after_three_thin_answers(client):
    from app.db import get_db

    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    await _start(client, created, version=1)

    version = 2
    nudged_at = None
    for i in range(5):
        res = await client.post(
            f"{base}/interview/answer",
            json={"answer_text": "meh", "base_version": version, "idempotency_key": f"fk5-nudge-{uuid.uuid4().hex[:8]}"},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        version = body["version"]
        if body["question"] and body["question"].get("effort_nudge") is True and nudged_at is None:
            nudged_at = i
    # Streak of 3 thin answers triggers the nudge on the 4th question...
    assert nudged_at == 2, f"nudge fired at answer index {nudged_at}"
    doc = await get_db()["assessments"].find_one({"_id": created["assessment_id"]})
    assert "effort_nudge:round1" in (doc["interview"].get("nudges_shown") or [])
    # ...and only once per round: the 5th question carries no nudge.
    res = await client.post(
        f"{base}/interview/answer",
        json={"answer_text": "meh", "base_version": version, "idempotency_key": f"fk5-nudge-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["question"].get("effort_nudge") is not True


async def test_no_nudge_for_denials_or_detailed_answers(client):
    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    await _start(client, created, version=1)

    version = 2
    for ans in ("No", "No, never an issue", "I cannot recall, sorry"):
        res = await client.post(
            f"{base}/interview/answer",
            json={"answer_text": ans, "base_version": version, "idempotency_key": f"fk5-nonudge-{uuid.uuid4().hex[:8]}"},
            headers=headers,
        )
        assert res.status_code == 200, res.text
        version = res.json()["version"]
        assert res.json()["question"].get("effort_nudge") is not True
