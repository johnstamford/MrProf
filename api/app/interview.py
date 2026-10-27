"""Feature 5: deterministic stub planner for the food/hobbies flow test.

The planner selects objectives IN CODE (round-robin over a fixed stub
set). The LLM only phrases the question for the assigned objective —
it never plans, scores, or diagnoses.

Stub flow (STUB_TOPIC_VERSION): 4 turns, then complete.
  turn 1 -> food-open, turn 2 -> hobbies-open,
  turn 3/4 -> follow-ups, shortest answer first.
Real coverage and stop rules land in Features 6/9.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

SKILL_VERSION = "stub-skill-v0.1"
TOPIC_VERSION = "stub-topics-v0.1"
MAX_STUB_TURNS = 4
HARD_TURN_CAP = 30
ANSWER_MIN_LEN = 1
ANSWER_MAX_LEN = 2000

OBJECTIVE_ORDER = ("food-open", "hobbies-open")
FOLLOWUP_OF = {"food-open": "food-followup", "hobbies-open": "hobbies-followup"}

_FALLBACK_OPENERS = {
    "food-open": "What do you most like to eat, and what makes it a favourite?",
    "hobbies-open": "What do you like to do in your free time?",
    "food-followup": "Can you tell me a bit more about a recent meal you enjoyed?",
    "hobbies-followup": "Can you tell me a bit more about the last time you did one of those activities?",
}


@lru_cache(maxsize=1)
def load_skill() -> str:
    path = Path(__file__).parent / "skills" / "SKILL.md"
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_topics() -> dict:
    """Parse the stub YAML with a minimal subset parser (no new dependency).

    The stub file uses only `key: value`, lists of `  - id: ...` mappings,
    and one plain-text continuation line. Anything richer raises loudly
    rather than silently misplanning.
    """
    path = Path(__file__).parent / "topics" / "stub.yaml"
    ordered: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s.startswith("- id:"):
            current = {"id": s.split(":", 1)[1].strip()}
            ordered[current["id"]] = current
        elif current is not None and ":" in s and not s.startswith("-"):
            k, _, v = s.partition(":")
            current[k.strip()] = v.strip().strip('"')
    if set(ordered) != set(_FALLBACK_OPENERS):
        raise RuntimeError(f"stub topics mismatch: {sorted(ordered)}")
    return ordered


def fallback_question(objective: str) -> str:
    topics = load_topics()
    if objective in topics and topics[objective].get("opener"):
        return topics[objective]["opener"]
    return _FALLBACK_OPENERS[objective]


def plan_next(turns: list[dict]) -> tuple[str, str, bool]:
    """Return (objective_id, reason, complete). Pure function of answered turns."""
    n = len(turns)
    if n < len(OBJECTIVE_ORDER):
        obj = OBJECTIVE_ORDER[n]
        return obj, f"stub plan turn {n + 1}: cover {obj} in fixed order", False
    if n >= MAX_STUB_TURNS:
        return "", f"stub complete after {n} answered turns", True
    # Follow-ups: shortest answer's topic first.
    lens = {}
    for t in turns:
        lens[t.get("objective", "")] = len(t.get("answer", ""))
    first_open = min(OBJECTIVE_ORDER, key=lambda o: lens.get(o, 0))
    done_followups = {t.get("objective") for t in turns} & set(FOLLOWUP_OF.values())
    if FOLLOWUP_OF[first_open] not in done_followups:
        obj = FOLLOWUP_OF[first_open]
        return obj, f"stub plan turn {n + 1}: follow up on shortest answer ({first_open})", False
    other = next(o for o in OBJECTIVE_ORDER if o != first_open)
    return FOLLOWUP_OF[other], f"stub plan turn {n + 1}: follow up on {other}", False


def build_prompt(
    *,
    objective: str,
    reason: str,  # noqa: ARG001 - kept for explicit logging parity
    history: list[dict],
    screening: dict | None,
) -> str:
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
    lines.append('Reply with JSON ONLY: {"question_text","objective","reason"}.')
    return "\n".join(lines)
