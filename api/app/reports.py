"""Feature 4: deterministic screening-report content from stored screening.

Fixed template, no LLM. Copy rules (hard domain rules):
- No diagnosis, exclusion, disease probability %, or severity labels.
- Positive screen: further assessment may be useful.
- Below threshold: does not exclude ADHD.
- Both outcomes offer the interview; scoring method is named explicitly.
"""

from __future__ import annotations

from .asrs import POSITIVE_CUTOFF, QUESTIONS, RESPONSE_LABELS, THRESHOLD_DESCRIPTION

EXPLANATION_POSITIVE = (
    "Your screening result is positive. This suggests further assessment may be useful. "
    "Only a qualified clinician can determine what explains these experiences."
)

EXPLANATION_BELOW = (
    "Your screening result is below the threshold. This does not exclude ADHD or other "
    "conditions. If you still have concerns, further assessment may be useful."
)

NEXT_SECTION_INTRO = (
    "What happens next: you will be asked several questions, one at a time, covering "
    "the following topics. Answer in your own words. If you cannot recall something, "
    "say so — you will not be pressed, and gaps are recorded as gaps."
)

# Broad areas shown in the intro. Per-question internal objectives stay hidden
# (owner decision 27 Oct 2026): the interviewer logs its objective and reason
# per question, but the participant is never shown which objective a question serves.
NEXT_TOPICS: tuple[str, ...] = (
    "Attention, organization, and getting things done",
    "Restlessness and activity",
    "Background and history over time",
    "Impact on work, education, and relationships",
    "Sleep, mood, health, and other context",
    "Strategies and support you use",
)


def build_screening_report(screening: dict) -> dict:
    """Build the fixed report content dict from a stored screening doc."""
    positive = screening["positive"]
    answers = screening["answers"]
    flags = screening["per_question_positive"]
    return {
        "instrument": screening["instrument"],
        "scoring_method": screening["scoring_method"],
        "scoring_version": screening["scoring_version"],
        "score": screening["score"],
        "cutoff": POSITIVE_CUTOFF,
        "positive": positive,
        "threshold_description": THRESHOLD_DESCRIPTION,
        "answers": [
            {
                "n": QUESTIONS[i]["n"],
                "question": QUESTIONS[i]["text"],
                "answer": RESPONSE_LABELS[a],
                "counted": flags[i],
            }
            for i, a in enumerate(answers)
        ],
        "explanation": EXPLANATION_POSITIVE if positive else EXPLANATION_BELOW,
        "interview_offer": {
            "offered": True,
            "next_stage": "interview",
            "note": "Your screening answers carry forward — you will not need to repeat them.",
        },
        "next_section": {"intro": NEXT_SECTION_INTRO, "topics": list(NEXT_TOPICS)},
        "completed_at": screening["completed_at"],
    }
