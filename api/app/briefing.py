"""Feature 9 rework: interview briefing from stored interview state.

Two-phase flow. Round 1 is a conversation; a batch assessment then extracts
evidence, scores coverage, and queues follow-ups; round 2 works the queue.
Fixed template, no LLM. The report is organized per topic: each planned
objective shows its questions, verbatim answers, and the evidence
observations grounded in exact transcript spans — then the full transcript
with line numbers, so every citation can be checked. Patient statements
stay separate from system notes. Gaps are documented, never treated as
negative findings. Draft topics, not clinically reviewed. No diagnostic
language.
"""

from __future__ import annotations

from datetime import datetime

from .interview import FAMILIES, PLAN_ORDER, detail_score, load_topics
from .risk import RISK_SIGNPOST

BRIEFING_BANNER = (
    "Draft-topics briefing (unreviewed). This summarizes what was reported "
    "in an interview using draft topics that are not clinically reviewed. "
    "It is not a clinical assessment. Only a qualified clinician can determine "
    "what explains a person's experiences."
)

# Section-1 display vocabulary. Denial stays distinct from missing information:
# "Explicitly denied" is an answer; "Not covered" means we have nothing.
TOPIC_STATUS_LABELS = {
    "covered": "Reported",
    "denied": "Explicitly denied",
    "unable": "Uncertain",
    "thin": "Limited",
    "unasked": "Not covered",
    "pending": "Not covered",
}

# The four clinician-facing areas. Rollup priority: uncertainty first (needs
# attention), then reported detail, denial, limited, and finally gaps. Counts
# are always shown alongside the headline so mixed areas stay honest.
FAMILY_META = (
    ("functioning", "Daily functioning"),
    ("course", "History and course"),
    ("impact", "Settings and impact"),
    ("context", "Context and background"),
)
_FAMILY_ROLLUP_PRIORITY = ("unable", "covered", "denied", "thin", "unasked", "pending")

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


def latency_summary(turns: list[dict]) -> dict:
    """p50/p95/max over stored per-turn phrase_ms values (server-side only)."""
    samples = sorted(float(t.get("phrase_ms", 0) or 0) for t in turns if t.get("phrase_ms") is not None)
    if not samples:
        return {"count": 0, "p50_ms": 0, "p95_ms": 0, "max_ms": 0}
    import math

    def _pct(p: float) -> float:
        k = (len(samples) - 1) * (p / 100)
        lo, hi = math.floor(k), math.ceil(k)
        if lo == hi:
            return samples[int(k)]
        return samples[lo] + (samples[hi] - samples[lo]) * (k - lo)

    return {
        "count": len(samples),
        "p50_ms": _pct(50),
        "p95_ms": _pct(95),
        "max_ms": samples[-1],
    }


def family_rollup(coverage: list[dict]) -> list[dict]:
    """Roll the 14 topic entries up into the 4 clinician-facing areas.

    Returns [{key, title, status, label, counts:{...}, objectives:[...]}].
    status is the raw winning status; label is its display word. Counts cover
    every member so mixed areas (e.g. 5 denied + 1 reported) stay honest.
    """
    by_objective = {e["objective"]: e for e in coverage}
    rank = {s: i for i, s in enumerate(_FAMILY_ROLLUP_PRIORITY)}
    areas = []
    for key, title in FAMILY_META:
        members = FAMILIES.get(key, ())
        counts: dict[str, int] = {}
        win = "unasked"
        for oid in members:
            status = (by_objective.get(oid) or {}).get("status", "unasked")
            counts[status] = counts.get(status, 0) + 1
            if rank.get(status, 99) < rank.get(win, 99):
                win = status
        areas.append(
            {
                "key": key,
                "title": title,
                "status": win,
                "label": TOPIC_STATUS_LABELS.get(win, win),
                "counts": counts,
                "objectives": list(members),
            }
        )
    return areas


def build_interview_briefing(
    assessment_id: str,
    interview: dict,
    coverage: list[dict],
    tensions: list[dict],
    evidence_turns: list[dict],
    segments: list[dict],
    report_version: int,
    completed_at: datetime,
    screening: dict | None = None,
) -> dict:
    """Build the fixed briefing content dict.

    coverage and tensions come from the batch assessment (evidence-grounded);
    the builder only renders them. evidence_turns are the stored evidence
    docs (latest versions); segments are the full transcript segments with
    stable line numbers. Every observation cites its segment and line.
    """
    turns = interview.get("turns", [])
    topics = load_topics()
    line_by_segment = {s["id"]: s.get("line") for s in segments}
    obs_by_turn: dict[int, list[dict]] = {}
    for doc in evidence_turns:
        latest = doc["versions"][-1]
        obs_by_turn.setdefault(doc["turn"], []).extend(latest["observations"])
    # Detail summary: per-turn 0-3 score from answer polarity + the
    # interviewer's advisory quality + actually-filled extractor fields.
    # Missing quality or evidence degrades gracefully to polarity alone.
    level_counts = [0, 0, 0, 0]
    for t in turns:
        filled = sum(
            1
            for obs in obs_by_turn.get(t["turn"], [])
            for field in ("period", "setting", "frequency", "note")
            if obs.get(field)
        )
        quality = t.get("quality")
        level = detail_score(t.get("answer"), quality, filled)
        level_counts[min(max(level, 0), 3)] += 1
    detail_summary = {
        "level_counts": level_counts,
        "grounded_turns": level_counts[3],
        "total_turns": len(turns),
    }
    turns_by_objective: dict[str, list[dict]] = {}
    for t in turns:
        turns_by_objective.setdefault(t["objective"], []).append(t)

    topic_entries = []
    for entry in coverage:
        oid = entry["objective"]
        topic_turns = []
        for t in turns_by_objective.get(oid, []):
            observations = []
            for obs in obs_by_turn.get(t["turn"], []):
                if obs["code"] != oid:
                    continue
                observations.append(
                    {
                        "assertion": obs["assertion"],
                        "quote": obs["quote"],
                        "segment_id": obs["segment_id"],
                        "note": obs.get("note", ""),
                        "line": line_by_segment.get(obs["segment_id"]),
                        "criterion_links": obs.get("criterion_links", []),
                        "review_status": obs.get("review_status", "pending"),
                        "review_note": obs.get("review_note", ""),
                        "reviewed_at": obs.get("reviewed_at"),
                        "obs_index": obs.get("obs_index", 0),
                    }
                )
            topic_turns.append(
                {
                    "turn": t["turn"],
                    "question": t["question"],
                    "answer": t["answer"],
                    "observations": observations,
                }
            )
        topic_entries.append(
            {
                "objective": oid,
                "title": entry["title"],
                "status": entry["status"],
                "label": TOPIC_STATUS_LABELS.get(entry["status"], entry["status"]),
                "note": entry["note"],
                "turns": topic_turns,
            }
        )

    clarified = _clarified_families(turns, tensions)
    screening_snapshot = None
    if screening:
        screening_snapshot = {
            "score": screening.get("score"),
            "scoring_method": screening.get("scoring_method", "original-0-6"),
            "positive": screening.get("positive"),
            "completed_at": screening.get("completed_at"),
        }
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
        "screening": screening_snapshot,
        "areas": family_rollup(coverage),
        "detail_summary": detail_summary,
        "latency_summary": latency_summary(turns),
        "support_note": RISK_SIGNPOST,
        "mode": interview.get("mode", "full"),
        "topics": topic_entries,
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
        "transcript": [
            {
                "id": s["id"],
                "turn": s["turn"],
                "role": s["role"],
                "n": s["n"],
                "text": s["text"],
                "line": s["line"],
            }
            for s in segments
        ],
        "completed_at": completed_at,
    }
