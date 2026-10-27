"""Feature 2: assessment creation, resume, and version-checked stage updates."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pymongo.errors import DuplicateKeyError

from ..auth import hash_secret, new_access_secret, new_assessment_id, verify_secret
from ..db import get_db
from ..models import STAGES, AssessmentCreated, AssessmentOut, StageUpdate, StageUpdateResult

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
async def create_assessment() -> AssessmentCreated:
    for _ in range(3):  # retry on the astronomically unlikely ID collision
        assessment_id = new_assessment_id()
        secret = new_access_secret()
        now = _now()
        try:
            await get_db()["assessments"].insert_one(
                {
                    "_id": assessment_id,
                    "secret_hash": hash_secret(secret),
                    "version": 1,
                    "stage": "created",
                    "status": "in_progress",
                    "idem": [],
                    "created_at": now,
                    "updated_at": now,
                }
            )
            return AssessmentCreated(
                assessment_id=assessment_id,
                access_secret=secret,
                version=1,
                stage="created",
                status="in_progress",
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
