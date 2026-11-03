"""Experimental provisional sketch (owner-authorized hackathon scope exception).

Owner decision (Nov 2026, Meta AI hackathon, "building for the future"):
judges and testers wanted the journey to end with more direction than an
evidence file. This panel is that direction — a deterministic,
plain-language sketch of the *reported pattern*, computed in code from
stored coverage + screening. It is NOT a diagnosis, names no condition as
present, and gives no probability or severity.

Hard limits (these do not move with the flag):
- Never states the person has, meets criteria for, or is excluded from any
  condition. The strongest condition-adjacent line is "the kind of
  presentation an ADHD assessment would explore", gated on a positive
  screen — a referral suggestion, not a finding.
- Never in the printable clinician evidence path by surprise: it renders as
  a separately badged experimental section, and the opening runbook
  requires it off for any real-user use.
- Deterministic code only. The LLM never writes it.

Modes (PROVISIONAL_SKETCH env): "demo-only" (default) = frozen synthetic
demos carry it, real journeys never do; "on" = real journeys include it
(for local hackathon judging only); "off" = nowhere.
"""

from __future__ import annotations

import os

BEHAVIOUR_OBJECTIVES = (
    "attention-focus",
    "organization",
    "task-completion",
    "forgetfulness",
    "restlessness",
    "impulsivity",
)


def sketch_mode() -> str:
    """Effective mode. Anything unrecognized falls back to demo-only."""
    mode = (os.environ.get("PROVISIONAL_SKETCH") or "demo-only").strip().lower()
    return mode if mode in ("demo-only", "on", "off") else "demo-only"


def build_provisional_sketch(coverage: list[dict], screening: dict | None) -> dict:
    """Deterministic pattern sketch from stored coverage + screening.

    Pure function of already-stored state. Denials and uncertainty stay
    distinct; gaps are listed as missing information.
    """
    by_status: dict[str, list[str]] = {}
    for entry in coverage or []:
        by_status.setdefault(entry.get("status", ""), []).append(entry.get("title", entry.get("objective", "")))
    reported = by_status.get("covered", [])
    denied = by_status.get("denied", [])
    uncertain = by_status.get("unable", [])
    thin = by_status.get("thin", [])
    missing = [t for s in ("unasked", "pending") for t in by_status.get(s, [])]
    behaviour_reported = sum(
        1 for oid in BEHAVIOUR_OBJECTIVES
        if next((e for e in coverage if e.get("objective") == oid), {}).get("status") == "covered"
    )
    score = (screening or {}).get("score")
    positive = (screening or {}).get("positive")
    method = (screening or {}).get("scoring_method", "original-0-6")

    lines = [
        "You reported difficulties in "
        f"{len(reported)} of {len(coverage)} areas"
        + (f" ({'; '.join(reported)})" if reported else "")
        + ".",
    ]
    if denied:
        lines.append(f"You said {len(denied)} {'area was' if len(denied) == 1 else 'areas were'} not an issue for you.")
    if uncertain:
        lines.append("You were unsure about some areas — that is recorded as uncertainty, not as a negative.")
    if thin or missing:
        lines.append("Some areas were thinly covered or not reached; they are missing information, not findings.")
    if score is None:
        lines.append("No screening was taken on this journey.")
    elif positive:
        lines.append(
            f"Your screening was {score}/6 ({method}), above the threshold where further assessment may be useful."
        )
        if behaviour_reported >= 3:
            lines.append(
                "Several reported everyday areas plus a positive screen is the kind of presentation "
                "an ADHD assessment would explore — but the same pattern can come from many other things, "
                "and this sketch is unvalidated."
            )
        else:
            lines.append(
                "With a positive screen, a clinician can help make sense of these experiences alongside it."
            )
    else:
        lines.append(
            f"Your screening was {score}/6 ({method}), below the threshold — which does not exclude "
            "ADHD or other conditions. This sketch does not point toward any particular condition."
        )
    lines.append(
        "Only a qualified clinician can determine what explains your experiences. "
        "Take both reports to your appointment."
    )
    return {
        "experimental": True,
        "headline": "Provisional sketch — experimental demo feature, not a medical conclusion",
        "behaviour_reported": behaviour_reported,
        "reported": len(reported),
        "denied": len(denied),
        "uncertain": len(uncertain),
        "thin_or_missing": len(thin) + len(missing),
        "lines": lines,
    }
