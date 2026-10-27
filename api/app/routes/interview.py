"""Feature 5: draft-topics interview API (v0.2 DRAFT, not clinically reviewed).

Endpoints (all require the assessment Bearer secret; ID is lookup only):
  POST /assessments/{id}/interview/start   begin stub interview -> Q1
  POST /assessments/{id}/interview/answer  save answer -> next Q or complete
  GET  /assessments/{id}/interview/next    read-only resume (no version change)

Concurrency/idempotency mirror the screening endpoint: writes match only
the exact base_version with an unseen idempotency key; replays return the
stored result; otherwise 409. Model failures never write state, so a retry
with the same key is always safe.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from .. import interview as planner
from ..briefing import build_interview_briefing
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
    InterviewAnswerRequest,
    InterviewAnswerResult,
    InterviewBriefingOut,
    InterviewNextOut,
    InterviewQuestionOut,
    InterviewStartRequest,
    InterviewStartResult,
)
from .assessments import require_assessment

router = APIRouter(prefix="/assessments", tags=["interview"])


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


async def _generate(assessment_id: str, objective: str, reason: str, history: list, screening: dict | None) -> tuple:
    """Run the InterviewAgent for the planner-assigned objective."""
    cfg = load_config()
    prompt = planner.build_prompt(
        objective=objective, reason=reason, history=history, screening=screening
    )
    return await generate_next_question(
        cfg=cfg,
        instructions=planner.load_skill(),
        prompt=prompt,
        objective=objective,
        reason=reason,
        fallback_question=planner.fallback_question(objective),
        session_id=assessment_id,
    )


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
    objective, reason, _ = planner.plan_next([])
    try:
        question, model_info, session_blob = await _generate(
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
        "model_provider": pending["model_provider"],
        "model_name": pending["model_name"],
        "skill_version": pending["skill_version"],
        "topic_version": pending["topic_version"],
    }
    new_history = history + [answered_turn]
    if len(new_history) >= HARD_TURN_CAP or len(new_history) >= MAX_TURNS:
        completed, next_turn_doc = True, None
        session_blob = iv.get("session") or {"session_id": assessment_id}
    else:
        completed = False
        objective, reason, done = planner.plan_next(new_history)
        if done:
            next_turn_doc = None
            completed = True
            session_blob = iv.get("session") or {"session_id": assessment_id}
        else:
            try:
                question, model_info, session_blob = await _generate(
                    assessment_id, objective, reason, new_history, doc.get("screening")
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
                "model_provider": model_info["provider"],
                "model_name": model_info["model"],
                "skill_version": SKILL_VERSION,
                "topic_version": TOPIC_VERSION,
            }
    col = get_db()["assessments"]
    now = _now()
    new_status = "complete" if completed else "active"
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
        # Versioned briefing write (replay path above never re-inserts).
        reports = get_db()["reports"]
        prior = await reports.count_documents({"assessment_id": doc["_id"], "kind": "interview"})
        content = build_interview_briefing(result["_id"], result["interview"], prior + 1, now)
        await reports.insert_one(
            {
                "assessment_id": doc["_id"],
                "kind": "interview",
                "report_version": prior + 1,
                "answer_idem_key": body.idempotency_key,
                "content": {**content, "completed_at": now},
                "created_at": now,
            }
        )
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
