"""F11-min: reviewer annotation on stored evidence observations.

Accept/amend/reject writes only to `evidence` (review_status/review_note/
reviewed_at on the latest version's observation) and mirrors the state
into the latest stored interview briefing so the report reflects review.
Transcripts and screening answers are never touched.

Addressing: (turn, obs_index) with optimistic concurrency via
expected_version (the evidence doc version being reviewed). Repeating the
same review is a replay (replayed=True), so retries are safe.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..db import get_db
from ..models import REVIEW_ACTIONS, ReviewResult, ReviewSubmit
from .assessments import require_assessment

router = APIRouter(prefix="/assessments", tags=["review"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


_STATUS_FOR = {"accept": "accepted", "amend": "amended", "reject": "rejected"}


@router.patch(
    "/{assessment_id}/interview/evidence/{turn}/observations/{obs_index}",
    response_model=ReviewResult,
)
async def review_observation(
    assessment_id: str,
    turn: int,
    obs_index: int,
    body: ReviewSubmit,
    doc: dict = Depends(require_assessment),
) -> ReviewResult:
    action = (body.action or "").strip().lower()
    if action not in REVIEW_ACTIONS:
        raise HTTPException(status_code=422, detail=f"action must be one of {list(REVIEW_ACTIONS)}")
    note = (body.note or "").strip()
    if action == "amend" and not note:
        raise HTTPException(status_code=422, detail="amend requires a note with the amended interpretation")
    status = _STATUS_FOR[action]

    db = get_db()
    edoc = await db["evidence"].find_one({"_id": f"{doc['_id']}:turn:{turn}"})
    if edoc is None:
        raise HTTPException(status_code=404, detail="evidence for turn not found")
    versions = edoc.get("versions", [])
    if not versions:
        raise HTTPException(status_code=404, detail="evidence for turn not found")
    latest = versions[-1]
    observations = latest.get("observations", [])
    if obs_index < 0 or obs_index >= len(observations):
        raise HTTPException(status_code=404, detail="observation not found")
    if latest.get("version") != body.expected_version:
        raise HTTPException(
            status_code=409,
            detail={"error": "version_conflict", "current_version": latest.get("version")},
        )
    current = observations[obs_index]
    if current.get("review_status") == status and (current.get("review_note") or "") == note:
        return ReviewResult(
            assessment_id=doc["_id"], turn=turn, obs_index=obs_index,
            evidence_version=latest.get("version"), review_status=status, replayed=True,
        )

    now = _now()
    vi = len(versions) - 1
    result = await db["evidence"].find_one_and_update(
        {
            "_id": edoc["_id"],
            f"versions.{vi}.version": body.expected_version,
        },
        {
            "$set": {
                f"versions.{vi}.observations.{obs_index}.review_status": status,
                f"versions.{vi}.observations.{obs_index}.review_note": note,
                f"versions.{vi}.observations.{obs_index}.reviewed_at": now,
                "updated_at": now,
            }
        },
        return_document=True,
    )
    if result is None:
        current_doc = await db["evidence"].find_one({"_id": edoc["_id"]})
        latest_version = (current_doc.get("versions", [{}])[-1] or {}).get("version")
        raise HTTPException(
            status_code=409,
            detail={"error": "version_conflict", "current_version": latest_version},
        )

    # Mirror into the latest stored interview briefing (derived report only;
    # transcripts and screening are never written here).
    report = (
        await db["reports"]
        .find({"assessment_id": doc["_id"], "kind": "interview"})
        .sort("report_version", -1)
        .limit(1)
        .to_list(1)
    )
    if report:
        topics = (report[0].get("content") or {}).get("topics", [])
        for ti, topic in enumerate(topics):
            for ui, tturn in enumerate(topic.get("turns", [])):
                if tturn.get("turn") != turn:
                    continue
                for oi, obs in enumerate(tturn.get("observations", [])):
                    if obs.get("obs_index", oi) != obs_index:
                        continue
                    await db["reports"].update_one(
                        {"_id": report[0]["_id"]},
                        {
                            "$set": {
                                f"content.topics.{ti}.turns.{ui}.observations.{oi}.review_status": status,
                                f"content.topics.{ti}.turns.{ui}.observations.{oi}.review_note": note,
                                f"content.topics.{ti}.turns.{ui}.observations.{oi}.reviewed_at": now,
                            }
                        },
                    )

    return ReviewResult(
        assessment_id=doc["_id"], turn=turn, obs_index=obs_index,
        evidence_version=body.expected_version, review_status=status,
    )
