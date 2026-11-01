"""Interview API: conversation rounds plus a batch assessment between them.

Endpoints (all require the assessment Bearer secret; ID is lookup only):
  POST /assessments/{id}/interview/start   begin round 1 -> Q1
  POST /assessments/{id}/interview/answer  save answer -> next Q (or assessment)
  GET  /assessments/{id}/interview/next    read-only resume (no version change)
  GET  /assessments/{id}/interview/assessment  poll the batch job; triggers it if needed
  GET  /assessments/{id}/interview/transcript  verbatim segments, read-only
  GET  /assessments/{id}/interview/evidence    versioned observations, read-only

Round 1 asks every objective once — a pure conversation, no analysis and
no evidence written. Completing round 1 schedules the batch assessment
job (after the response): per-turn extraction, deterministic synthesis
(coverage, tensions, follow-up queue), then either a follow-up round or
the final briefing. Concurrency/idempotency mirror the screening
endpoint: writes match only the exact base_version with an unseen
idempotency key; replays return the stored result; otherwise 409.

Latency design: each answered turn schedules a background extraction for
just that turn while the user reads the next question. The end-of-round
batch therefore usually finds most evidence already stored (idempotent
dedupe) and only synthesizes + phrases the first follow-up.
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from .. import interview as planner
from ..assessment import extract_single_turn, run_round_assessment
from ..db import get_db
from ..interview import (
    ANSWER_MAX_LEN,
    HARD_TURN_CAP,
    SKILL_VERSION,
    TOPIC_VERSION,
)
from ..llm import LLMError, LLMQuestion, generate_next_question, load_config
from ..question_validation import (
    REPAIR_HINTS,
    VALIDATION_MAX_REGENS,
    validate_question,
)
from ..models import (
    EvidenceOut,
    EvidenceTurnOut,
    InterviewAnswerRequest,
    InterviewAnswerResult,
    InterviewAssessmentOut,
    InterviewBriefingOut,
    InterviewNextOut,
    InterviewQuestionOut,
    InterviewStartRequest,
    InterviewStartResult,
    TranscriptOut,
)
from ..transcripts import append_turn_segments
from .assessments import require_assessment

router = APIRouter(prefix="/assessments", tags=["interview"])

log = logging.getLogger("mrprof")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _question_out(turn_doc: dict) -> InterviewQuestionOut:
    return InterviewQuestionOut(
        turn=turn_doc["turn"],
        objective=turn_doc["objective"],
        reason=turn_doc["reason"],
        text=turn_doc["question"],
        model_provider=turn_doc["model_provider"],
        model_name=turn_doc["model_name"],
        skill_version=turn_doc["skill_version"],
        topic_version=turn_doc["topic_version"],
        effort_nudge=bool(turn_doc.get("effort_nudge", False)),
    )


def _nudge_shown(iv: dict, turns: list[dict]) -> bool:
    """Whether the effort nudge already fired this round (once-per-round cap)."""
    mark = (
        planner.EFFORT_NUDGE_MARK_ROUND2
        if planner.nudge_round(turns) == "round2"
        else planner.EFFORT_NUDGE_MARK_ROUND1
    )
    return mark in (iv.get("nudges_shown") or [])


def _nudge_mark(turns: list[dict]) -> str:
    return (
        planner.EFFORT_NUDGE_MARK_ROUND2
        if planner.nudge_round(turns) == "round2"
        else planner.EFFORT_NUDGE_MARK_ROUND1
    )


def _next_out(doc: dict) -> InterviewNextOut:
    iv = doc.get("interview") or {}
    current = iv.get("current")
    return InterviewNextOut(
        assessment_id=doc["_id"],
        version=doc["version"],
        status=iv.get("status", "active"),
        turns_answered=len(iv.get("turns", [])),
        question=_question_out(current) if current else None,
        completed=iv.get("status") == "complete",
        mode=iv.get("mode", "full"),
    )


def _replay_result(doc: dict, key: str) -> dict | None:
    for entry in doc.get("idem", []):
        if entry["key"] == key:
            return entry
    return None


async def _generate(assessment_id: str, objective: str, reason: str, history: list, screening: dict | None, hint: dict | None = None) -> tuple:
    """Run the InterviewAgent for the planner-assigned objective.

    Returns (question, model_info, session_blob, probe, quality) where probe is the
    deterministic marker (None, "followup", "inline", or "clarify:<family>")
    stored on the turn for stop-rule accounting. "followup" marks round-2
    queue items; "inline" marks round-1 thin-answer probes (excluded from
    round-2 queue accounting). quality is the interviewer's advisory rating
    of the just-given answer (dict or None) — stored on the answered turn
    for detail reporting; never drives planning on its own.

    F10a: the phrased question is validated in code (off-objective /
    already-answered / repeated / leading / compound / too-long) with
    bounded regens; persistent failure falls back to the pre-approved
    opener so the interview never stalls. model_info carries phrase_ms
    (server-side phrasing latency; user think-time excluded).
    """
    import time as _time

    started = _time.monotonic()
    cfg = load_config()
    last_answer = history[-1].get("answer") if history else None
    hint = hint or {}
    prompt = planner.build_prompt(
        objective=objective, reason=reason, history=history, screening=screening,
        last_answer=last_answer, tension=hint.get("tension"),
    )
    fallbacks = {t.get("opener", "") for t in planner.load_topics().values()}
    prior_qs = [t.get("question", "") for t in history if t.get("question")]
    asked = [t.get("objective", "") for t in history if t.get("objective")]
    current_prompt = prompt
    question = None
    model_info: dict = {}
    session_blob: dict = {}
    for attempt in range(1 + VALIDATION_MAX_REGENS):
        question, model_info, session_blob = await generate_next_question(
            cfg=cfg,
            instructions=planner.load_skill(),
            prompt=current_prompt,
            objective=objective,
            reason=reason,
            fallback_question=planner.fallback_question(objective),
            session_id=assessment_id,
        )
        # Dummy path returns the pre-approved opener: valid by construction.
        if question.question_text == planner.fallback_question(objective):
            break
        code = validate_question(
            question.question_text, question.objective, objective,
            prior_questions=prior_qs, asked_objectives=asked,
            fallback_texts=fallbacks,
        )
        if code == "ok":
            break
        log.warning("question validation failed (%s), regen %d", code, attempt + 1)
        if attempt >= VALIDATION_MAX_REGENS:
            question = LLMQuestion(
                question_text=planner.fallback_question(objective),
                objective=objective, reason=reason if len(reason or "") >= 3 else "cover assigned objective",
            )
            model_info["validation_fallback"] = code
            break
        repair = REPAIR_HINTS.get(code, "Ask exactly ONE short neutral question for the assigned objective.")
        base = current_prompt if isinstance(current_prompt, str) else "\n".join(current_prompt)
        current_prompt = (
            f"Your previous question was rejected ({code}): {repair} "
            "Reply with JSON ONLY, no other text.\n\n" + base
        )
    assert question is not None
    model_info["phrase_ms"] = round((_time.monotonic() - started) * 1000, 1)
    kind = hint.get("kind")
    probe = f"clarify:{hint['family']}" if kind == "clarify" else (kind if kind in ("followup", "inline") else None)
    quality = question.answer_quality.model_dump() if question.answer_quality is not None else None
    return question, model_info, session_blob, probe, quality


async def _phrase_for_job(assessment_id: str, objective: str, reason: str, history: list, screening: dict | None, tension: str | None = None) -> tuple:
    """Phrase one question for the batch job. Returns (text, model_info, session).

    Same F10a validation as the live path: bounded regens, then the
    pre-approved opener. model_info carries phrase_ms.
    """
    import time as _time

    started = _time.monotonic()
    cfg = load_config()
    last_answer = history[-1].get("answer") if history else None
    prompt = planner.build_prompt(
        objective=objective, reason=reason, history=history, screening=screening,
        last_answer=last_answer, tension=tension,
    )
    fallbacks = {t.get("opener", "") for t in planner.load_topics().values()}
    prior_qs = [t.get("question", "") for t in history if t.get("question")]
    asked = [t.get("objective", "") for t in history if t.get("objective")]
    current_prompt = prompt
    text, model_info, session_blob = planner.fallback_question(objective), {"provider": "dummy"}, {}
    for attempt in range(1 + VALIDATION_MAX_REGENS):
        question, model_info, session_blob = await generate_next_question(
            cfg=cfg,
            instructions=planner.load_skill(),
            prompt=current_prompt,
            objective=objective,
            reason=reason,
            fallback_question=planner.fallback_question(objective),
            session_id=assessment_id,
        )
        model_info["phrase_ms"] = round((_time.monotonic() - started) * 1000, 1)
        if question.question_text == planner.fallback_question(objective):
            return question.question_text, model_info, session_blob
        code = validate_question(
            question.question_text, question.objective, objective,
            prior_questions=prior_qs, asked_objectives=asked,
            fallback_texts=fallbacks,
        )
        if code == "ok":
            return question.question_text, model_info, session_blob
        log.warning("batch phrase validation failed (%s), regen %d", code, attempt + 1)
        if attempt >= VALIDATION_MAX_REGENS:
            model_info["validation_fallback"] = code
            return planner.fallback_question(objective), model_info, session_blob
        repair = REPAIR_HINTS.get(code, "Ask exactly ONE short neutral question for the assigned objective.")
        base = current_prompt if isinstance(current_prompt, str) else "\n".join(current_prompt)
        current_prompt = (
            f"Your previous question was rejected ({code}): {repair} "
            "Reply with JSON ONLY, no other text.\n\n" + base
        )
    return text, model_info, session_blob


def _consume_prefetch(iv: dict, pending_turn: int, objective: str) -> dict | None:
    """Return a ready next-turn doc from a matching prefetch, else None.

    plan_next() is deterministic over answered objectives, probe markers,
    and the thin-answer check — and the prefetch task plans with the same
    real turns, so a match phrases the exact same objective/reason. Only
    the phrasing context lags by one answer, which is acceptable for
    fixed-order openers. Mismatch or absence falls back to the live path.
    """
    pre = iv.get("prefetch")
    if not pre or pre.get("for_turn") != pending_turn + 1 or pre.get("objective") != objective:
        return None
    return {
        "turn": pending_turn + 1,
        "objective": pre["objective"],
        "reason": pre["reason"],
        "question": pre["question"],
        "answer": None,
        "probe": pre.get("probe"),
        "effort_nudge": bool(pre.get("effort_nudge", False)),
        "phrase_ms": pre.get("phrase_ms"),
        "model_provider": pre.get("model_provider", "dummy"),
        "model_name": pre.get("model_name", "dummy-stub"),
        "skill_version": pre.get("skill_version", SKILL_VERSION),
        "topic_version": pre.get("topic_version", TOPIC_VERSION),
    }


def _prefetch_session(iv: dict, pending_turn: int, objective: str, fallback: dict) -> dict:
    pre = iv.get("prefetch")
    if pre and pre.get("for_turn") == pending_turn + 1 and pre.get("objective") == objective:
        return pre.get("session") or fallback
    return fallback


async def _extract_task(assessment_id: str, turn: int) -> None:
    """Background per-turn extraction. Best-effort: never fails the loop.

    Scheduled after each answer write while the user reads the next
    question. Idempotent with the batch job's _extract_missing (existing
    turn docs are kept), so a turn extracted here is skipped there.
    """
    try:
        await extract_single_turn(get_db(), assessment_id, turn)
    except Exception:  # noqa: BLE001 - background work only logs
        log.warning("background extract task failed for %s turn %d", assessment_id, turn)


async def _prefetch_task(assessment_id: str, expected_answered: int, expected_pending_turn: int) -> None:
    """Phrase the question after next ahead of the user. Best-effort.

    Runs after the response while the user reads/thinks. Plans past the
    pending current question (plan_next is pure over answered objectives),
    guarded so a stale task can never overwrite newer state; failures only
    log, and the live path covers any miss.
    """
    try:
        db = get_db()
        doc = await db["assessments"].find_one({"_id": assessment_id})
        if doc is None:
            return
        iv = doc.get("interview") or {}
        if iv.get("status") not in ("active", "followup"):
            return
        if iv.get("prefetch") is not None:
            return
        turns = iv.get("turns", [])
        current = iv.get("current")
        if len(turns) != expected_answered or current is None or current.get("turn") != expected_pending_turn:
            return
        # Plan with the real answered turns (answer text drives the thin
        # check) plus the pending objective. Exact: same inputs as the live
        # path will see, minus the not-yet-written probe answer — and no
        # prefetch is scheduled on probe turns, so that gap never matters.
        pseudo = list(turns) + [{"objective": current["objective"]}]
        queue = iv.get("followups") or []
        mode = iv.get("mode", "full")
        objective, reason, done, hint = planner.plan_next(pseudo, queue, _nudge_shown(iv, pseudo), mode)
        if done:
            return
        question, model_info, session_blob, probe, quality = await _generate(
            assessment_id, objective, reason, turns, doc.get("screening"), hint=hint,
        )
        nudge = bool((hint or {}).get("effort_nudge", False))
        prefetch = {
            "for_turn": expected_pending_turn + 1,
            "objective": objective,
            "reason": reason,
            "question": question.question_text,
            "answer": None,
            "probe": probe,
            "effort_nudge": nudge,
            "phrase_ms": model_info.get("phrase_ms"),
            "model_provider": model_info["provider"],
            "model_name": model_info["model"],
            "skill_version": SKILL_VERSION,
            "topic_version": TOPIC_VERSION,
            "session": session_blob,
        }
        update: dict = {"interview.prefetch": prefetch}
        array_filters = None
        if nudge:
            marks = list(iv.get("nudges_shown") or [])
            mark = _nudge_mark(pseudo)
            if mark not in marks:
                marks.append(mark)
            update["interview.nudges_shown"] = marks
        if quality is not None and turns:
            # Backfill the advisory rating onto the already-saved answered
            # turn (the live path stores it inline; prefetch covers the
            # consumed-prefetch path). Best-effort: a miss just leaves the
            # turn to polarity + extractor scoring.
            update["interview.turns.$[t].quality"] = quality
            array_filters = [{"t.turn": turns[-1]["turn"]}]
        await db["assessments"].update_one(
            {
                "_id": assessment_id,
                "interview.turns": {"$size": expected_answered},
                "interview.prefetch": None,
            },
            {"$set": update},
            array_filters=array_filters,
        )
    except Exception:  # noqa: BLE001 - prefetch never fails the interview loop
        log.warning("prefetch failed for %s", assessment_id)


@router.post("/{assessment_id}/interview/start", response_model=InterviewStartResult)
async def start_interview(
    assessment_id: str,
    body: InterviewStartRequest,
    background: BackgroundTasks,
    doc: dict = Depends(require_assessment),
) -> InterviewStartResult:
    existing = doc.get("interview")
    if existing is not None:
        replay = _replay_result(doc, body.idempotency_key)
        if replay is not None and replay.get("kind") == "interview-start":
            return InterviewStartResult(
                assessment_id=doc["_id"],
                version=replay["version"],
                stage=doc["stage"],
                status=(existing.get("status") or "active"),
                question=_question_out(existing["current"]),
                replayed=True,
                mode=existing.get("mode", "full"),
            )
        raise HTTPException(
            status_code=409,
            detail={"error": "interview_already_started", "current_version": doc["version"]},
        )
    mode = (body.mode or "full").strip().lower()
    if mode not in planner.INTERVIEW_MODES:
        raise HTTPException(status_code=422, detail=f"mode must be one of {list(planner.INTERVIEW_MODES)}")
    objective, reason, _, _ = planner.plan_next([], mode=mode)
    try:
        question, model_info, session_blob, _, _ = await _generate(
            assessment_id, objective, reason, [], doc.get("screening")
        )
    except LLMError as exc:
        raise HTTPException(status_code=exc.status, detail={"error": exc.code, "message": exc.message})
    col = get_db()["assessments"]
    now = _now()
    turn_doc = {
        "turn": 1,
        "objective": question.objective,
        "reason": question.reason,
        "question": question.question_text,
        "answer": None,
        "probe": None,
        "phrase_ms": model_info.get("phrase_ms"),
        "model_provider": model_info["provider"],
        "model_name": model_info["model"],
        "skill_version": SKILL_VERSION,
        "topic_version": TOPIC_VERSION,
    }
    result = await col.find_one_and_update(
        {
            "_id": doc["_id"],
            "version": body.base_version,
            "idem.key": {"$ne": body.idempotency_key},
            "interview": {"$exists": False},
        },
        {
            "$set": {
                "stage": "interview",
                "version": body.base_version + 1,
                "updated_at": now,
                "interview": {
                    "status": "active",
                    "mode": mode,
                    "skill_version": SKILL_VERSION,
                    "topic_version": TOPIC_VERSION,
                    "turns": [],
                    "current": turn_doc,
                    "session": session_blob,
                    "followups": [],
                    "assessed_turns": 0,
                    "rounds_done": 0,
                    "assessment": None,
                    "assessing_error": None,
                    "started_at": now,
                    "updated_at": now,
                },
            },
            "$push": {
                "idem": {
                    "key": body.idempotency_key,
                    "version": body.base_version + 1,
                    "kind": "interview-start",
                }
            },
        },
        return_document=True,
    )
    if result is None:
        current = await col.find_one({"_id": doc["_id"]})
        assert current is not None
        replay = _replay_result(current, body.idempotency_key)
        if replay is not None and replay.get("kind") == "interview-start":
            iv = current["interview"]
            return InterviewStartResult(
                assessment_id=current["_id"],
                version=replay["version"],
                stage=current["stage"],
                status=iv.get("status", "active"),
                question=_question_out(iv["current"]),
                replayed=True,
                mode=iv.get("mode", "full"),
            )
        raise HTTPException(
            status_code=409,
            detail={"error": "version_conflict", "current_version": current["version"]},
        )
    await append_turn_segments(
        get_db(), result["_id"], 1, turn_doc["question"], None,
        SKILL_VERSION, TOPIC_VERSION,
    )
    # Phrase Q2 while the user reads Q1; the opener order is deterministic.
    background.add_task(_prefetch_task, result["_id"], 0, 1)
    return InterviewStartResult(
        assessment_id=result["_id"],
        version=result["version"],
        stage=result["stage"],
        status="active",
        question=_question_out(turn_doc),
        mode=mode,
    )


@router.post("/{assessment_id}/interview/answer", response_model=InterviewAnswerResult)
async def submit_answer(
    assessment_id: str,
    body: InterviewAnswerRequest,
    background: BackgroundTasks,
    doc: dict = Depends(require_assessment),
) -> InterviewAnswerResult:
    answer = body.answer_text.strip()
    if not answer:
        raise HTTPException(status_code=422, detail="answer must not be empty")
    if len(body.answer_text) > ANSWER_MAX_LEN:
        raise HTTPException(status_code=422, detail=f"answer must be at most {ANSWER_MAX_LEN} characters")
    iv = doc.get("interview")
    if iv is None:
        raise HTTPException(status_code=404, detail="interview not started")
    if iv.get("status") == "complete":
        raise HTTPException(status_code=409, detail={"error": "interview_complete"})
    pending = iv.get("current")
    if pending is None:
        raise HTTPException(status_code=409, detail={"error": "no_pending_question"})
    replay = _replay_result(doc, body.idempotency_key)
    if replay is not None and replay.get("kind") == "interview-answer":
        fresh = await get_db()["assessments"].find_one({"_id": doc["_id"]})
        assert fresh is not None
        return _answer_result_from_doc(fresh, replay["version"], replayed=True)

    history = list(iv.get("turns", []))
    mode = iv.get("mode", "full")
    answered_turn = {
        "turn": pending["turn"],
        "objective": pending["objective"],
        "reason": pending["reason"],
        "question": pending["question"],
        "answer": answer[:ANSWER_MAX_LEN],
        "answered_at": _now(),
        "probe": pending.get("probe"),
        "phrase_ms": pending.get("phrase_ms"),
        "model_provider": pending["model_provider"],
        "model_name": pending["model_name"],
        "skill_version": pending["skill_version"],
        "topic_version": pending["topic_version"],
    }
    new_history = history + [answered_turn]
    queue = iv.get("followups") or []
    assessed_turns = iv.get("assessed_turns", 0)
    schedule_assessment = False
    cap = len(planner.round1_objectives(mode)) + planner.INLINE_PROBE_BUDGET + planner.max_followups(mode)
    if len(new_history) >= HARD_TURN_CAP or len(new_history) >= cap:
        completed, next_turn_doc = False, None
        session_blob = iv.get("session") or {"session_id": assessment_id}
        schedule_assessment = True
    else:
        completed = False
        objective, reason, done, hint = planner.plan_next(new_history, queue, _nudge_shown(iv, new_history), mode)
        if done and assessed_turns != len(new_history):
            # Round complete but not yet assessed -> run the batch job.
            next_turn_doc = None
            session_blob = iv.get("session") or {"session_id": assessment_id}
            schedule_assessment = True
        elif done:
            next_turn_doc = None
            completed = True
            session_blob = iv.get("session") or {"session_id": assessment_id}
        else:
            session_blob = iv.get("session") or {"session_id": assessment_id}
            prefetched = _consume_prefetch(iv, pending["turn"], objective)
            if prefetched is not None:
                next_turn_doc = prefetched
                session_blob = _prefetch_session(iv, pending["turn"], objective, session_blob)
            else:
                try:
                    question, model_info, session_blob, probe, quality = await _generate(
                        assessment_id, objective, reason, new_history, doc.get("screening"),
                        hint=hint,
                    )
                except LLMError as exc:
                    # No write happened: the saved answer is untouched, the same
                    # key can be retried safely.
                    raise HTTPException(
                        status_code=exc.status, detail={"error": exc.code, "message": exc.message}
                    )
                answered_turn["quality"] = quality
                next_turn_doc = {
                    "turn": pending["turn"] + 1,
                    "objective": question.objective,
                    "reason": question.reason,
                    "question": question.question_text,
                    "answer": None,
                    "probe": probe,
                    "effort_nudge": bool((hint or {}).get("effort_nudge", False)),
                    "phrase_ms": model_info.get("phrase_ms"),
                    "model_provider": model_info["provider"],
                    "model_name": model_info["model"],
                    "skill_version": SKILL_VERSION,
                    "topic_version": TOPIC_VERSION,
                }
    col = get_db()["assessments"]
    now = _now()
    if schedule_assessment:
        new_status = "assessing"
    elif completed:
        new_status = "complete"
    else:
        new_status = "followup" if queue else "active"
    marks = list(iv.get("nudges_shown") or [])
    if next_turn_doc is not None and next_turn_doc.get("effort_nudge"):
        mark = _nudge_mark(new_history)
        if mark not in marks:
            marks.append(mark)
    result = await col.find_one_and_update(
        {
            "_id": doc["_id"],
            "version": body.base_version,
            "idem.key": {"$ne": body.idempotency_key},
        },
        {
            "$set": {
                "version": body.base_version + 1,
                "updated_at": now,
                "interview.status": new_status,
                "interview.turns": [{**t, "answered_at": t["answered_at"]} for t in new_history],
                "interview.current": next_turn_doc,
                "interview.session": session_blob,
                "interview.prefetch": None,
                "interview.nudges_shown": marks,
                "interview.updated_at": now,
            },
            "$push": {
                "idem": {
                    "key": body.idempotency_key,
                    "version": body.base_version + 1,
                    "kind": "interview-answer",
                    "turn": pending["turn"],
                }
            },
        },
        return_document=True,
    )
    if result is None:
        current = await col.find_one({"_id": doc["_id"]})
        assert current is not None
        replay = _replay_result(current, body.idempotency_key)
        if replay is not None and replay.get("kind") == "interview-answer":
            return _answer_result_from_doc(current, replay["version"], replayed=True)
        raise HTTPException(
            status_code=409,
            detail={"error": "version_conflict", "current_version": current["version"]},
        )
    if completed:
        # Defensive: the batch job is the only briefing writer, so reaching
        # here with assessed turns means it already ran and set complete.
        pass
    await append_turn_segments(
        get_db(), result["_id"], answered_turn["turn"], answered_turn["question"], answered_turn["answer"],
        SKILL_VERSION, TOPIC_VERSION,
    )
    if next_turn_doc is not None:
        await append_turn_segments(
            get_db(), result["_id"], next_turn_doc["turn"], next_turn_doc["question"], None,
            SKILL_VERSION, TOPIC_VERSION,
        )
    if schedule_assessment:
        # Batch evidence extraction + synthesis runs after the response.
        background.add_task(run_round_assessment, get_db(), result["_id"], _phrase_for_job)
    elif next_turn_doc is not None and next_turn_doc.get("probe") != "inline":
        # Phrase the question after next while the user reads this one.
        # No prefetch on inline-probe turns: the probe answer decides the
        # plan, so the live path asks it with full context.
        background.add_task(_prefetch_task, result["_id"], len(new_history), next_turn_doc["turn"])
    # Extract this turn's evidence in the background while the user reads
    # on. Idempotent with the batch: whichever lands first wins.
    background.add_task(_extract_task, result["_id"], answered_turn["turn"])
    return _answer_result_from_doc(result, result["version"])


def _answer_result_from_doc(doc: dict, version: int, replayed: bool = False) -> InterviewAnswerResult:
    iv = doc.get("interview") or {}
    turns = iv.get("turns", [])
    current = iv.get("current")
    completed = iv.get("status") == "complete"
    return InterviewAnswerResult(
        assessment_id=doc["_id"],
        version=version,
        turn_answered=len(turns),
        status=iv.get("status", "active"),
        question=_question_out(current) if current and not completed else None,
        completed=completed,
        replayed=replayed,
        mode=iv.get("mode", "full"),
    )


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@router.post("/{assessment_id}/interview/answer/stream")
async def submit_answer_stream(
    assessment_id: str,
    body: InterviewAnswerRequest,
    background: BackgroundTasks,
    doc: dict = Depends(require_assessment),
):
    """Staged-event stream for answer submission (Change 1).

    Same validation, auth, idempotency, and atomic write as the sync
    endpoint; transport only. Events: received -> phrasing|assessing ->
    done|error. A matching prefetch is consumed instantly (no phrasing
    event); the client then triggers the following prefetch via
    POST .../interview/prefetch. Strict JSON/Pydantic validation stays
    server-side. Disconnect before `done` is safe: no write happened, or
    the same idempotency key replays via GET .../next + POST retry.
    """
    answer = body.answer_text.strip()
    if not answer:
        raise HTTPException(status_code=422, detail="answer must not be empty")
    if len(body.answer_text) > ANSWER_MAX_LEN:
        raise HTTPException(status_code=422, detail=f"answer must be at most {ANSWER_MAX_LEN} characters")
    iv = doc.get("interview")
    if iv is None:
        raise HTTPException(status_code=404, detail="interview not started")
    if iv.get("status") == "complete":
        raise HTTPException(status_code=409, detail={"error": "interview_complete"})
    pending = iv.get("current")
    if pending is None:
        raise HTTPException(status_code=409, detail={"error": "no_pending_question"})

    async def _events():
        # Replay fast-path: same key already stored.
        replay = _replay_result(doc, body.idempotency_key)
        if replay is not None and replay.get("kind") == "interview-answer":
            fresh = await get_db()["assessments"].find_one({"_id": doc["_id"]})
            assert fresh is not None
            result = _answer_result_from_doc(fresh, replay["version"], replayed=True)
            yield _sse("done", result.model_dump())
            return

        yield _sse("received", {"turn": pending["turn"]})

        history = list(iv.get("turns", []))
        mode = iv.get("mode", "full")
        answered_turn = {
            "turn": pending["turn"],
            "objective": pending["objective"],
            "reason": pending["reason"],
            "question": pending["question"],
            "answer": answer[:ANSWER_MAX_LEN],
            "answered_at": _now(),
            "probe": pending.get("probe"),
            "phrase_ms": pending.get("phrase_ms"),
            "model_provider": pending["model_provider"],
            "model_name": pending["model_name"],
            "skill_version": pending["skill_version"],
            "topic_version": pending["topic_version"],
        }
        new_history = history + [answered_turn]
        queue = iv.get("followups") or []
        assessed_turns = iv.get("assessed_turns", 0)
        schedule_assessment = False
        next_turn_doc: dict | None = None
        session_blob = iv.get("session") or {"session_id": assessment_id}
        cap = len(planner.round1_objectives(mode)) + planner.INLINE_PROBE_BUDGET + planner.max_followups(mode)
        if len(new_history) >= HARD_TURN_CAP or len(new_history) >= cap:
            schedule_assessment = True
        else:
            objective, reason, done, hint = planner.plan_next(new_history, queue, _nudge_shown(iv, new_history), mode)
            if done and assessed_turns != len(new_history):
                schedule_assessment = True
            elif done:
                pass
            else:
                prefetched = _consume_prefetch(iv, pending["turn"], objective)
                if prefetched is not None:
                    next_turn_doc = prefetched
                    session_blob = _prefetch_session(iv, pending["turn"], objective, session_blob)
                else:
                    yield _sse("phrasing", {"objective": objective, "reason": reason})
                    try:
                        question, model_info, session_blob, probe, quality = await _generate(
                            assessment_id, objective, reason, new_history,
                            doc.get("screening"), hint=hint,
                        )
                    except LLMError as exc:
                        yield _sse("error", {"error": exc.code, "message": exc.message})
                        return
                    answered_turn["quality"] = quality
                    next_turn_doc = {
                        "turn": pending["turn"] + 1,
                        "objective": question.objective,
                        "reason": question.reason,
                        "question": question.question_text,
                        "answer": None,
                        "probe": probe,
                        "effort_nudge": bool((hint or {}).get("effort_nudge", False)),
                        "phrase_ms": model_info.get("phrase_ms"),
                        "model_provider": model_info["provider"],
                        "model_name": model_info["model"],
                        "skill_version": SKILL_VERSION,
                        "topic_version": TOPIC_VERSION,
                    }
        if schedule_assessment:
            yield _sse("assessing", {"turns_answered": len(new_history)})

        col = get_db()["assessments"]
        now = _now()
        if schedule_assessment:
            new_status = "assessing"
        elif next_turn_doc is None:
            new_status = "complete"
        else:
            new_status = "followup" if queue else "active"
        marks = list((iv.get("nudges_shown") or []))
        if next_turn_doc is not None and next_turn_doc.get("effort_nudge"):
            mark = _nudge_mark(new_history)
            if mark not in marks:
                marks.append(mark)
        result_doc = await col.find_one_and_update(
            {
                "_id": doc["_id"],
                "version": body.base_version,
                "idem.key": {"$ne": body.idempotency_key},
            },
            {
                "$set": {
                    "version": body.base_version + 1,
                    "updated_at": now,
                    "interview.status": new_status,
                    "interview.turns": [{**t, "answered_at": t["answered_at"]} for t in new_history],
                    "interview.current": next_turn_doc,
                    "interview.session": session_blob,
                    "interview.prefetch": None,
                    "interview.nudges_shown": marks,
                    "interview.updated_at": now,
                },
                "$push": {
                    "idem": {
                        "key": body.idempotency_key,
                        "version": body.base_version + 1,
                        "kind": "interview-answer",
                        "turn": pending["turn"],
                    }
                },
            },
            return_document=True,
        )
        if result_doc is None:
            current = await col.find_one({"_id": doc["_id"]})
            assert current is not None
            replay2 = _replay_result(current, body.idempotency_key)
            if replay2 is not None and replay2.get("kind") == "interview-answer":
                result = _answer_result_from_doc(current, replay2["version"], replayed=True)
                yield _sse("done", result.model_dump())
                return
            yield _sse(
                "error",
                {"error": "version_conflict", "message": "the interview changed — reload and retry", "current_version": current["version"]},
            )
            return
        await append_turn_segments(
            get_db(), result_doc["_id"], answered_turn["turn"],
            answered_turn["question"], answered_turn["answer"],
            SKILL_VERSION, TOPIC_VERSION,
        )
        if next_turn_doc is not None:
            await append_turn_segments(
                get_db(), result_doc["_id"], next_turn_doc["turn"],
                next_turn_doc["question"], None, SKILL_VERSION, TOPIC_VERSION,
            )
        # Batch job is triggered by GET .../assessment polling (self-healing).
        # Prefetch for the following turn is triggered by the client via
        # POST .../interview/prefetch once it holds the new question.
        # Per-turn extraction is scheduled here (turn number is known
        # upfront); it no-ops harmlessly if the write above lost a race.
        background.add_task(_extract_task, assessment_id, pending["turn"])
        result = _answer_result_from_doc(result_doc, result_doc["version"])
        yield _sse("done", result.model_dump())

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=background,
    )


@router.post("/{assessment_id}/interview/prefetch")
async def trigger_prefetch(
    assessment_id: str,
    background: BackgroundTasks,
    doc: dict = Depends(require_assessment),
) -> dict:
    """Schedule best-effort prefetch of the next question. Always fast.

    Called by the client after receiving a question via the stream endpoint
    (which cannot schedule background work mid-stream). Safe to call any
    time: the task self-guards and the live path covers any miss.
    """
    iv = doc.get("interview") or {}
    if iv.get("status") not in ("active", "followup"):
        return {"scheduled": False}
    if iv.get("current") is None or iv.get("prefetch") is not None:
        return {"scheduled": False}
    current = iv.get("current") or {}
    if (current.get("probe") or "") == "inline":
        return {"scheduled": False}
    background.add_task(_prefetch_task, doc["_id"], len(iv.get("turns", [])), current.get("turn"))
    return {"scheduled": True}


@router.get("/{assessment_id}/interview/next", response_model=InterviewNextOut)
async def get_next(doc: dict = Depends(require_assessment)) -> InterviewNextOut:
    """Read-only resume: return the pending question, completion, or 404."""
    if doc.get("interview") is None:
        raise HTTPException(status_code=404, detail="interview not started")
    return _next_out(doc)


@router.get("/{assessment_id}/interview/assessment", response_model=InterviewAssessmentOut)
async def get_assessment(
    background: BackgroundTasks, doc: dict = Depends(require_assessment)
) -> InterviewAssessmentOut:
    """Poll the batch assessment: status assessing -> followup|complete.

    If the assessment job never ran for the current turns (crash before the
    background task), this endpoint triggers it idempotently; the atomic
    claim inside the job prevents double runs.
    """
    from datetime import timedelta

    iv = doc.get("interview")
    if iv is None:
        raise HTTPException(status_code=404, detail="interview not started")
    status = iv.get("status", "active")
    if status in ("assessing", "processing"):
        stale = iv.get("updated_at")
        if isinstance(stale, datetime) and stale.tzinfo is None:
            stale = stale.replace(tzinfo=timezone.utc)
        is_stale = (
            status == "processing"
            and isinstance(stale, datetime)
            and (datetime.now(timezone.utc) - stale) > timedelta(minutes=5)
        )
        if status == "assessing" or is_stale:
            if is_stale:
                await get_db()["assessments"].find_one_and_update(
                    {"_id": doc["_id"]},
                    {"$set": {"interview.status": "assessing", "interview.updated_at": _now()}},
                )
            if iv.get("assessed_turns", 0) != len(iv.get("turns", [])):
                background.add_task(run_round_assessment, get_db(), doc["_id"], _phrase_for_job)
    fresh = await get_db()["assessments"].find_one({"_id": doc["_id"]})
    assert fresh is not None
    fiv = fresh.get("interview") or {}
    summary = fiv.get("assessment") or {}
    current = fiv.get("current")
    followups = fiv.get("followups") or []
    done = sum(1 for t in fiv.get("turns", []) if (t.get("probe") or "") == "followup")
    prog = fiv.get("assess_progress") or {}
    return InterviewAssessmentOut(
        assessment_id=doc["_id"],
        status=fiv.get("status", "active"),
        error=fiv.get("assessing_error"),
        question=_question_out(current) if current and fiv.get("status") == "followup" else None,
        followups_total=len(followups),
        followups_done=min(done, len(followups)),
        coverage=summary.get("coverage", []),
        tensions=summary.get("tensions", []),
        extracted=int(prog.get("done", 0) or 0),
        extract_total=int(prog.get("total", 0) or 0),
    )


@router.get("/{assessment_id}/interview/report", response_model=InterviewBriefingOut)
async def get_interview_report(doc: dict = Depends(require_assessment)) -> InterviewBriefingOut:
    report = (
        await get_db()["reports"]
        .find({"assessment_id": doc["_id"], "kind": "interview"})
        .sort("report_version", -1)
        .limit(1)
        .to_list(1)
    )
    if not report:
        raise HTTPException(status_code=404, detail="interview briefing not found")
    content = {
        k: v
        for k, v in report[0]["content"].items()
        if k not in ("assessment_id", "report_version")
    }
    return InterviewBriefingOut(
        assessment_id=doc["_id"],
        report_version=report[0]["report_version"],
        **content,
    )


@router.get("/{assessment_id}/interview/transcript", response_model=TranscriptOut)
async def get_transcript(doc: dict = Depends(require_assessment)) -> TranscriptOut:
    """Read-only verbatim transcript with stable segment IDs. 404 until start."""
    t = await get_db()["transcripts"].find_one({"_id": doc["_id"]})
    if t is None:
        raise HTTPException(status_code=404, detail="transcript not found")
    return TranscriptOut(
        assessment_id=doc["_id"],
        skill_version=t.get("skill_version", ""),
        topic_version=t.get("topic_version", ""),
        segments=t.get("segments", []),
        lines=t.get("lines", 0),
    )


@router.get("/{assessment_id}/interview/evidence", response_model=EvidenceOut)
async def get_evidence(doc: dict = Depends(require_assessment)) -> EvidenceOut:
    """Read-only versioned evidence per turn. Empty turns list before any answer."""
    docs = (
        await get_db()["evidence"]
        .find({"assessment_id": doc["_id"]})
        .sort("turn", 1)
        .to_list(100)
    )
    turns = []
    for d in docs:
        latest = d["versions"][-1]
        turns.append(
            EvidenceTurnOut(
                turn=d["turn"],
                status=d.get("status", "complete"),
                version=latest["version"],
                taxonomy_version=latest["taxonomy_version"],
                extractor=latest["extractor"],
                observations=latest["observations"],
                coverage=latest["coverage"],
            )
        )
    return EvidenceOut(assessment_id=doc["_id"], turns=turns)
