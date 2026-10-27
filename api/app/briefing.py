"""Feature 6: initial interview briefing from stored stub-interview state.

Fixed template, no LLM. Patient statements (verbatim questions/answers)
stay separate from system notes (per-question objective/reason). The stub
flow covers food/hobbies only, so the six broad areas named in the
screening report are listed as unexplored gaps — gaps are documented,
never treated as negative findings. No diagnostic language.
"""

from __future__ import annotations

from datetime import datetime

from .reports import NEXT_TOPICS

BRIEFING_BANNER = (
    "Short-flow test briefing (unreviewed). This summarizes what was reported "
    "in a short stub interview about food and hobbies. It is not a clinical "
    "assessment. Only a qualified clinician can determine what explains a "
    "person's experiences."
)

COMPLETION_NOTE = (
    "Information gathering for this short test flow has ended. The areas below "
    "were not explored in this flow; they are recorded as gaps, not as negative "
    "findings."
)


def build_interview_briefing(
    assessment_id: str,
    interview: dict,
    report_version: int,
    completed_at: datetime,
) -> dict:
    """Build the fixed briefing content dict from stored interview state."""
    turns = interview.get("turns", [])
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
        "gaps": [{"area": area, "status": "unexplored in this short flow"} for area in NEXT_TOPICS],
        "completed_at": completed_at,
    }
