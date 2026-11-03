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


class InterviewCorrectRequest(BaseModel):
    """WS5 "Fix my last answer": append a correction to the latest turn.

    The original answer is never edited; the correction is stored as an
    addendum (transcript C-segments + turn.correction) and re-extracted.
    Only the most recently answered turn can be corrected, and only while
    its follow-up question is still pending.
    """

    corrects_turn: int = Field(ge=1)
    answer_text: str = Field(min_length=1, max_length=2000)
    base_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)


class InterviewCorrectResult(BaseModel):
    assessment_id: str
    version: int
    corrects_turn: int
    replayed: bool = False


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
    # WS5 in-loop fix (answer-level) and WS1 review correction
    # (observation-level) are stored separately and shown alongside the
    # untouched original note and quote.
    user_correction: str = ""
    user_corrected_at: datetime | None = None
    obs_index: int = 0


class BriefingTopicTurn(BaseModel):
    turn: int
    question: str
    answer: str
    # WS5 user correction addendum (original answer untouched).
    correction: str | None = None
    observations: list[BriefingTopicObservation] = Field(default_factory=list)


class BriefingTopic(BaseModel):
    objective: str
    title: str
    status: str
    label: str = ""
    note: str
    # WS2-B dimension line (e.g. example/frequency/timeframe/setting); empty
    # until populated, rendered only when present.
    coverage_detail: str = ""
    turns: list[BriefingTopicTurn] = Field(default_factory=list)


class BriefingFrontQuote(BaseModel):
    """One front-sheet evidence card: an exact stored quote with its anchor."""

    turn: int
    objective: str
    title: str
    assertion: str = ""
    quote: str
    segment_id: str
    line: int | None = None
    period: str = ""
    review_status: str = "pending"
    review_note: str = ""
    obs_index: int = 0
    # WS1: the user's own correction of this observation ("this isn't what
    # I meant"). Original note and quote untouched; both shown.
    user_correction: str = ""


class BriefingOpenArea(BaseModel):
    """One 'worth exploring together' item: a gap, an uncertainty, or an
    unresolved tension, phrased as an open area rather than a finding."""

    kind: str
    ref: str
    title: str
    text: str


class BriefingFrontSheet(BaseModel):
    """One-page front sheet assembled from stored evidence only."""

    why: list[BriefingFrontQuote] = Field(default_factory=list)
    timeline: list[BriefingFrontQuote] = Field(default_factory=list)
    impact: list[BriefingFrontQuote] = Field(default_factory=list)
    context: list[BriefingFrontQuote] = Field(default_factory=list)
    open_areas: list[BriefingOpenArea] = Field(default_factory=list)


class ReviewObservationOut(BaseModel):
    turn: int
    obs_index: int
    assertion: str
    quote: str
    segment_id: str
    line: int | None = None
    note: str = ""
    user_correction: str = ""


class ReviewTopicOut(BaseModel):
    objective: str
    title: str
    status: str
    label: str = ""
    note: str = ""
    observations: list[ReviewObservationOut] = Field(default_factory=list)


class InterviewReviewOut(BaseModel):
    """WS1 review-step state: what the user checks before the briefing."""

    assessment_id: str
    version: int
    status: str
    mode: str = "full"
    turns_answered: int
    topics: list[ReviewTopicOut] = Field(default_factory=list)


class ReviewAddRequest(BaseModel):
    """WS1 per-topic (or global) addition: free text stored as a new verbatim
    addendum turn. Originals untouched."""

    objective: str = Field(min_length=1, max_length=64)
    answer_text: str = Field(min_length=1, max_length=2000)
    base_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ReviewAddResult(BaseModel):
    assessment_id: str
    version: int
    turn: int
    objective: str
    replayed: bool = False


class ReviewCorrectRequest(BaseModel):
    """WS1 per-observation correction ("this isn't what I meant")."""

    turn: int = Field(ge=1)
    obs_index: int = Field(ge=0)
    answer_text: str = Field(min_length=1, max_length=2000)
    base_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ReviewCorrectResult(BaseModel):
    assessment_id: str
    version: int
    turn: int
    obs_index: int
    replayed: bool = False


class ReviewConfirmRequest(BaseModel):
    base_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ReviewConfirmResult(BaseModel):
    assessment_id: str
    version: int
    report_version: int
    user_confirmed_at: datetime
    replayed: bool = False


class ReviewTopupOut(BaseModel):
    objective: str
    title: str
    question: str
    dimension: str = ""


class ReviewTopupsOut(BaseModel):
    assessment_id: str
    topups: list[ReviewTopupOut] = Field(default_factory=list)


class ContinueRequest(BaseModel):
    """WS2-C taster→full upgrade: resume the same assessment for the full
    interview. Full-mode users never see a downgrade offer."""

    base_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=128)


class ContinueResult(BaseModel):
    assessment_id: str
    version: int
    mode: str
    question: InterviewQuestionOut | None = None
    replayed: bool = False


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
    front_sheet: BriefingFrontSheet | None = None
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
    # WS1: set when the user confirms the review step. The briefing is never
    # generated before confirmation.
    user_confirmed_at: datetime | None = None
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
