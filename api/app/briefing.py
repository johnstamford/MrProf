"""Feature 6: initial interview briefing from stored interview state.

Fixed template, no LLM. Patient statements (verbatim questions/answers)
stay separate from system notes (per-question objective/reason). Topics
not yet covered are listed as unexplored gaps — gaps are documented,
never treated as negative findings. Draft topics, not clinically
reviewed. No diagnostic language.
"""

from __future__ import annotations

from datetime import datetime

from .interview import PLAN_ORDER, load_topics

BRIEFING_BANNER = (
    "Draft-topics briefing (unreviewed). This summarizes what was reported "
    "in a short interview using draft topics that are not clinically reviewed. "
    "It is not a clinical assessment. Only a qualified clinician can determine "
    "what explains a person's experiences."
)

COMPLETION_NOTE = (
    "Information gathering for this short flow has ended. Topics below were "
    "not covered in this flow; they are recorded as gaps, not as negative findings."
)


def build_interview_briefing(
    assessment_id: str,
    interview: dict,
    report_version: int,
    completed_at: datetime,
) -> dict:
    """Build the fixed briefing content dict from stored interview state."""
    turns = interview.get("turns", [])
    covered = {t["objective"] for t in turns}
    topics = load_topics()
    return {
        "assessment_id": assessment_id,
        "report_version": report_version,
        "kind": "interview",
        "skill_version": interview.get("skill_version", ""),
        "topic_version": interview.get("topic_version", ""),
        "banner": BRIEFING_BANNER,
        "completion_note": COMPLETION_NOTE,
        "turns_answered": len(turns),
        "statements": [
            {"turn": t["turn"], "question": t["question"], "answer": t["answer"]}
            for t in turns
        ],
        "system_notes": [
            {
                "turn": t["turn"],
                "objective": t["objective"],
                "reason": t["reason"],
                "model_provider": t.get("model_provider", ""),
                "model_name": t.get("model_name", ""),
            }
            for t in turns
        ],
        "gaps": [
            {"area": topics[oid].get("title", oid), "status": "unexplored in this short flow"}
            for oid in PLAN_ORDER
            if oid not in covered
        ],
        "completed_at": completed_at,
    }
