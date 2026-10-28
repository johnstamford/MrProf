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
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from .. import interview as planner
from ..assessment import run_round_assessment
from ..db import get_db
from ..interview import (
    ANSWER_MAX_LEN,
    HARD_TURN_CAP,
    MAX_TURNS,
    SKILL_VERSION,
    TOPIC_VERSION,
)
from ..llm import LLMError, generate_next_question, load_config
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
    )


def _replay_result(doc: dict, key: str) -> dict | None:
    for entry in doc.get("idem", []):
        if entry["key"] == key:
            return entry
    return None


async def _generate(assessment_id: str, objective: str, reason: str, history: list, screening: dict | None, hint: dict | None = None) -> tuple:
    """Run the InterviewAgent for the planner-assigned objective.

    Returns (question, model_info, session_blob, probe) where probe is the
    deterministic marker (None, "followup", or "clarify:<family>") stored on
    the turn for stop-rule accounting.
    """
    cfg = load_config()
    last_answer = history[-1].get("answer") if history else None
    hint = hint or {}
    prompt = planner.build_prompt(
        objective=objective, reason=reason, history=history, screening=screening,
        last_answer=last_answer, tension=hint.get("tension"),
    )
    question, model_info, session_blob = await generate_next_question(
        cfg=cfg,
        instructions=planner.load_skill(),
        prompt=prompt,
        objective=objective,
        reason=reason,
        fallback_question=planner.fallback_question(objective),
        session_id=assessment_id,
    )
    kind = hint.get("kind")
    probe = f"clarify:{hint['family']}" if kind == "clarify" else (kind if kind == "followup" else None)
    return question, model_info, session_blob, probe


async def _phrase_for_job(assessment_id: str, objective: str, reason: str, history: list, screening: dict | None, tension: str | None = None) -> tuple:
    """Phrase one question for the batch job. Returns (text, model_info, session)."""
    cfg = load_config()
    last_answer = history[-1].get("answer") if history else None
    prompt = planner.build_prompt(
        objective=objective, reason=reason, history=history, screening=screening,
        last_answer=last_answer, tension=tension,
    )
    question, model_info, session_blob = await generate_next_question(
        cfg=cfg,
        instructions=planner.load_skill(),
        prompt=prompt,
        objective=objective,
        reason=reason,
        fallback_question=planner.fallback_question(objective),
        session_id=assessment_id,
    )
    return question.question_text, model_info, session_blob


@router.post("/{assessment_id}/interview/start", response_model=InterviewStartResult)
async def start_interview(
    assessment_id: str,
    body: InterviewStartRequest,
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
            )
        raise HTTPException(
            status_code=409,
            detail={"error": "interview_already_started", "current_version": doc["version"]},
        )
    objective, reason, _, _ = planner.plan_next([])
    try:
        question, model_info, session_blob, _ = await _generate(
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
            )
        raise HTTPException(
            status_code=409,
            detail={"error": "version_conflict", "current_version": current["version"]},
        )
    await append_turn_segments(
        get_db(), result["_id"], 1, turn_doc["question"], None,
        SKILL_VERSION, TOPIC_VERSION,
    )
    return InterviewStartResult(
        assessment_id=result["_id"],
        version=result["version"],
        stage=result["stage"],
        status="active",
        question=_question_out(turn_doc),
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
    answered_turn = {
        "turn": pending["turn"],
        "objective": pending["objective"],
        "reason": pending["reason"],
        "question": pending["question"],
        "answer": answer[:ANSWER_MAX_LEN],
        "answered_at": _now(),
        "probe": pending.get("probe"),
        "model_provider": pending["model_provider"],
        "model_name": pending["model_name"],
        "skill_version": pending["skill_version"],
        "topic_version": pending["topic_version"],
    }
    new_history = history + [answered_turn]
    queue = iv.get("followups") or []
    assessed_turns = iv.get("assessed_turns", 0)
    schedule_assessment = False
    if len(new_history) >= HARD_TURN_CAP or len(new_history) >= MAX_TURNS:
        completed, next_turn_doc = False, None
        session_blob = iv.get("session") or {"session_id": assessment_id}
        schedule_assessment = True
    else:
        completed = False
        objective, reason, done, hint = planner.plan_next(new_history, queue)
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
            try:
                question, model_info, session_blob, probe = await _generate(
                    assessment_id, objective, reason, new_history, doc.get("screening"),
                    hint=hint,
                )
            except LLMError as exc:
                # No write happened: the saved answer is untouched, the same
                # key can be retried safely.
                raise HTTPException(
                    status_code=exc.status, detail={"error": exc.code, "message": exc.message}
                )
            next_turn_doc = {
                "turn": pending["turn"] + 1,
                "objective": question.objective,
                "reason": question.reason,
                "question": question.question_text,
                "answer": None,
                "probe": probe,
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
    )


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
    return InterviewAssessmentOut(
        assessment_id=doc["_id"],
        status=fiv.get("status", "active"),
        error=fiv.get("assessing_error"),
        question=_question_out(current) if current and fiv.get("status") == "followup" else None,
        followups_total=len(followups),
        followups_done=min(done, len(followups)),
        coverage=summary.get("coverage", []),
        tensions=summary.get("tensions", []),
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
