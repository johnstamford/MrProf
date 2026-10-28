"""Feature 9: interview briefing from stored interview state.

Fixed template, no LLM. Patient statements (verbatim questions/answers)
stay separate from system notes (per-question objective/reason). Coverage
lists every planned objective with its status: covered by a substantive
account, denied, unable to recall, thin, or unasked. Cross-turn tensions
are listed with their turn references and whether they were clarified —
retained, never silently merged. Gaps are documented, never treated as
negative findings. Draft topics, not clinically reviewed. No diagnostic
language.
"""

from __future__ import annotations

from datetime import datetime

from .interview import FAMILIES, PLAN_ORDER, coverage_summary, family_tensions, load_topics

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


def _clarified_families(turns: list[dict]) -> set[str]:
    out: set[str] = set()
    for t in turns:
        probe = t.get("probe") or ""
        if probe.startswith("clarify:"):
            out.add(probe.split(":", 1)[1])
    return out


def build_interview_briefing(
    assessment_id: str,
    interview: dict,
    report_version: int,
    completed_at: datetime,
) -> dict:
    """Build the fixed briefing content dict from stored interview state."""
    turns = interview.get("turns", [])
    topics = load_topics()
    coverage = coverage_summary(turns)
    clarified = _clarified_families(turns)
    contradictions = [
        {
            "family": tension["family"],
            "areas": [topics[oid].get("title", oid) for oid in FAMILIES[tension["family"]]],
            "present_turn": tension["present_turn"],
            "denial_turn": tension["denial_turn"],
            "clarified": tension["family"] in clarified,
            "note": (
                "clarified in a later neutral question; both accounts retained"
                if tension["family"] in clarified
                else "not clarified within the turn budget; both accounts retained"
            ),
        }
        for tension in family_tensions(turns)
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
            if entry["status"] in ("unasked", "thin")
        ],
        "completed_at": completed_at,
    }
