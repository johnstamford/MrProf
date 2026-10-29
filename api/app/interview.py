"""Deterministic interview planner (v0.4 topics, Feature 9 rework).

Two-phase flow with bounded inline probes. Round 1 asks every objective
once in fixed order — a pure conversation with no analysis and no evidence
written — plus at most INLINE_PROBE_BUDGET immediate same-objective probes
for thin answers (short, not denials, not uncertainty). A batch assessment
job then extracts evidence, links tension, and queues bounded follow-ups.
Round 2 works through that queue; a second batch run finalizes.

The LLM only phrases questions — it never plans, scores, or diagnoses.
Topics are explicitly NOT clinically reviewed.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

SKILL_VERSION = "skill-v0.4-draft"
TOPIC_VERSION = "topics-v0.4-draft"
TOPICS_FILE = "v0.4.yaml"

# Round 1 asks every objective once, in fixed order.
PLAN_ORDER = (
    "attention-focus",
    "organization",
    "task-completion",
    "forgetfulness",
    "restlessness",
    "impulsivity",
    "childhood-onset",
    "persistence-course",
    "settings",
    "impact-work",
    "impact-relationships",
    "context-factors",
    "strategies",
    "background-goals",
)
ROUND1_TURNS = len(PLAN_ORDER)
# Round 2 works a bounded follow-up queue set by the batch assessment.
MAX_FOLLOWUPS = 6
# Thin answers (short, not a denial, not uncertainty) get one immediate
# same-objective probe in round 1 — struck while the context is fresh.
# Denials and uncertainty are complete answers and are never probed.
INLINE_PROBE_BUDGET = 3
MAX_TURNS = ROUND1_TURNS + INLINE_PROBE_BUDGET + MAX_FOLLOWUPS
HARD_TURN_CAP = 30
ANSWER_MIN_LEN = 1
ANSWER_MAX_LEN = 2000

# Answers shorter than this get a gentle in-question invite for a concrete
# detail. Genuine denials and stated uncertainty are exempt — they are
# complete answers and must never be pressured for more. Phrasing guidance
# only; round 1 records nothing but the transcript.
SHORT_ANSWER_LEN = 20
_DENIAL_RE = re.compile(r"^(no|nope|never|none|nothing|not really)\b", re.IGNORECASE)
_DENIAL_PHRASES = (
    "never a problem",
    "never been a problem",
    "no issues",
    "no issue",
    "no problem",
    "not an issue",
    "not really an issue",
    "no difficulty",
    "never had that problem",
)
_UNCERTAIN_RE = re.compile(
    r"(don't know|do not know|can't remember|cannot remember|not sure|unsure"
    r"|dunno|no idea|can't recall|cannot recall)",
    re.IGNORECASE,
)

# Families group objectives for tension detection (present-like and
# denial-like answers about the same area) and coverage reporting.
FAMILIES: dict[str, tuple[str, ...]] = {
    "functioning": (
        "attention-focus",
        "organization",
        "task-completion",
        "forgetfulness",
        "restlessness",
        "impulsivity",
    ),
    "course": ("childhood-onset", "persistence-course"),
    "impact": ("settings", "impact-work", "impact-relationships"),
    "context": ("context-factors", "strategies", "background-goals"),
}


@lru_cache(maxsize=1)
def load_skill() -> str:
    path = Path(__file__).parent / "skills" / "SKILL.md"
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_topics() -> dict:
    """Parse the topics YAML with a minimal subset parser (no new dependency).

    Supported shape only: `key: value` lines, `  - id: ...` items, and
    `    key: value` fields. Anything richer raises loudly rather than
    silently misplanning.
    """
    path = Path(__file__).parent / "topics" / TOPICS_FILE
    ordered: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- id:"):
            current = {"id": s.split(":", 1)[1].strip()}
            ordered[current["id"]] = current
        elif current is not None and ":" in s and not s.startswith("-"):
            k, _, v = s.partition(":")
            current[k.strip()] = v.strip().strip('"')
    if tuple(ordered) != PLAN_ORDER:
        raise RuntimeError(f"topics file {TOPICS_FILE} order mismatch: {tuple(ordered)}")
    for oid in PLAN_ORDER:
        if not ordered[oid].get("opener"):
            raise RuntimeError(f"topic {oid} has no opener")
    return ordered


def fallback_question(objective: str) -> str:
    return load_topics()[objective]["opener"]


def polarity(answer: str | None) -> str:
    """Classify an answer's polarity for stop rules and tension detection.

    Returns one of: present-like, denial-like, uncertain-like, thin, empty.
    Heuristic and draft-only; the extractor remains the source of truth for
    stored evidence assertions.
    """
    if not answer:
        return "empty"
    text = answer.strip()
    if not text:
        return "empty"
    lowered = text.lower()
    if _UNCERTAIN_RE.search(text):
        return "uncertain-like"
    if _DENIAL_RE.match(text) or any(p in lowered for p in _DENIAL_PHRASES):
        return "denial-like"
    if len(text) < SHORT_ANSWER_LEN:
        return "thin"
    return "present-like"


def _needs_detail_invite(last_answer: str | None) -> bool:
    """True when the last answer is so short it cannot support a briefing.

    Genuine denials and stated uncertainty are exempt: they are complete
    answers and must never be pressured for more.
    """
    return polarity(last_answer) == "thin"


def family_tensions(turns: list[dict]) -> list[dict]:
    """Detect families with both present-like and denial-like answers.

    Returns [{family, present_turn, denial_turn}] in fixed family order.
    Pure polarity heuristic used by the batch assessment; contradiction
    judgment stays with the clinician.
    """
    tensions: list[dict] = []
    for family, members in FAMILIES.items():
        present_turn: int | None = None
        denial_turn: int | None = None
        for t in turns:
            if t.get("objective") not in members:
                continue
            pol = polarity(t.get("answer"))
            if pol == "present-like" and present_turn is None:
                present_turn = t.get("turn")
            elif pol == "denial-like" and denial_turn is None:
                denial_turn = t.get("turn")
        if present_turn is not None and denial_turn is not None:
            tensions.append(
                {"family": family, "present_turn": present_turn, "denial_turn": denial_turn}
            )
    return tensions


def plan_next(
    turns: list[dict], followups: list[dict] | None = None
) -> tuple[str, str, bool, dict | None]:
    """Return (objective_id, reason, complete, hint). Pure function of turns.

    Round 1 asks every objective once in fixed order, plus at most
    INLINE_PROBE_BUDGET immediate same-objective probes for thin answers
    (short, not a denial, not uncertainty — one probe per objective).
    Round 2 works through the follow-up queue set by the batch assessment
    (each item: objective, reason, optional tension). hint carries tension
    text for neutral clarification phrasing, {"kind": "inline"} for an
    inline probe, else None. Probe decisions are deterministic code over
    the turns (including answer text for the thin check only); the model
    only phrases.
    """
    followups = followups or []
    n = len(turns)
    if n >= MAX_TURNS:
        return "", f"interview complete at cap ({n} answered turns)", True, None
    if not followups and turns:
        last = turns[-1]
        if polarity(last.get("answer")) == "thin":
            used = sum(1 for t in turns if (t.get("probe") or "") == "inline")
            probed = {t["objective"] for t in turns if (t.get("probe") or "") == "inline"}
            if last["objective"] not in probed and used < INLINE_PROBE_BUDGET:
                title = load_topics()[last["objective"]].get("title", last["objective"])
                return (
                    last["objective"],
                    f"invite one concrete detail about {title} ({last['objective']}), once, no pressure",
                    False,
                    {"kind": "inline"},
                )
    asked = [t["objective"] for t in turns]
    unasked = [o for o in PLAN_ORDER if o not in asked]
    if unasked:
        obj = unasked[0]
        title = load_topics()[obj].get("title", obj)
        return obj, f"cover {title} ({obj}) in fixed order", False, None
    consumed = sum(1 for t in turns if (t.get("probe") or "") == "followup")
    if consumed < len(followups):
        item = followups[consumed]
        hint = {"kind": "followup", "tension": item.get("tension")} if item.get("tension") else {"kind": "followup"}
        return item["objective"], item["reason"], False, hint
    return "", f"all objectives and {len(followups)} follow-ups explored after {n} answered turns", True, None


def coverage_summary(turns: list[dict]) -> list[dict]:
    """Per-objective coverage for the briefing: one entry per PLAN_ORDER item."""
    by_objective: dict[str, list[dict]] = {}
    for t in turns:
        by_objective.setdefault(t["objective"], []).append(t)
    topics = load_topics()
    summary: list[dict] = []
    for oid in PLAN_ORDER:
        answered = by_objective.get(oid, [])
        if not answered:
            summary.append(
                {
                    "objective": oid,
                    "title": topics[oid].get("title", oid),
                    "status": "unasked",
                    "turns": [],
                    "note": "not reached within the turn budget",
                }
            )
            continue
        pols = [polarity(t.get("answer")) for t in answered]
        turn_nos = [t["turn"] for t in answered]
        if any(p == "present-like" for p in pols):
            status, note = "covered", "substantive account recorded"
        elif any(p == "denial-like" for p in pols):
            status, note = "denied", "difficulty denied; accepted as reported"
        elif any(p == "uncertain-like" for p in pols):
            status, note = "unable", "could not recall or say; not pressed further"
        else:
            status, note = "thin", "only brief answers recorded; limited evidence"
        summary.append(
            {
                "objective": oid,
                "title": topics[oid].get("title", oid),
                "status": status,
                "turns": turn_nos,
                "note": note,
            }
        )
    return summary


def build_prompt(
    *,
    objective: str,
    reason: str,  # noqa: ARG001 - kept for explicit logging parity
    history: list[dict],
    screening: dict | None,
    last_answer: str | None = None,
    tension: str | None = None,
) -> list[str]:
    lines = [
        f"Assigned objective: {objective}. Ask ONE question for this objective only.",
    ]
    if screening:
        lines.append(
            "Screening context (do not repeat these questions): "
            f"instrument={screening.get('instrument')}, score={screening.get('score')}, "
            f"positive={screening.get('positive')}, "
            f"answers={','.join(screening.get('answers', []))}."
        )
    else:
        lines.append("No screening context available.")
    if history:
        lines.append("Conversation so far:")
        for t in history[-6:]:
            lines.append(f"Q{t.get('turn')}: {t.get('question', '')}")
            lines.append(f"A{t.get('turn')}: {t.get('answer', '')[:300]}")
    else:
        lines.append("This is the first question.")
    if tension:
        lines.append(
            "Earlier answers seem in tension: "
            + tension
            + ". Ask one neutral question to understand both sides. "
            "Do not accuse, do not assume error, and accept either account as reported."
        )
    elif _needs_detail_invite(last_answer):
        lines.append(
            "The previous answer was very brief. Invite one concrete detail or "
            "example for this objective, once, without pressuring. A short question "
            "add-on is enough; do not lecture about answer length."
        )
    lines.append('Reply with JSON ONLY: {"question_text","objective","reason"}.')
    return lines
