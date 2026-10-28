"""Feature 7: immutable transcripts with stable deterministic segments.

The transcript is the durable verbatim record, independent of extracted
evidence. Segments are paragraphs (blank-line separated; internal line
breaks such as lists are preserved inside one segment). IDs are stable:
T{turn}-Q{n} for question paragraphs, T{turn}-A{n} for answer paragraphs,
plus a running global line number. The transcript collection is
append-only — segments are pushed, never edited.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

log = logging.getLogger("mrprof")

_BLANK_LINE = re.compile(r"\n\s*\n")


def split_paragraphs(text: str) -> list[str]:
    """Split into paragraphs, dropping empties. Internal newlines kept."""
    return [p.strip() for p in _BLANK_LINE.split(text.strip()) if p.strip()]


def segment_text(text: str, turn: int, role: str, start_line: int) -> tuple[list[dict], int]:
    """Segment one question/answer. Returns (segments, next_line).

    role is "Q" or "A". Segment text is stored exactly (post-strip of the
    paragraph edges only). IDs: T{turn}-{role}{n}, lines: global counter.
    Pure function — stable IDs for identical inputs.
    """
    assert role in ("Q", "A")
    segments = []
    line = start_line
    for n, para in enumerate(split_paragraphs(text), start=1):
        segments.append(
            {"id": f"T{turn}-{role}{n}", "turn": turn, "role": role, "n": n, "text": para, "line": line}
        )
        line += 1
    return segments, line


async def append_turn_segments(
    db, assessment_id: str, turn: int, question: str, answer: str | None,
    skill_version: str, topic_version: str,
) -> list[dict]:
    """Append Q/A segments for one turn. Append-only; replays dedupe by ID.

    Returns the turn's segments. Transcript failures are logged, never
    raised — the assessment write is the source of truth.
    """
    doc = await db["transcripts"].find_one({"_id": assessment_id})
    existing = {s["id"] for s in (doc.get("segments") if doc else [])} if doc else set()
    start_line = (doc.get("lines", 0) + 1) if doc else 1
    q_segs, line = segment_text(question, turn, "Q", start_line)
    if existing and q_segs and all(s["id"] in existing for s in q_segs):
        # Question already stored (normal case: written at start). Discard the
        # re-segmentation so it cannot consume line numbers; answers continue
        # exactly where the transcript left off.
        q_segs = []
        line = start_line
    a_segs: list[dict] = []
    if answer is not None:
        a_segs, line = segment_text(answer, turn, "A", line)
    turn_segs = q_segs + a_segs
    fresh = [s for s in turn_segs if s["id"] not in existing]
    now = datetime.now(timezone.utc)
    try:
        if doc is None:
            await db["transcripts"].insert_one(
                {
                    "_id": assessment_id,
                    "assessment_id": assessment_id,
                    "skill_version": skill_version,
                    "topic_version": topic_version,
                    "segments": fresh,
                    "lines": line - 1,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        elif fresh:
            await db["transcripts"].update_one(
                {"_id": assessment_id},
                {
                    "$push": {"segments": {"$each": fresh}},
                    "$set": {"lines": line - 1, "updated_at": now},
                },
            )
    except DuplicateKeyError:
        pass  # concurrent start won the insert; segments dedupe by ID below
    except Exception as exc:  # noqa: BLE001 - transcript is secondary to the turn write
        log.warning("transcript append failed for %s turn %d: %s", assessment_id, turn, type(exc).__name__)
    return turn_segs
