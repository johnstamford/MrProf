"""Feature 2: assessment creation, resume, and version-checked stage updates."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pymongo.errors import DuplicateKeyError

from ..auth import ID_ATTEMPTS, hash_secret, new_assessment_id, verify_secret
from ..consent import CONSENT_VERSION
from ..db import get_db
from ..models import (
    STAGES,
    AssessmentCreateRequest,
    AssessmentCreated,
    AssessmentOut,
    DeleteResult,
    StageUpdate,
    StageUpdateResult,
)
from ..opening import check_invite, consent_required

router = APIRouter(prefix="/assessments", tags=["assessments"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def require_assessment(
    assessment_id: str,
    authorization: str | None = Header(default=None),
) -> dict:
    """ID is lookup only; the Bearer secret authorizes. Unknown ID -> 404,
    wrong/missing secret -> 401. The secret hash never leaves the database."""
    doc = await get_db()["assessments"].find_one({"_id": assessment_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="not found")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="unauthorized")
    if not verify_secret(authorization[len("Bearer "):], doc["secret_hash"]):
        raise HTTPException(status_code=401, detail="unauthorized")
    return doc


@router.post("", response_model=AssessmentCreated, status_code=201)
async def create_assessment(body: AssessmentCreateRequest) -> AssessmentCreated:
    if not check_invite(body.invite_code):
        raise HTTPException(status_code=403, detail={"error": "invite_required"})
    if consent_required() and (
        not body.consent_accepted or body.consent_version != CONSENT_VERSION
    ):
        raise HTTPException(
            status_code=422,
            detail={"error": "consent_required", "consent_version": CONSENT_VERSION},
        )
    for _ in range(ID_ATTEMPTS):
        assessment_id = new_assessment_id()
        now = _now()
        try:
            await get_db()["assessments"].insert_one(
                {
                    "_id": assessment_id,
                    "secret_hash": hash_secret(body.password),
                    "version": 1,
                    "stage": "created",
                    "status": "in_progress",
                    "consent": (
                        {"version": body.consent_version, "accepted_at": now}
                        if body.consent_accepted
                        else None
                    ),
                    "idem": [],
                    "created_at": now,
                    "updated_at": now,
                }
            )
            return AssessmentCreated(
                assessment_id=assessment_id,
                version=1,
                stage="created",
                status="in_progress",
                consent_version=body.consent_version if body.consent_accepted else "",
            )
        except DuplicateKeyError:
            continue
    raise HTTPException(status_code=500, detail="could not allocate assessment id")


@router.get("/{assessment_id}", response_model=AssessmentOut)
async def get_assessment(doc: dict = Depends(require_assessment)) -> AssessmentOut:
    return AssessmentOut(
        assessment_id=doc["_id"],
        version=doc["version"],
        stage=doc["stage"],
        status=doc["status"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


@router.delete("/{assessment_id}", response_model=DeleteResult)
async def delete_assessment(doc: dict = Depends(require_assessment)) -> DeleteResult:
    """F13-min manual deletion: assessment + all linked records.

    Requires the assessment Bearer secret (same authorization as every
    answer/report/review endpoint). Removes the assessment doc, the
    transcript doc, all evidence docs, and all reports. A second call
    finds nothing and returns 404 via require_assessment.
    """
    db = get_db()
    aid = doc["_id"]
    evidence = await db["evidence"].delete_many({"assessment_id": aid})
    reports = await db["reports"].delete_many({"assessment_id": aid})
    transcript = await db["transcripts"].delete_one({"_id": aid})
    assessment = await db["assessments"].delete_one({"_id": aid})
    return DeleteResult(
        assessment_id=aid,
        deleted={
            "assessments": assessment.deleted_count,
            "transcripts": transcript.deleted_count,
            "evidence": evidence.deleted_count,
            "reports": reports.deleted_count,
        },
    )


@router.patch("/{assessment_id}/stage", response_model=StageUpdateResult)
async def update_stage(
    body: StageUpdate,
    doc: dict = Depends(require_assessment),
) -> StageUpdateResult:
    """Optimistic concurrency + idempotency in one atomic update.

    - Filter matches only the exact base_version and only if this
      idempotency_key was never applied: retries/double-clicks cannot
      duplicate the transition.
    - Replay: same key seen before -> return the stored result, no new write.
    - Otherwise the version moved on -> 409 with current state.
    """
    if body.stage not in STAGES:
        raise HTTPException(status_code=422, detail=f"stage must be one of {STAGES}")
    status = "complete" if body.stage == "complete" else doc["status"]
    col = get_db()["assessments"]
    now = _now()
    result = await col.find_one_and_update(
        {
            "_id": doc["_id"],
            "version": body.base_version,
            "idem.key": {"$ne": body.idempotency_key},
        },
        {
            "$set": {"stage": body.stage, "status": status, "version": body.base_version + 1, "updated_at": now},
            "$push": {
                "idem": {
                    "key": body.idempotency_key,
                    "version": body.base_version + 1,
                    "stage": body.stage,
                }
            },
        },
        return_document=True,
    )
    if result is not None:
        return StageUpdateResult(
            assessment_id=result["_id"], version=result["version"], stage=result["stage"], status=result["status"]
        )
    current = await col.find_one({"_id": doc["_id"]})
    assert current is not None
    for entry in current.get("idem", []):
        if entry["key"] == body.idempotency_key:
            return StageUpdateResult(
                assessment_id=current["_id"],
                version=entry["version"],
                stage=entry["stage"],
                status=current["status"],
                replayed=True,
            )
    raise HTTPException(
        status_code=409,
        detail={
            "error": "version_conflict",
            "current_version": current["version"],
            "current_stage": current["stage"],
        },
    )
