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

from .interview import (
    DIMENSION_LABELS,
    FAMILIES,
    PLAN_ORDER,
    detail_score,
    effective_answer,
    load_topics,
    missing_dimensions,
    objective_dimensions,
)
from .risk import RISK_SIGNPOST

BRIEFING_BANNER = (
    "Prepared from your answers for clinician review \u2014 unreviewed draft."
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

# Headline rule (WS3): the dominant status wins (largest member count);
# ties break Reported → Explicitly denied → Uncertain → Limited →
# Not covered. Counts are always shown alongside the headline so mixed
# areas stay honest.
FAMILY_META = (
    ("functioning", "Daily functioning"),
    ("course", "History and course"),
    ("impact", "Settings and impact"),
    ("context", "Context and background"),
)
_FAMILY_HEADLINE_TIEBREAK = ("covered", "denied", "unable", "thin", "unasked", "pending")

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
    tie = {s: i for i, s in enumerate(_FAMILY_HEADLINE_TIEBREAK)}
    areas = []
    for key, title in FAMILY_META:
        members = FAMILIES.get(key, ())
        counts: dict[str, int] = {}
        for oid in members:
            status = (by_objective.get(oid) or {}).get("status", "unasked")
            counts[status] = counts.get(status, 0) + 1
        win = max(counts, key=lambda s: (counts[s], -tie.get(s, 99)))
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


def build_front_sheet(
    coverage: list[dict],
    tensions: list[dict],
    evidence_turns: list[dict],
    segments: list[dict],
    clarified: set[str],
) -> dict:
    """Assemble the one-page front sheet from stored evidence. Deterministic.

    All content is existing stored fields only: background-goals quotes,
    screening (added by the caller snapshot), timeline (course observations
    with a stated period), impact and context observations, and "worth
    exploring together" (gaps, unable topics, unresolved tensions as open
    areas). Every entry carries its quote/line/turn anchor; nothing new is
    claimed.
    """
    topics = load_topics()
    titles = {oid: topics[oid].get("title", oid) for oid in PLAN_ORDER}
    line_by_segment = {s["id"]: s.get("line") for s in segments}
    by_code: dict[str, list[tuple[int, dict]]] = {}
    for doc in evidence_turns:
        latest = doc["versions"][-1]
        for obs in latest["observations"]:
            by_code.setdefault(obs.get("code", ""), []).append((doc["turn"], obs))

    def card(turn: int, obs: dict, oid: str) -> dict:
        return {
            "turn": turn,
            "objective": oid,
            "title": titles.get(oid, oid),
            "assertion": obs.get("assertion", ""),
            "quote": obs.get("quote", ""),
            "segment_id": obs.get("segment_id", ""),
            "line": line_by_segment.get(obs.get("segment_id", "")),
            "period": obs.get("period") or "",
            "review_status": obs.get("review_status", "pending"),
            "review_note": obs.get("review_note", ""),
            "user_correction": obs.get("user_correction", ""),
            "obs_index": obs.get("obs_index", 0),
        }

    def quotes_for(oids: list[str], *, period_only: bool = False) -> list[dict]:
        out = []
        for oid in oids:
            for turn, obs in by_code.get(oid, []):
                if period_only and not (obs.get("period") or ""):
                    continue
                out.append(card(turn, obs, oid))
        return out

    open_areas = []
    for entry in coverage:
        status = entry["status"]
        if status in ("unasked", "thin", "pending"):
            open_areas.append(
                {
                    "kind": "gap",
                    "ref": entry["objective"],
                    "title": entry["title"],
                    "text": f"{entry['title']}: {entry['note']}",
                }
            )
        elif status == "unable":
            open_areas.append(
                {
                    "kind": "uncertain",
                    "ref": entry["objective"],
                    "title": entry["title"],
                    "text": f"{entry['title']}: could not recall or say — not pressed further",
                }
            )
    for tension in tensions:
        family = tension["family"]
        area_title = dict(FAMILY_META).get(family, family)
        if family in clarified:
            continue
        open_areas.append(
            {
                "kind": "tension",
                "ref": family,
                "title": area_title,
                "text": (
                    f"{area_title}: turn {tension['denial_turn']} reported no difficulty "
                    f"while turn {tension['present_turn']} described difficulty — "
                    "both accounts retained, not revisited in a follow-up"
                ),
            }
        )
    return {
        "why": quotes_for(["background-goals"]),
        "timeline": quotes_for(["childhood-onset", "persistence-course"], period_only=True),
        "impact": quotes_for(["settings", "impact-work", "impact-relationships"]),
        "context": quotes_for(["context-factors", "strategies"]),
        "open_areas": open_areas,
    }


def coverage_detail_line(objective: str, observations: list[dict], quality=None) -> str:
    """Small per-topic dimension line for the briefing (WS2-B → WS3).

    Built from the same matrix as the follow-up queue: which of the
    objective's dimensions the stored evidence fills. Empty for topics with
    no present observation (denied/uncertain/unasked render nothing).
    """
    if not any((o or {}).get("assertion") == "present" for o in observations or []):
        return ""
    missing = set(missing_dimensions(objective, observations, quality))
    parts = [
        f"{DIMENSION_LABELS[d]} {'\u2014' if d in missing else '\u2713'}"
        for d in objective_dimensions(objective)
    ]
    return "Coverage detail: " + " \u00b7 ".join(parts)


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
    user_confirmed_at: datetime | None = None,
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
        level = detail_score(effective_answer(t), quality, filled)
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
        topic_obs: list[dict] = []
        topic_quality = None
        for t in turns_by_objective.get(oid, []):
            if t.get("quality") is not None:
                topic_quality = t["quality"]
            observations = []
            for obs in obs_by_turn.get(t["turn"], []):
                if obs["code"] != oid:
                    continue
                topic_obs.append(obs)
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
                        "user_correction": obs.get("user_correction", ""),
                        "obs_index": obs.get("obs_index", 0),
                    }
                )
            correction = t.get("correction") or {}
            topic_turns.append(
                {
                    "turn": t["turn"],
                    "question": t["question"],
                    "answer": t["answer"],
                    "correction": correction.get("text") if isinstance(correction, dict) else None,
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
                # WS2-B fills this dimension line from stored evidence.
                "coverage_detail": coverage_detail_line(oid, topic_obs, topic_quality),
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
        "front_sheet": build_front_sheet(coverage, tensions, evidence_turns, segments, clarified),
        "detail_summary": detail_summary,
        "latency_summary": latency_summary(turns),
        "support_note": RISK_SIGNPOST,
        "mode": interview.get("mode", "full"),
        "user_confirmed_at": user_confirmed_at,
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
