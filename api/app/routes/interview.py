"""Feature 7: interview API with immutable transcripts + evidence extraction.

Endpoints (all require the assessment Bearer secret; ID is lookup only):
  POST /assessments/{id}/interview/start   begin interview -> Q1
  POST /assessments/{id}/interview/answer  save answer -> extract -> next Q
  GET  /assessments/{id}/interview/next    read-only resume (no version change)
  GET  /assessments/{id}/interview/transcript  verbatim segments, read-only
  GET  /assessments/{id}/interview/evidence    versioned observations, read-only

Concurrency/idempotency mirror the screening endpoint: writes match only
the exact base_version with an unseen idempotency key; replays return the
stored result; otherwise 409. Extraction runs after the atomic turn write
and never blocks the interview loop: model failures leave the saved turn
intact with evidence pending.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from .. import interview as planner
from ..briefing import build_interview_briefing
from ..db import get_db
from ..extraction import extract_turn, upsert_evidence
from ..interview import (
    ANSWER_MAX_LEN,
    HARD_TURN_CAP,
    MAX_TURNS,
    PLAN_ORDER,
    SKILL_VERSION,
    TOPIC_VERSION,
)
from ..llm import LLMError, generate_next_question, load_config
from ..models import (
    EvidenceOut,
    EvidenceTurnOut,
    InterviewAnswerRequest,
    InterviewAnswerResult,
    InterviewBriefingOut,
    InterviewNextOut,
    InterviewQuestionOut,
    InterviewStartRequest,
    InterviewStartResult,
    TranscriptOut,
)
from ..transcripts import segment_text
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


async def _append_transcript(
    assessment_id: str, turn: int, question: str, answer: str | None
) -> list[dict]:
    """Append Q/A segments for one turn. Append-only; replays dedupe by ID.

    Returns the turn's segments for extraction. Transcript failures are
    logged, never raised — the assessment write is the source of truth.
    """
    db = get_db()
    doc = await db["transcripts"].find_one({"_id": assessment_id})
    existing = {s["id"] for s in (doc.get("segments") if doc else [])} if doc else set()
    start_line = (doc.get("lines", 0) + 1) if doc else 1
    q_segs, line = segment_text(question, turn, "Q", start_line)
    if existing and q_segs and all(s["id"] in existing for s in q_segs):
        # Question already stored (normal case: written at start). Discard the
        # re-segmentation so it cannot consume line numbers; answers continue
        # exactly where the transcript left off.
        q_segs = []
        line = start_line
    a_segs: list[dict] = []
    if answer is not None:
        a_segs, line = segment_text(answer, turn, "A", line)
    turn_segs = q_segs + a_segs
    fresh = [s for s in turn_segs if s["id"] not in existing]
    now = _now()
    try:
        if doc is None:
            await db["transcripts"].insert_one(
                {
                    "_id": assessment_id,
                    "assessment_id": assessment_id,
                    "skill_version": SKILL_VERSION,
                    "topic_version": TOPIC_VERSION,
                    "segments": fresh,
                    "lines": line - 1,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        elif fresh:
            await db["transcripts"].update_one(
                {"_id": assessment_id},
                {
                    "$push": {"segments": {"$each": fresh}},
                    "$set": {"lines": line - 1, "updated_at": now},
                },
            )
    except DuplicateKeyError:
        pass  # concurrent start won the insert; segments dedupe by ID below
    except Exception as exc:  # noqa: BLE001 - transcript is secondary to the turn write
        log.warning("transcript append failed for %s turn %d: %s", assessment_id, turn, type(exc).__name__)
    return turn_segs


async def _extract_and_store(
    assessment_id: str, answered_turn: dict, history: list[dict], turn_segs: list[dict]
) -> None:
    """Run the extractor and upsert versioned evidence. Never raises."""
    try:
        result, info = await extract_turn(
            objective=answered_turn["objective"],
            segments=turn_segs,
            answer=answered_turn["answer"] or "",
            session_id=assessment_id,
        )
    except LLMError as exc:
        log.warning(
            "extraction pending for %s turn %d: %s", assessment_id, answered_turn["turn"], exc.code
        )
        return
    except Exception as exc:  # noqa: BLE001 - extraction must not break the loop
        log.warning(
            "extraction failed for %s turn %d: %s", assessment_id, answered_turn["turn"], type(exc).__name__
        )
        return
    covered = [t["objective"] for t in history]
    gaps = [o for o in PLAN_ORDER if o not in covered]
    try:
        await upsert_evidence(
            get_db(),
            assessment_id=assessment_id,
            turn=answered_turn["turn"],
            result=result,
            info=info,
            covered=covered,
            gaps=gaps,
        )
    except Exception as exc:  # noqa: BLE001 - turn already saved; evidence stays pending
        log.warning(
            "evidence store failed for %s turn %d: %s", assessment_id, answered_turn["turn"], type(exc).__name__
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
    await _append_transcript(result["_id"], 1, turn_doc["question"], None)
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
    turn_segs = await _append_transcript(
        result["_id"], answered_turn["turn"], answered_turn["question"], answered_turn["answer"]
    )
    if next_turn_doc is not None:
        await _append_transcript(
            result["_id"], next_turn_doc["turn"], next_turn_doc["question"], None
        )
    await _extract_and_store(result["_id"], answered_turn, new_history, turn_segs)
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
