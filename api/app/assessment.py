"""End-of-round batch assessment (Feature 9 rework).

Round 1 is a pure conversation: no analysis, no evidence written. When it
completes, this job runs once over the full transcript:

1. Extract observations per turn (parallel, bounded) into `evidence`.
2. Synthesize deterministically in code: coverage per objective,
   cross-turn tensions, and a bounded follow-up queue.
3. Round 1 with follow-ups -> store the queue, phrase the first follow-up
   question, status followup. Otherwise (or round 2) -> build the briefing,
   status complete.

The model only phrases questions. Gap detection, tension detection, and
stop rules are code. Idempotent: per-turn evidence docs dedupe, and the job
is claimed atomically so concurrent triggers cannot double-run.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .briefing import build_interview_briefing
from .extraction import EXTRACTOR_VERSION, TAXONOMY_VERSION, extract_turn, upsert_evidence
from .interview import (
    FAMILIES,
    MAX_FOLLOWUPS,
    PLAN_ORDER,
    load_topics,
    polarity,
)
from .transcripts import append_turn_segments
from .transcripts import append_turn_segments

log = logging.getLogger("mrprof")

ASSESS_VERSION = "assessor-v0.1"
EXTRACT_CONCURRENCY = 4


def assertions_by_objective(evidence_turns: list[dict]) -> dict[str, dict]:
    """Map objective -> {assertions, turns} from the latest evidence versions."""
    out: dict[str, dict] = {}
    for doc in evidence_turns:
        latest = doc["versions"][-1]
        for obs in latest["observations"]:
            entry = out.setdefault(obs["code"], {"assertions": set(), "turns": set()})
            entry["assertions"].add(obs["assertion"])
            entry["turns"].add(doc["turn"])
    return out


def coverage_from_evidence(turns: list[dict], evidence_turns: list[dict]) -> list[dict]:
    """Per-objective coverage grounded in stored evidence. One entry per objective."""
    by_objective: dict[str, list[dict]] = {}
    for t in turns:
        by_objective.setdefault(t["objective"], []).append(t)
    by_code = assertions_by_objective(evidence_turns)
    topics = load_topics()
    summary: list[dict] = []
    for oid in PLAN_ORDER:
        answered = by_objective.get(oid, [])
        entry = by_code.get(oid)
        turn_nos = sorted({t["turn"] for t in answered})
        base = {"objective": oid, "title": topics[oid].get("title", oid), "turns": turn_nos}
        if not answered:
            summary.append({**base, "status": "unasked", "note": "not reached within the turn budget"})
            continue
        if entry is None:
            summary.append({**base, "status": "pending", "note": "evidence extraction did not complete"})
            continue
        assertions = entry["assertions"]
        pols = [polarity(t.get("answer")) for t in answered]
        if "present" in assertions and any(p == "present-like" for p in pols):
            summary.append({**base, "status": "covered", "note": "substantive account recorded"})
        elif "present" in assertions:
            summary.append({**base, "status": "thin", "note": "only brief answers recorded; limited evidence"})
        elif "explicitly-denied" in assertions:
            summary.append({**base, "status": "denied", "note": "difficulty denied; accepted as reported"})
        elif "uncertain" in assertions:
            summary.append({**base, "status": "unable", "note": "could not recall or say; not pressed further"})
        else:
            summary.append({**base, "status": "thin", "note": "only brief answers recorded; limited evidence"})
    return summary


def tensions_from_evidence(turns: list[dict], evidence_turns: list[dict]) -> list[dict]:
    """Cross-turn tensions per family from stored evidence assertions.

    An objective counts present-like with any present observation, denial-like
    with any explicitly-denied observation and no present one. Returns
    [{family, present_turn, denial_turn}] in fixed family order.
    """
    by_code = assertions_by_objective(evidence_turns)
    first_turn: dict[str, int] = {}
    for t in turns:
        first_turn.setdefault(t["objective"], t["turn"])
    tensions: list[dict] = []
    for family, members in FAMILIES.items():
        present_turn: int | None = None
        denial_turn: int | None = None
        for oid in members:
            entry = by_code.get(oid)
            if not entry:
                continue
            if "present" in entry["assertions"] and present_turn is None:
                present_turn = first_turn.get(oid)
            elif "explicitly-denied" in entry["assertions"] and denial_turn is None:
                denial_turn = first_turn.get(oid)
        if present_turn is not None and denial_turn is not None:
            tensions.append({"family": family, "present_turn": present_turn, "denial_turn": denial_turn})
    return tensions


def build_followups(
    turns: list[dict], evidence_turns: list[dict], tensions: list[dict]
) -> list[dict]:
    """Bounded follow-up queue: tensions first, then pending, then thin.

    One per objective, at most MAX_FOLLOWUPS. Each item is {objective,
    reason, tension?}. Deterministic; the model only phrases the question.
    """
    coverage = {e["objective"]: e for e in coverage_from_evidence(turns, evidence_turns)}
    queue: list[dict] = []
    used: set[str] = set()

    def _take(oid: str, reason: str, tension: str | None = None) -> None:
        if oid not in used and len(queue) < MAX_FOLLOWUPS:
            used.add(oid)
            item: dict = {"objective": oid, "reason": reason}
            if tension:
                item["tension"] = tension
            queue.append(item)

    for tension in tensions:
        family = tension["family"]
        members = FAMILIES[family]
        oid = next((o for o in members if coverage[o]["status"] in ("thin", "pending")), tension_member_deny(members, coverage))
        _take(
            oid,
            f"Clarify {family} accounts together: turn {tension['denial_turn']} reported "
            f"no difficulty while turn {tension['present_turn']} described difficulty; "
            f"one neutral question, accept either account",
            f"in turn {tension['denial_turn']} no difficulty was reported, "
            f"but turn {tension['present_turn']} described difficulty",
        )
    for entry in coverage_from_evidence(turns, evidence_turns):
        if entry["status"] in ("pending", "thin"):
            _take(
                entry["objective"],
                f"Follow up {entry['objective']}: invite one concrete detail or example "
                f"about {entry['title']}, once, no pressure",
            )
    return queue


def tension_member_deny(members: tuple[str, ...], coverage: dict) -> str:
    """Objective in the family whose coverage reads denied (clarify there)."""
    for oid in members:
        if coverage[oid]["status"] == "denied":
            return oid
    return members[0]


async def _extract_missing(db, assessment_id: str, turns: list[dict]) -> list[dict]:
    """Extract observations for turns without evidence docs (bounded parallel)."""
    tdoc = await db["transcripts"].find_one({"_id": assessment_id})
    segments = tdoc.get("segments", []) if tdoc else []
    by_turn: dict[int, list[dict]] = {}
    for s in segments:
        by_turn.setdefault(s["turn"], []).append(s)
    sem = asyncio.Semaphore(EXTRACT_CONCURRENCY)

    async def _one(turn: dict) -> None:
        tn = turn["turn"]
        if await db["evidence"].find_one({"_id": f"{assessment_id}:turn:{tn}"}):
            return
        turn_segs = by_turn.get(tn, [])
        if not turn_segs:
            log.warning("assessment has no transcript segments for %s turn %d", assessment_id, tn)
            return
        async with sem:
            try:
                result, info = await extract_turn(
                    objective=turn["objective"],
                    segments=turn_segs,
                    answer=turn.get("answer") or "",
                    session_id=assessment_id,
                )
            except Exception as exc:  # noqa: BLE001 - pending is a valid outcome
                log.warning("assessment extraction pending for %s turn %d: %s", assessment_id, tn, type(exc).__name__)
                return
        covered = sorted({t["objective"] for t in turns if t["turn"] <= tn})
        gaps = [o for o in PLAN_ORDER if o not in {t["objective"] for t in turns}]
        await upsert_evidence(db, assessment_id=assessment_id, turn=tn, result=result, info=info, covered=covered, gaps=gaps)

    await asyncio.gather(*(_one(t) for t in turns))
    return await db["evidence"].find({"assessment_id": assessment_id}).sort("turn", 1).to_list(100)


async def run_round_assessment(db, assessment_id: str, phrase) -> dict:
    """Run one batch assessment job. Returns the stored assessment summary.

    phrase(objective, reason, history, screening, tension) phrases one
    question via the model and returns (question_text, model_info, session).
    phrase is called as phrase(assessment_id, objective, reason, history,
    screening, tension). Claims the job atomically; concurrent triggers
    return current state.
    """
    doc = await db["assessments"].find_one({"_id": assessment_id})
    if doc is None:
        raise ValueError(f"unknown assessment {assessment_id}")
    iv = doc.get("interview") or {}
    turns = iv.get("turns", [])
    rounds_done = iv.get("rounds_done", 0)

    claimed = await db["assessments"].find_one_and_update(
        {
            "_id": assessment_id,
            "interview.status": "assessing",
            "interview.assessed_turns": {"$ne": len(turns)},
        },
        {"$set": {"interview.status": "processing", "interview.updated_at": datetime.now(timezone.utc)}},
        return_document=True,
    )
    if claimed is None:
        current = await db["assessments"].find_one({"_id": assessment_id})
        return (current.get("interview") or {}).get("assessment") or {"status": "unknown"}

    now = datetime.now(timezone.utc)
    try:
        evidence_turns = await _extract_missing(db, assessment_id, turns)
        coverage = coverage_from_evidence(turns, evidence_turns)
        tensions = tensions_from_evidence(turns, evidence_turns)
        followups = build_followups(turns, evidence_turns, tensions) if rounds_done == 0 else []
        summary: dict = {
            "assessor": "assessor-v0.1",
            "taxonomy": TAXONOMY_VERSION,
            "extractor": EXTRACTOR_VERSION,
            "rounds_done": rounds_done + 1,
            "assessed_turns": len(turns),
            "coverage": coverage,
            "tensions": tensions,
            "followups": followups,
            "created_at": now,
        }
        if followups:
            first = followups[0]
            q_text, model_info, session_blob = await phrase(
                assessment_id, first["objective"], first["reason"], turns, doc.get("screening"), first.get("tension")
            )
            current = {
                "turn": len(turns) + 1,
                "objective": first["objective"],
                "reason": first["reason"],
                "question": q_text,
                "answer": None,
                "probe": "followup",
                "model_provider": model_info["provider"],
                "model_name": model_info["model"],
                "skill_version": iv.get("skill_version", ""),
                "topic_version": iv.get("topic_version", ""),
            }
            await db["assessments"].find_one_and_update(
                {"_id": assessment_id},
                {
                    "$set": {
                        "interview.status": "followup",
                        "interview.current": current,
                        "interview.session": session_blob,
                        "interview.followups": followups,
                        "interview.assessed_turns": len(turns),
                        "interview.rounds_done": rounds_done + 1,
                        "interview.assessment": summary,
                        "interview.updated_at": now,
                    }
                },
            )
            # Store the follow-up question in the transcript ahead of the answer.
            await append_turn_segments(
                db, assessment_id, current["turn"], current["question"], None,
                iv.get("skill_version", ""), iv.get("topic_version", ""),
            )
        else:
            prior = await db["reports"].count_documents({"assessment_id": assessment_id, "kind": "interview"})
            transcripts_doc = await db["transcripts"].find_one({"_id": assessment_id})
            content = build_interview_briefing(
                assessment_id, iv, coverage, tensions, evidence_turns,
                (transcripts_doc or {}).get("segments", []), prior + 1, now,
            )
            await db["reports"].insert_one(
                {
                    "assessment_id": assessment_id,
                    "kind": "interview",
                    "report_version": prior + 1,
                    "answer_idem_key": None,
                    "content": {**content, "completed_at": now},
                    "created_at": now,
                }
            )
            await db["assessments"].find_one_and_update(
                {"_id": assessment_id},
                {
                    "$set": {
                        "stage": "complete",
                        "interview.status": "complete",
                        "interview.current": None,
                        "interview.followups": [],
                        "interview.assessed_turns": len(turns),
                        "interview.rounds_done": rounds_done + 1,
                        "interview.assessment": summary,
                        "interview.updated_at": now,
                    }
                },
            )
        return summary
    except Exception as exc:  # noqa: BLE001 - job failure must leave a retryable state
        log.warning("round assessment failed for %s: %s", assessment_id, type(exc).__name__)
        await db["assessments"].find_one_and_update(
            {"_id": assessment_id},
            {
                "$set": {
                    "interview.status": "assessing",
                    "interview.assessing_error": type(exc).__name__,
                    "interview.updated_at": datetime.now(timezone.utc),
                }
            },
        )
        raise
