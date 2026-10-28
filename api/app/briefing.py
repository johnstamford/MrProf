"""Feature 9 rework: interview briefing from stored interview state.

Two-phase flow. Round 1 is a conversation; a batch assessment then extracts
evidence, scores coverage, and queues follow-ups; round 2 works the queue.
Fixed template, no LLM. Patient statements (verbatim questions/answers)
stay separate from system notes (per-question objective/reason). Coverage
lists every planned objective with its evidence-grounded status. Cross-turn
tensions are listed with turn references and whether a follow-up clarified
them — retained, never silently merged. Gaps are documented, never treated
as negative findings. Draft topics, not clinically reviewed. No diagnostic
language.
"""

from __future__ import annotations

from datetime import datetime

from .interview import FAMILIES, PLAN_ORDER, load_topics

BRIEFING_BANNER = (
    "Draft-topics briefing (unreviewed). This summarizes what was reported "
    "in an interview using draft topics that are not clinically reviewed. "
    "It is not a clinical assessment. Only a qualified clinician can determine "
    "what explains a person's experiences."
)

COMPLETION_NOTE = (
    "Information gathering has ended within the turn budget. Topics below were "
    "not covered or only thinly covered; they are recorded as gaps, not as "
    "negative findings. A clinician will still need to explore anything missing."
)


def _clarified_families(turns: list[dict], tensions: list[dict]) -> set[str]:
    """Families a round-2 follow-up revisited (probe followup in that family)."""
    out: set[str] = set()
    by_objective = {t["objective"]: t for t in turns}
    for tension in tensions:
        for oid in FAMILIES.get(tension["family"], ()):
            if (by_objective.get(oid) or {}).get("probe") == "followup":
                out.add(tension["family"])
    return out


def build_interview_briefing(
    assessment_id: str,
    interview: dict,
    coverage: list[dict],
    tensions: list[dict],
    report_version: int,
    completed_at: datetime,
) -> dict:
    """Build the fixed briefing content dict from stored interview state.

    coverage and tensions come from the batch assessment (evidence-grounded);
    the builder only renders them.
    """
    turns = interview.get("turns", [])
    topics = load_topics()
    clarified = _clarified_families(turns, tensions)
    contradictions = [
        {
            "family": tension["family"],
            "areas": [topics[oid].get("title", oid) for oid in FAMILIES[tension["family"]]],
            "present_turn": tension["present_turn"],
            "denial_turn": tension["denial_turn"],
            "clarified": tension["family"] in clarified,
            "note": (
                "revisited in a round-2 follow-up; both accounts retained"
                if tension["family"] in clarified
                else "not revisited in a follow-up; both accounts retained"
            ),
        }
        for tension in tensions
    ]
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
        "coverage": coverage,
        "contradictions": contradictions,
        "gaps": [
            {
                "area": entry["title"],
                "status": (
                    "unexplored within the turn budget"
                    if entry["status"] == "unasked"
                    else f"only thinly covered ({entry['note']})"
                ),
            }
            for entry in coverage
            if entry["status"] in ("unasked", "thin", "pending")
        ],
        "completed_at": completed_at,
    }
