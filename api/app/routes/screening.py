"""Feature 3: ASRS v1.1 6Q screening submission, resume, idempotent versioned writes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..asrs import (
    INSTRUMENT,
    SCORING_METHOD,
    SCORING_VERSION,
    score_answers,
)
from ..db import get_db
from ..models import ScreeningOut, ScreeningReportOut, ScreeningResult, ScreeningSubmit
from ..reports import build_screening_report
from .assessments import require_assessment

router = APIRouter(prefix="/assessments", tags=["screening"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _screening_out(assessment_id: str, version: int, screening: dict) -> ScreeningOut:
    return ScreeningOut(
        assessment_id=assessment_id,
        version=version,
        instrument=screening["instrument"],
        scoring_method=screening["scoring_method"],
        scoring_version=screening["scoring_version"],
        answers=screening["answers"],
        per_question_positive=screening["per_question_positive"],
        score=screening["score"],
        positive=screening["positive"],
        completed_at=screening["completed_at"],
    )


@router.post("/{assessment_id}/screening", response_model=ScreeningResult)
async def submit_screening(
    assessment_id: str,
    body: ScreeningSubmit,
    doc: dict = Depends(require_assessment),
) -> ScreeningResult:
    """Validate 6 answers, score deterministically in code, persist atomically.

    Idempotency + optimistic concurrency mirror the stage endpoint: the write
    matches only the exact base_version and only if this idempotency_key was
    never applied. Replays return the stored result; stale versions get a 409.
    """
    try:
        score, positive, flags = score_answers(list(body.answers))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    normalized = [a.strip().lower().replace("-", " ").replace("_", " ") for a in body.answers]
    normalized = [" ".join(n.split()).replace(" ", "_") for n in normalized]

    col = get_db()["assessments"]
    now = _now()
    screening_doc = {
        "instrument": INSTRUMENT,
        "scoring_method": SCORING_METHOD,
        "scoring_version": SCORING_VERSION,
        "answers": normalized,
        "per_question_positive": flags,
        "score": score,
        "positive": positive,
        "completed_at": now,
        "idem_key": body.idempotency_key,
    }
    result = await col.find_one_and_update(
        {
            "_id": doc["_id"],
            "version": body.base_version,
            "idem.key": {"$ne": body.idempotency_key},
            "screening.idem_key": {"$ne": body.idempotency_key},
        },
        {
            "$set": {
                "screening": screening_doc,
                "version": body.base_version + 1,
                "updated_at": now,
            },
            "$push": {
                "idem": {
                    "key": body.idempotency_key,
                    "version": body.base_version + 1,
                    "kind": "screening",
                }
            },
        },
        return_document=True,
    )
    if result is not None:
        content = build_screening_report(screening_doc)
        reports = get_db()["reports"]
        prior = await reports.count_documents({"assessment_id": doc["_id"], "kind": "screening"})
        await reports.insert_one(
            {
                "assessment_id": doc["_id"],
                "kind": "screening",
                "report_version": prior + 1,
                "screening_idem_key": body.idempotency_key,
                "content": {**content, "completed_at": now},
                "created_at": now,
            }
        )
        return ScreeningResult(
            assessment_id=result["_id"], version=result["version"], score=score, positive=positive
        )
    current = await col.find_one({"_id": doc["_id"]})
    assert current is not None
    existing = current.get("screening")
    if existing is not None and existing.get("idem_key") == body.idempotency_key:
        stored_version = current["version"]
        for entry in current.get("idem", []):
            if entry["key"] == body.idempotency_key:
                stored_version = entry["version"]
                break
        return ScreeningResult(
            assessment_id=current["_id"],
            version=stored_version,
            score=existing["score"],
            positive=existing["positive"],
            replayed=True,
        )
    for entry in current.get("idem", []):
        if entry["key"] == body.idempotency_key:
            return ScreeningResult(
                assessment_id=current["_id"],
                version=entry["version"],
                score=(existing or {}).get("score", 0),
                positive=(existing or {}).get("positive", False),
                replayed=True,
            )
    raise HTTPException(
        status_code=409,
        detail={
            "error": "version_conflict",
            "current_version": current["version"],
        },
    )


@router.get("/{assessment_id}/screening/report", response_model=ScreeningReportOut)
async def get_screening_report(doc: dict = Depends(require_assessment)) -> ScreeningReportOut:
    report = (
        await get_db()["reports"]
        .find({"assessment_id": doc["_id"], "kind": "screening"})
        .sort("report_version", -1)
        .limit(1)
        .to_list(1)
    )
    if not report:
        raise HTTPException(status_code=404, detail="screening report not found")
    content = report[0]["content"]
    return ScreeningReportOut(
        assessment_id=doc["_id"],
        report_version=report[0]["report_version"],
        **content,
    )


@router.get("/{assessment_id}/screening", response_model=ScreeningOut)
async def get_screening(doc: dict = Depends(require_assessment)) -> ScreeningOut:
    screening = doc.get("screening")
    if screening is None:
        raise HTTPException(status_code=404, detail="screening not found")
    return _screening_out(doc["_id"], doc["version"], screening)
