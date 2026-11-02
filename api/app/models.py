"""Pydantic models for Features 2-3: assessment session, persistence, screening."""

from datetime import datetime

from pydantic import BaseModel, Field

STAGES = ("created", "screening", "interview", "complete")


class AssessmentCreateRequest(BaseModel):
    # Called "password" in the UI. Hashed with bcrypt, never stored or logged.
    password: str = Field(min_length=10, max_length=128)
    # F13-min opening gates: invite code (required only when the server
    # configures PUBLIC_INVITE_CODE) + explicit consent record.
    invite_code: str = Field(default="", max_length=128)
    consent_accepted: bool = False
    consent_version: str = Field(default="", max_length=64)


class AssessmentCreated(BaseModel):
    assessment_id: str
    version: int
    stage: str
    status: str
    consent_version: str = ""


class AssessmentOut(BaseModel):
    assessment_id: str
    version: int
    stage: str
    status: str
    created_at: datetime
    updated_at: datetime


class DeleteResult(BaseModel):
    assessment_id: str
    deleted: dict[str, int]


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


class InterviewStartRequest(BaseModel):
    base_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)
    # F10a taster flag: "full" (14 objectives) or "taster" (~6). Not a fork.
    mode: str = Field(default="full", max_length=16)


class InterviewAnswerRequest(BaseModel):
    answer_text: str = Field(min_length=1, max_length=2000)
    base_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)


class InterviewQuestionOut(BaseModel):
    turn: int
    objective: str
    reason: str
    text: str
    model_provider: str
    model_name: str
    skill_version: str
    topic_version: str
    # Supportive effort banner (frontend-rendered) after repeated thin
    # answers. Never set for denials/uncertainty; at most once per round.
    effort_nudge: bool = False


class InterviewStartResult(BaseModel):
    assessment_id: str
    version: int
    stage: str
    status: str
    question: InterviewQuestionOut
    replayed: bool = False
    mode: str = "full"


class InterviewAnswerResult(BaseModel):
    assessment_id: str
    version: int
    turn_answered: int
    status: str
    question: InterviewQuestionOut | None = None
    completed: bool = False
    replayed: bool = False
    mode: str = "full"


class InterviewNextOut(BaseModel):
    assessment_id: str
    version: int
    status: str
    turns_answered: int
    question: InterviewQuestionOut | None = None
    completed: bool = False
    mode: str = "full"


class BriefingStatement(BaseModel):
    turn: int
    question: str
    answer: str


class BriefingSystemNote(BaseModel):
    turn: int
    objective: str
    reason: str
    model_provider: str
    model_name: str


class BriefingGap(BaseModel):
    area: str
    status: str


class BriefingCoverage(BaseModel):
    objective: str
    title: str
    status: str
    turns: list[int]
    note: str


class BriefingContradiction(BaseModel):
    family: str
    areas: list[str] = Field(default_factory=list)
    present_turn: int
    denial_turn: int
    clarified: bool = False
    note: str = ""


class TranscriptSegment(BaseModel):
    id: str
    turn: int
    role: str
    n: int
    text: str
    line: int


class BriefingTopicObservation(BaseModel):
    assertion: str
    quote: str
    segment_id: str
    line: int | None = None
    # Extractor's one-sentence explainer: what the quote shows about this
    # topic. System interpretation, not a quote; never a finding.
    note: str = ""
    criterion_links: list[dict] = Field(default_factory=list)
    review_status: str = "pending"
    review_note: str = ""
    reviewed_at: datetime | None = None
    obs_index: int = 0


class BriefingTopicTurn(BaseModel):
    turn: int
    question: str
    answer: str
    observations: list[BriefingTopicObservation] = Field(default_factory=list)


class BriefingTopic(BaseModel):
    objective: str
    title: str
    status: str
    label: str = ""
    note: str
    turns: list[BriefingTopicTurn] = Field(default_factory=list)


class BriefingArea(BaseModel):
    """Section-1/2 area rollup: headline status plus honest per-status counts."""

    key: str
    title: str
    status: str
    label: str = ""
    counts: dict[str, int] = Field(default_factory=dict)
    objectives: list[str] = Field(default_factory=list)


class BriefingScreeningSnapshot(BaseModel):
    """Screening score carried into the interview briefing summary."""

    score: int | None = None
    scoring_method: str = "original-0-6"
    positive: bool | None = None
    completed_at: datetime | None = None


class BriefingDetailSummary(BaseModel):
    level_counts: list[int] = Field(default_factory=lambda: [0, 0, 0, 0])
    grounded_turns: int = 0
    total_turns: int = 0


class BriefingLatencySummary(BaseModel):
    """Server-side question-phrasing latency (ms). Think-time excluded."""

    count: int = 0
    p50_ms: float = 0
    p95_ms: float = 0
    max_ms: float = 0


class InterviewBriefingOut(BaseModel):
    assessment_id: str
    report_version: int
    kind: str
    skill_version: str
    topic_version: str
    banner: str
    completion_note: str
    turns_answered: int
    screening: BriefingScreeningSnapshot | None = None
    areas: list[BriefingArea] = Field(default_factory=list)
    topics: list[BriefingTopic] = Field(default_factory=list)
    statements: list[BriefingStatement]
    system_notes: list[BriefingSystemNote]
    coverage: list[BriefingCoverage] = Field(default_factory=list)
    contradictions: list[BriefingContradiction] = Field(default_factory=list)
    gaps: list[BriefingGap]
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    detail_summary: BriefingDetailSummary = Field(default_factory=BriefingDetailSummary)
    latency_summary: BriefingLatencySummary = Field(default_factory=BriefingLatencySummary)
    support_note: str = ""
    mode: str = "full"
    completed_at: datetime


class InterviewAssessmentOut(BaseModel):
    assessment_id: str
    status: str
    error: str | None = None
    question: InterviewQuestionOut | None = None
    followups_total: int = 0
    followups_done: int = 0
    coverage: list[BriefingCoverage] = Field(default_factory=list)
    tensions: list[BriefingContradiction] = Field(default_factory=list)
    extracted: int = 0
    extract_total: int = 0


class TranscriptOut(BaseModel):
    assessment_id: str
    skill_version: str
    topic_version: str
    segments: list[TranscriptSegment]
    lines: int


class EvidenceObservationOut(BaseModel):
    code: str
    assertion: str
    segment_id: str
    quote: str
    period: str = ""
    setting: str = ""
    frequency: str = ""
    note: str = ""
    criterion_links: list[dict] = Field(default_factory=list)
    links: list[dict] = Field(default_factory=list)
    review_status: str = "pending"
    review_note: str = ""
    reviewed_at: datetime | None = None
    obs_index: int = 0


class EvidenceTurnOut(BaseModel):
    turn: int
    status: str
    version: int
    taxonomy_version: str
    extractor: dict
    observations: list[EvidenceObservationOut]
    coverage: dict


class EvidenceOut(BaseModel):
    assessment_id: str
    turns: list[EvidenceTurnOut]


REVIEW_ACTIONS = ("accept", "amend", "reject")
REVIEW_STATUSES = ("pending", "accepted", "amended", "rejected")


class ReviewSubmit(BaseModel):
    action: str = Field(min_length=1, max_length=16)
    note: str = Field(default="", max_length=500)
    expected_version: int = Field(ge=1)


class ReviewResult(BaseModel):
    assessment_id: str
    turn: int
    obs_index: int
    evidence_version: int
    review_status: str
    replayed: bool = False
