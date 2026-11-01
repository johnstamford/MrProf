"""Feature 10a: deterministic question validation (no LLM).

Checks a model-phrased interview question against the assigned objective
before it is stored or shown. All checks are pure code so they run the
same in tests, dummy mode, and live mode.

Violation codes: off_objective, already_answered, repeated, leading,
compound, too_long. "ok" means the question may be asked.
Fallback openers from topics/v0.4.yaml are pre-approved and always pass
content checks (they define the house style, including a two-sentence
opener with a generic "What is that like?" closer).
"""

from __future__ import annotations

import re

QUESTION_MAX_CHARS = 200
VALIDATION_MAX_REGENS = 2  # bounded: 1 initial + 2 regens, then fallback

_LEADING_RES = (
    r"don't you",
    r"doesn't it",
    r"isn't it",
    r"aren't you",
    r"wouldn't you",
    r"shouldn't you",
    r"\bright\?\s*$",
    r"\bcorrect\?\s*$",
    r"\byou agree\b",
    r"\badhd\b",
    r"\bdiagnos",
    r"\bdisorder\b",
    r"\bsymptom\b",
    r"\bhyperactiv",
    r"\binattentive",
    r"\bcaused by\b",
    r"\bbecause of your\b",
    r"\bdue to your\b",
)
_LEADING_RE = re.compile("|".join(_LEADING_RES), re.IGNORECASE)

_WH_WORDS = ("how", "what", "when", "where", "why", "describe", "tell me", "explain")


def normalize_question(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _is_fallback_text(text: str, fallback_texts: set[str] | None) -> bool:
    if not fallback_texts:
        return False
    return normalize_question(text) in {normalize_question(t) for t in fallback_texts}


def validate_question(
    question_text: str,
    returned_objective: str,
    assigned_objective: str,
    prior_questions: list[str] | None = None,
    asked_objectives: list[str] | None = None,
    fallback_texts: set[str] | None = None,
) -> str:
    """Return "ok" or a violation code. Pure function, never raises on text."""
    if returned_objective != assigned_objective:
        if asked_objectives and returned_objective in asked_objectives:
            return "already_answered"
        return "off_objective"
    norm = normalize_question(question_text)
    if _is_fallback_text(question_text, fallback_texts):
        # Pre-approved house style; still guard against exact repeats.
        if prior_questions and any(norm == normalize_question(q) for q in prior_questions):
            return "repeated"
        return "ok"
    if len((question_text or "").strip()) > QUESTION_MAX_CHARS:
        return "too_long"
    if prior_questions and any(norm == normalize_question(q) for q in prior_questions if q):
        return "repeated"
    if _LEADING_RE.search(question_text or ""):
        return "leading"
    text = (question_text or "").strip()
    if text.count("?") >= 3:
        return "compound"
    if re.search(r"(^|\n)\s*\d[.)]\s+\S", text):
        return "compound"
    lowered = norm
    if text.count("?") == 2 and " and " in lowered:
        # Two questions joined by "and" ("How is work? And how is home?").
        # The house-style "What is that like?" closer is exempt.
        clauses = [c for c in re.split(r"\band\b", lowered) if c.strip()]
        left_q = any(w in clauses[0] for w in _WH_WORDS) if clauses else False
        right_q = any(w in clauses[-1] for w in _WH_WORDS) if clauses else False
        if left_q and right_q and "what is that like" not in lowered:
            return "compound"
    if text.count("?") == 1 and " and " in lowered:
        # One question mark but two question clauses
        # ("How is work and how is home?").
        clauses = [c for c in re.split(r"\band\b", lowered) if c.strip()]
        if len(clauses) >= 2:
            left_q = any(w in clauses[0] for w in _WH_WORDS)
            right_q = any(w in clauses[-1] for w in _WH_WORDS)
            if left_q and right_q:
                return "compound"
    return "ok"


REPAIR_HINTS = {
    "off_objective": "Stay on the assigned objective only; set objective to the assigned id.",
    "already_answered": "That objective was already covered; set objective to the assigned id and ask only that topic.",
    "repeated": "Ask a fresh question you have not asked before; do not repeat an earlier question verbatim.",
    "leading": "Ask neutrally without suggesting an answer, diagnosis, or cause; remove any leading phrasing.",
    "compound": "Ask exactly ONE question in one short sentence; split or drop any second question.",
    "too_long": f"Keep the question to one short sentence under {QUESTION_MAX_CHARS} characters.",
}
