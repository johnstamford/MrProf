"""Pydantic models for Features 2-3: assessment session, persistence, screening."""

from datetime import datetime

from pydantic import BaseModel, Field

STAGES = ("created", "screening", "interview", "complete")


class AssessmentCreateRequest(BaseModel):
    # Called "password" in the UI. Hashed with bcrypt, never stored or logged.
    password: str = Field(min_length=10, max_length=128)


class AssessmentCreated(BaseModel):
    assessment_id: str
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


class ScreeningSubmit(BaseModel):
    answers: list[str] = Field(min_length=6, max_length=6)
    base_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ScreeningResult(BaseModel):
    assessment_id: str
    version: int
    score: int
    positive: bool
    replayed: bool = False


class ScreeningOut(BaseModel):
    assessment_id: str
    version: int
    instrument: str
    scoring_method: str
    scoring_version: str
    answers: list[str]
    per_question_positive: list[bool]
    score: int
    positive: bool
    completed_at: datetime


class ScreeningAnswerSummary(BaseModel):
    n: str
    question: str
    answer: str
    counted: bool


class InterviewOffer(BaseModel):
    offered: bool
    next_stage: str
    note: str


class NextSection(BaseModel):
    intro: str
    topics: list[str]


class ScreeningReportOut(BaseModel):
    assessment_id: str
    report_version: int
    instrument: str
    scoring_method: str
    scoring_version: str
    score: int
    cutoff: int
    positive: bool
    threshold_description: str
    answers: list[ScreeningAnswerSummary]
    explanation: str
    interview_offer: InterviewOffer
    next_section: NextSection
    completed_at: datetime
