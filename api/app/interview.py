"""Deterministic interview planner (v0.3 draft topics, Feature 9).

The planner selects objectives IN CODE. The LLM only phrases the question
for the assigned objective — it never plans, scores, or diagnoses.

v0.3: fourteen experience-focused objectives covering reported behaviors,
course over time, settings, impact, context, coping, and background. Each
objective is asked once in fixed order; a bounded probe budget (follow-ups
for thin answers, neutral clarification of cross-turn tension) fills the
remaining turns up to MAX_TURNS. Topics close through substantive
evidence, clear denial, or documented inability — never through pressure.
Topics are explicitly NOT clinically reviewed.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

SKILL_VERSION = "skill-v0.3-draft"
TOPIC_VERSION = "topics-v0.3-draft"
TOPICS_FILE = "v0.3.yaml"

# Fixed opener order. Probes (follow-ups/clarifications) interleave; every
# objective is still asked at least once within the turn budget.
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
MAX_TURNS = 20
HARD_TURN_CAP = 30
ANSWER_MIN_LEN = 1
ANSWER_MAX_LEN = 2000

# Shared probe budget: follow-ups for thin answers + neutral clarifications
# of cross-turn tension. 14 openers + 6 probes = MAX_TURNS.
MAX_PROBES = 6
MAX_CLARIFICATIONS = 2

# Answers shorter than this invite one gentle follow-up for a concrete
# detail. Genuine denials and stated uncertainty are exempt — they are
# complete answers and must never be pressured for more.
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


def _probe_kind(turn: dict) -> str | None:
    """Deterministic probe marker stored on each turn (independent of the
    model-phrased reason text). One of None, "followup", "clarify:<family>"."""
    return turn.get("probe")


def _probes_used(turns: list[dict]) -> int:
    return sum(1 for t in turns if _probe_kind(t) is not None)


def _clarified_families(turns: list[dict]) -> set[str]:
    out: set[str] = set()
    for t in turns:
        probe = _probe_kind(t)
        if probe and probe.startswith("clarify:"):
            out.add(probe.split(":", 1)[1])
    return out


def family_tensions(turns: list[dict]) -> list[dict]:
    """Detect families with both present-like and denial-like answers.

    Returns [{family, present_turn, denial_turn}] in fixed family order.
    Pure polarity heuristic; contradiction judgment stays with the clinician.
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


def plan_next(turns: list[dict]) -> tuple[str, str, bool, dict | None]:
    """Return (objective_id, reason, complete, hint). Pure function of turns.

    hint is None or {"tension": ...} for neutral clarification phrasing.
    Priority: turn cap > clarification of new tension (bounded) > follow-up
    for a thin last answer (bounded) > next unasked objective > complete.
    """
    n = len(turns)
    if n >= MAX_TURNS:
        return "", f"interview complete at cap ({n} answered turns)", True, None
    asked = [t["objective"] for t in turns]
    unasked = [o for o in PLAN_ORDER if o not in asked]
    probes = _probes_used(turns)
    budget_left = MAX_PROBES - probes

    if budget_left > 0 and unasked and turns:
        clarified = _clarified_families(turns)
        clarifications = sum(1 for t in turns if (_probe_kind(t) or "").startswith("clarify:"))
        if clarifications < MAX_CLARIFICATIONS:
            for tension in family_tensions(turns):
                if tension["family"] not in clarified:
                    obj = turns[-1]["objective"]
                    reason = (
                        f"Clarify (family: {tension['family']}) tension between turn "
                        f"{tension['denial_turn']} (denied difficulty) and turn "
                        f"{tension['present_turn']} (described difficulty); one neutral "
                        f"question, accept either account"
                    )
                    hint = {
                        "kind": "clarify",
                        "family": tension["family"],
                        "tension": (
                            f"in turn {tension['denial_turn']} no difficulty was reported, "
                            f"but turn {tension['present_turn']} described difficulty"
                        ),
                    }
                    return obj, reason, False, hint
        last = turns[-1]
        if _needs_detail_invite(last.get("answer")) and asked.count(last["objective"]) == 1:
            title = load_topics()[last["objective"]].get("title", last["objective"])
            reason = (
                f"Follow up {last['objective']} (turn {last['turn']} was very brief): "
                f"invite one concrete detail or example about {title}, once, no pressure"
            )
            return last["objective"], reason, False, {"kind": "followup"}

    if not unasked:
        return "", f"all {len(PLAN_ORDER)} objectives explored after {n} answered turns", True, None
    obj = unasked[0]
    title = load_topics()[obj].get("title", obj)
    return obj, f"cover {title} ({obj}) in fixed order", False, None


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
