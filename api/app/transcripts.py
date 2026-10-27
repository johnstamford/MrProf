"""Feature 7: immutable transcripts with stable deterministic segments.

The transcript is the durable verbatim record, independent of extracted
evidence. Segments are paragraphs (blank-line separated; internal line
breaks such as lists are preserved inside one segment). IDs are stable:
T{turn}-Q{n} for question paragraphs, T{turn}-A{n} for answer paragraphs,
plus a running global line number. The transcript collection is
append-only — segments are pushed, never edited.
"""

from __future__ import annotations

import re

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
