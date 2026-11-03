"""End-of-round batch assessment (Feature 9 rework).

Round 1 is a pure conversation: no analysis, no evidence written. When it
completes, this job runs once over the full transcript:

1. Extract observations per turn (parallel, bounded) into `evidence`.
2. Synthesize deterministically in code: coverage per objective,
   cross-turn tensions, and a bounded follow-up queue.
3. Round 1 with follow-ups -> store the queue, phrase the first follow-up
   question, status followup. Otherwise (or round 2) -> status review:
   the briefing is built only after the WS1 user review-and-confirm step.

The model only phrases questions. Gap detection, tension detection, and
stop rules are code. Idempotent: per-turn evidence docs dedupe, and the job
is claimed atomically so concurrent triggers cannot double-run.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from .extraction import EXTRACTOR_VERSION, TAXONOMY_VERSION, append_evidence_version, extract_turn, upsert_evidence
from .interview import (
    DIMENSION_GUIDANCE,
    DIMENSION_LABELS,
    FAMILIES,
    MAX_FOLLOWUPS,
    PLAN_ORDER,
    dummy_quality,
    effective_answer,
    load_topics,
    max_followups,
    missing_dimensions,
    polarity,
)
from .transcripts import append_correction_segments, append_turn_segments

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
        pols = [polarity(effective_answer(t)) for t in answered]
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
    turns: list[dict], evidence_turns: list[dict], tensions: list[dict],
    mode: str = "full",
) -> list[dict]:
    """Bounded follow-up queue: tensions first, then pending, then thin.

    One per objective, at most MAX_FOLLOWUPS (TASTER_MAX_FOLLOWUPS in
    taster mode). Each item is {objective, reason, tension?}.
    Deterministic; the model only phrases the question.
    """
    limit = max_followups(mode)
    coverage = {e["objective"]: e for e in coverage_from_evidence(turns, evidence_turns)}
    queue: list[dict] = []
    used: set[str] = set()

    def _take(oid: str, reason: str, tension: str | None = None, dimension: str | None = None) -> None:
        if oid not in used and len(queue) < limit:
            used.add(oid)
            item: dict = {"objective": oid, "reason": reason}
            if tension:
                item["tension"] = tension
            if dimension:
                item["dimension"] = dimension
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
    # WS2-B: present topics with missing evidence dimensions come before
    # thin/pending ones. Denials and uncertainty are exempt (complete
    # answers, never probed); pending topics keep today's handling below.
    covered = [e for e in coverage_from_evidence(turns, evidence_turns) if e["status"] == "covered"]
    if covered:
        obs_by_oid = objective_observations(turns, evidence_turns)
        quality_by_oid = objective_quality(turns)
        for entry in covered:
            oid = entry["objective"]
            missing = missing_dimensions(oid, obs_by_oid.get(oid, []), quality_by_oid.get(oid))
            if missing:
                dim = missing[0]
                _take(
                    oid,
                    f"{entry['title']} is reported but {DIMENSION_LABELS[dim]} is missing: "
                    f"ask for {DIMENSION_GUIDANCE[dim]}, once, no pressure",
                    dimension=dim,
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


def objective_observations(turns: list[dict], evidence_turns: list[dict]) -> dict[str, list[dict]]:
    """Latest observations grouped by objective for the answered turns."""
    by_turn = {t["turn"]: t for t in turns}
    out: dict[str, list[dict]] = {}
    for doc in evidence_turns:
        turn = by_turn.get(doc["turn"])
        if turn is None:
            continue
        latest = doc["versions"][-1]
        out.setdefault(turn["objective"], []).extend(latest["observations"])
    return out


def objective_quality(turns: list[dict]) -> dict[str, dict | None]:
    """Latest advisory quality per objective (None when the model omitted it)."""
    out: dict[str, dict | None] = {}
    for t in turns:
        if t.get("quality") is not None:
            out[t["objective"]] = t["quality"]
    return {t["objective"]: out.get(t["objective"]) for t in turns}


def backfill_quality(turns: list[dict]) -> list[dict]:
    """Fill missing advisory quality with the deterministic heuristic.

    The interviewer rates an answer while phrasing the next question, so the
    final round-1 answer (and any the model skipped) carries no rating. The
    fallback mirrors polarity for detail and flags explicit example language;
    a stored model rating always wins when present. Advisory only — planning
    never depends on it beyond the WS2-B example check.
    """
    out = []
    for t in turns:
        if t.get("quality") is None:
            t = {**t, "quality": dummy_quality(effective_answer(t))}
        out.append(t)
    return out


async def write_assess_progress(db, assessment_id: str, done: int, total: int) -> None:
    """Record batch-extraction progress for the assessing UI. Best-effort."""
    await db["assessments"].update_one(
        {"_id": assessment_id},
        {"$set": {"interview.assess_progress": {"done": done, "total": total}}},
    )


def _turn_text_for_extraction(turn: dict) -> str:
    """Answer text the extractor reads: original plus any later correction.

    Segments carry both verbatim; the combined string keeps the dummy
    classifier and any answer-scanning logic honest about what was said.
    """
    base = turn.get("answer") or ""
    correction = (turn.get("correction") or {}).get("text")
    return f"{base}\n{correction}" if correction else base


async def extract_single_turn(db, assessment_id: str, turn_number: int) -> dict | None:
    """Extract evidence for one answered turn. Idempotent, best-effort.

    Runs as a per-answer background task while the user reads the next
    question, so the end-of-round batch usually finds this turn already
    done and only synthesizes. Returns the evidence doc, or None when
    there is nothing to extract (unknown turn, no segments, model
    failure — the batch treats that as pending and retries it there).
    Never raises: background work must not break the interview loop.
    """
    try:
        if await db["evidence"].find_one({"_id": f"{assessment_id}:turn:{turn_number}"}):
            return await db["evidence"].find_one({"_id": f"{assessment_id}:turn:{turn_number}"})
        doc = await db["assessments"].find_one({"_id": assessment_id})
        turns = (doc.get("interview") or {}).get("turns", []) if doc else []
        turn = next((t for t in turns if t.get("turn") == turn_number), None)
        if turn is None or not turn.get("answer"):
            return None
        tdoc = await db["transcripts"].find_one({"_id": assessment_id})
        segments = [s for s in (tdoc.get("segments", []) if tdoc else []) if s.get("turn") == turn_number]
        if not segments:
            return None
        try:
            result, info = await extract_turn(
                objective=turn["objective"],
                segments=segments,
                answer=_turn_text_for_extraction(turn),
                session_id=assessment_id,
            )
        except Exception as exc:  # noqa: BLE001 - pending is a valid outcome
            log.warning("background extraction pending for %s turn %d: %s", assessment_id, turn_number, type(exc).__name__)
            return None
        covered = sorted({t["objective"] for t in turns if t.get("turn", 0) <= turn_number})
        objectives = {t["objective"] for t in turns}
        gaps = [o for o in PLAN_ORDER if o not in objectives]
        return await upsert_evidence(db, assessment_id=assessment_id, turn=turn_number, result=result, info=info, covered=covered, gaps=gaps)
    except Exception:  # noqa: BLE001 - background extraction never fails the loop
        log.warning("background extraction failed for %s turn %d", assessment_id, turn_number)
        return None


async def extract_corrected_turn(db, assessment_id: str, turn_number: int) -> dict | None:
    """Re-extract one turn after a WS5 user correction. Best-effort.

    The original evidence version is never rewritten; the correction
    re-extraction (original + correction segments) is appended as a new
    latest version. When no evidence doc exists yet, there is nothing to
    version — the batch job extracts the turn (with correction segments)
    in the normal path.
    """
    try:
        if not await db["evidence"].find_one({"_id": f"{assessment_id}:turn:{turn_number}"}):
            return None
        doc = await db["assessments"].find_one({"_id": assessment_id})
        turns = (doc.get("interview") or {}).get("turns", []) if doc else []
        turn = next((t for t in turns if t.get("turn") == turn_number), None)
        correction = (turn or {}).get("correction") or {}
        if turn is None or not correction.get("text"):
            return None
        tdoc = await db["transcripts"].find_one({"_id": assessment_id})
        segments = [s for s in (tdoc.get("segments", []) if tdoc else []) if s.get("turn") == turn_number]
        if not segments:
            return None
        try:
            result, info = await extract_turn(
                objective=turn["objective"],
                segments=segments,
                answer=_turn_text_for_extraction(turn),
                session_id=assessment_id,
            )
        except Exception as exc:  # noqa: BLE001 - pending is a valid outcome
            log.warning("correction extraction pending for %s turn %d: %s", assessment_id, turn_number, type(exc).__name__)
            return None
        covered = sorted({t["objective"] for t in turns if t.get("turn", 0) <= turn_number})
        gaps = [o for o in PLAN_ORDER if o not in {t["objective"] for t in turns}]
        return await append_evidence_version(
            db, assessment_id=assessment_id, turn=turn_number,
            result=result, info=info, covered=covered, gaps=gaps,
        )
    except Exception:  # noqa: BLE001 - background extraction never fails the loop
        log.warning("correction extraction failed for %s turn %d", assessment_id, turn_number)
        return None


async def _extract_missing(db, assessment_id: str, turns: list[dict]) -> list[dict]:
    """Extract observations for turns without evidence docs (bounded parallel)."""
    tdoc = await db["transcripts"].find_one({"_id": assessment_id})
    segments = tdoc.get("segments", []) if tdoc else []
    by_turn: dict[int, list[dict]] = {}
    for s in segments:
        by_turn.setdefault(s["turn"], []).append(s)
    sem = asyncio.Semaphore(EXTRACT_CONCURRENCY)
    total = len(turns)
    done = 0
    lock = asyncio.Lock()

    async def _one(turn: dict) -> None:
        nonlocal done
        try:
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
                        answer=_turn_text_for_extraction(turn),
                        session_id=assessment_id,
                    )
                except Exception as exc:  # noqa: BLE001 - pending is a valid outcome
                    log.warning("assessment extraction pending for %s turn %d: %s", assessment_id, tn, type(exc).__name__)
                    return
            covered = sorted({t["objective"] for t in turns if t["turn"] <= tn})
            gaps = [o for o in PLAN_ORDER if o not in {t["objective"] for t in turns}]
            await upsert_evidence(db, assessment_id=assessment_id, turn=tn, result=result, info=info, covered=covered, gaps=gaps)
        finally:
            async with lock:
                done += 1
                await write_assess_progress(db, assessment_id, done, total)

    await asyncio.gather(*(_one(t) for t in turns))
    await write_assess_progress(db, assessment_id, total, total)
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
    mode = iv.get("mode", "full")

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

    await write_assess_progress(db, assessment_id, 0, len(turns))
    job_started = time.monotonic()
    now = datetime.now(timezone.utc)
    try:
        evidence_turns = await _extract_missing(db, assessment_id, turns)
        log.info(
            "batch extraction done for %s: %d/%d evidence in %.1fs (background pre-extracted the rest)",
            assessment_id, len(evidence_turns), len(turns), time.monotonic() - job_started,
        )
        turns = backfill_quality(turns)
        coverage = coverage_from_evidence(turns, evidence_turns)
        tensions = tensions_from_evidence(turns, evidence_turns)
        followups = build_followups(turns, evidence_turns, tensions, mode) if rounds_done == 0 else []
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
                assessment_id, first["objective"], first["reason"], turns, doc.get("screening"), first.get("tension"), first.get("dimension")
            )
            current = {
                "turn": len(turns) + 1,
                "objective": first["objective"],
                "reason": first["reason"],
                "question": q_text,
                "answer": None,
                "probe": "followup",
                "phrase_ms": (model_info or {}).get("phrase_ms"),
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
                        "interview.turns": turns,
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
            # WS1: gathering is done but the briefing is deferred — the user
            # checks and confirms the review step first. No briefing exists
            # (and no report endpoint resolves) before confirmation.
            await db["assessments"].find_one_and_update(
                {"_id": assessment_id},
                {
                    "$set": {
                        "interview.status": "review",
                        "interview.current": None,
                        "interview.followups": [],
                        "interview.turns": turns,
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
