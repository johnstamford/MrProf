"""Feature 3: ASRS v1.1 6-question screener — fixed content + deterministic scoring.

Original 0-6 method (owner decision 27 Oct 2026, supersedes the summed-0-24
note in docs/plan/mrprof-locked-plan.md): count answers meeting the official
question-specific shaded-box thresholds; >= 4 of 6 is a positive screen.

Content source: WHO Adult ASRS v1.1 Part A patient-facing wording, used under
the NYU terms (free clinical/non-clinical/commercial use with attribution;
electronic versions allowed, no other modifications). Attribution retained
verbatim in ATTRIBUTION. The February 2024 Harvard scoring-update PDF was
unreachable (HTTP 503) at build time, so the threshold table below must be
re-verified against the official shaded PDF when reachable. Thresholds are
kept as explicit versioned constants — never inferred by an LLM.

Threshold table applied (documented, reviewable):
  Q1-Q3 positive on Sometimes / Often / Very often (>= Sometimes).
  Q4-Q6 positive on Often / Very often (>= Often).
Cutoff: score >= 4 -> positive screen.
"""

from __future__ import annotations

INSTRUMENT = "asrs-v1.1-6q"
SCORING_METHOD = "original-0-6"
SCORING_VERSION = (
    "WHO-Adult-ASRS-v1.1-PartA-shaded-2003/Q1-3>=Sometimes-Q4-6>=Often-cutoff4;"
    "NYU-attribution-2026-10;harvard-update-unreachable-2026-10-27-reverify"
)
THRESHOLD_DESCRIPTION = "Q1-Q3: Sometimes/Often/Very often; Q4-Q6: Often/Very often; positive if >=4 of 6"

INSTRUCTIONS = (
    "Please answer the questions below, rating yourself on each of the criteria shown "
    "using the scale on the right side of the page. As you answer each question, place an X "
    "in the box that best describes how you have felt and conducted yourself over the past "
    "6 months."
)

ATTRIBUTION = (
    "The 6-question Adult Self-Report Scale-Version1.1 (ASRS-V1.1) Screener is a subset of "
    "the 18-question Adult ADHD Self-Report Scale-Version1.1 (Adult ASRS-V1.1) Symptom Checklist. "
    "\u00a9 New York University and the President and Fellows of Harvard College. Created by "
    "Dr. Lenard Adler (NYU) and Dr. Ronald Kessler (Harvard). Freely available for clinical, "
    "non-clinical, and commercial use with attribution; no modifications other than creating "
    "electronic versions are permitted. This screener is not a diagnosis."
)

RESPONSES: tuple[str, ...] = ("never", "rarely", "sometimes", "often", "very_often")
RESPONSE_LABELS: dict[str, str] = {
    "never": "Never",
    "rarely": "Rarely",
    "sometimes": "Sometimes",
    "often": "Often",
    "very_often": "Very often",
}

QUESTIONS: tuple[dict[str, str], ...] = (
    {"n": "1", "text": "How often do you have trouble wrapping up the final details of a project, once the challenging parts have been done?"},
    {"n": "2", "text": "How often do you have difficulty getting things in order when you have to do a task that requires organization?"},
    {"n": "3", "text": "How often do you have problems remembering appointments or obligations?"},
    {"n": "4", "text": "When you have a task that requires a lot of thought, how often do you avoid or delay getting started?"},
    {"n": "5", "text": "How often do you fidget or squirm with your hands or feet when you have to sit down for a long time?"},
    {"n": "6", "text": "How often do you feel overly active and compelled to do things, like you were driven by a motor?"},
)

# Question-specific positive sets (0-based index). Q1-Q3 >= Sometimes, Q4-Q6 >= Often.
POSITIVE_SETS: tuple[frozenset[str], ...] = (
    frozenset({"sometimes", "often", "very_often"}),
    frozenset({"sometimes", "often", "very_often"}),
    frozenset({"sometimes", "often", "very_often"}),
    frozenset({"often", "very_often"}),
    frozenset({"often", "very_often"}),
    frozenset({"often", "very_often"}),
)

POSITIVE_CUTOFF = 4


def normalize_answer(value: str) -> str:
    """Normalize one raw answer to a canonical key. Raises ValueError if unknown."""
    key = value.strip().lower().replace("-", " ").replace("_", " ")
    key = " ".join(key.split())
    key = key.replace(" ", "_")
    if key not in RESPONSES:
        raise ValueError(f"answer must be one of {list(RESPONSES)}")
    return key


def score_answers(answers: list[str]) -> tuple[int, bool, list[bool]]:
    """Deterministically score exactly 6 normalized answers.

    Returns (score 0-6, positive bool, per-question flags).
    Raises ValueError when the answer list is not exactly 6 valid responses.
    Pure function — no I/O, no LLM.
    """
    if len(answers) != 6:
        raise ValueError("all six answers are required")
    flags: list[bool] = []
    for i, raw in enumerate(answers):
        key = normalize_answer(raw)
        flags.append(key in POSITIVE_SETS[i])
    total = sum(flags)
    return total, total >= POSITIVE_CUTOFF, flags
