"""Pydantic models for Feature 2: assessment session and persistence."""

from datetime import datetime

from pydantic import BaseModel, Field

STAGES = ("created", "screening", "interview", "complete")


class AssessmentCreated(BaseModel):
    assessment_id: str
    access_secret: str  # returned once at creation, never stored or logged
    version: int
    stage: str
    status: str


class AssessmentOut(BaseModel):
    assessment_id: str
    version: int
    stage: str
    status: str
    created_at: datetime
    updated_at: datetime


class StageUpdate(BaseModel):
    base_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)
    stage: str


class StageUpdateResult(BaseModel):
    assessment_id: str
    version: int
    stage: str
    status: str
    replayed: bool = False
