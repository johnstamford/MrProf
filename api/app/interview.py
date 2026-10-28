"""Deterministic interview planner (v0.2 draft topics).

The planner selects objectives IN CODE in fixed order, one topic at a
time. The LLM only phrases the question for the assigned objective —
it never plans, scores, or diagnoses.

v0.2-draft: six experience-focused topics (one per broad screening area),
asked once each, then complete. No follow-up probing yet — adaptive
follow-ups, gap prioritization, and stop rules land in later features.
Topics are explicitly NOT clinically reviewed.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

SKILL_VERSION = "skill-v0.2-draft"
TOPIC_VERSION = "topics-v0.2-draft"
TOPICS_FILE = "v0.2.yaml"

# One topic finished before the next begins; each asked once in v0.2.
PLAN_ORDER = (
    "attention-tasks",
    "restlessness",
    "history-course",
    "impact-life",
    "context-factors",
    "strategies",
)
MAX_TURNS = len(PLAN_ORDER)
HARD_TURN_CAP = 30
ANSWER_MIN_LEN = 1
ANSWER_MAX_LEN = 2000

# Answers shorter than this get one gentle invite for a concrete detail.
# Genuine denials and stated uncertainty are exempt — they are complete
# answers and must never be pressured for more.
SHORT_ANSWER_LEN = 20
_DENIAL_RE = re.compile(r"^(no|nope|never|none|nothing|not really)\b", re.IGNORECASE)
_UNCERTAIN_RE = re.compile(
    r"(don't know|do not know|can't remember|cannot remember|not sure|unsure"
    r"|dunno|no idea|can't recall|cannot recall)",
    re.IGNORECASE,
)


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


def plan_next(turns: list[dict]) -> tuple[str, str, bool]:
    """Return (objective_id, reason, complete). Pure function of answered turns."""
    n = len(turns)
    if n >= len(PLAN_ORDER):
        return "", f"draft flow complete after {n} answered turns", True
    obj = PLAN_ORDER[n]
    title = load_topics()[obj].get("title", obj)
    return obj, f"draft plan turn {n + 1}: cover {title} ({obj}) in fixed order", False


def build_prompt(
    *,
    objective: str,
    reason: str,  # noqa: ARG001 - kept for explicit logging parity
    history: list[dict],
    screening: dict | None,
    last_answer: str | None = None,
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
    if _needs_detail_invite(last_answer):
        lines.append(
            "The previous answer was very brief. Invite one concrete detail or "
            "example for this objective, once, without pressuring. A short question "
            "add-on is enough; do not lecture about answer length."
        )
    lines.append('Reply with JSON ONLY: {"question_text","objective","reason"}.')
    return lines


def _needs_detail_invite(last_answer: str | None) -> bool:
    """True when the last answer is so short it cannot support a briefing.

    Genuine denials and stated uncertainty are exempt: they are complete
    answers and must never be pressured for more.
    """
    if not last_answer:
        return False
    text = last_answer.strip()
    if len(text) >= SHORT_ANSWER_LEN:
        return False
    if _DENIAL_RE.match(text) or _UNCERTAIN_RE.search(text):
        return False
    return True
