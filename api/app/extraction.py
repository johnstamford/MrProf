"""Feature 7: evidence extraction from transcript segments.

A second Agent Framework agent (the extractor) reads one turn's segments
and emits structured observations. Every quote is validated
character-for-character against the stored segments — altered or missing
quotes are rejected, never stored. Assertion kinds (present /
explicitly-denied / uncertain) and candidate criterion links stay
distinct; contradictions are retained as linked observations, never merged.

Dummy path (LLM_PROVIDER=dummy): deterministic keyword heuristic, clearly
marked by extractor provider "dummy". Test-only scaffolding — real
judgment comes from the model path. Real path: strict JSON + Pydantic,
one bounded regen, same timeout/cost bounds as the interviewer.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from .interview import PLAN_ORDER, polarity
from .llm import (
    LLMConfig,
    LLMError,
    build_agent,
    load_config,
    require_effective_provider,
    run_agent_text,
)

log = logging.getLogger("mrprof")

EXTRACTOR_VERSION = "extractor-v0.1"
TAXONOMY_VERSION = "taxonomy-v0.3-draft"
TAXONOMY_FILE = "v0.3.yaml"
ALLOWED_ASSERTIONS = ("present", "explicitly-denied", "uncertain")

_UNCERTAIN_RE = re.compile(
    r"(don'?t know|do not know|can'?t remember|cannot remember|not sure|unsure"
    r"|maybe|hard to (say|remember|recall)|can'?t recall)",
    re.IGNORECASE,
)
_DENIAL_RE = re.compile(r"^(no|nope|never|none|nothing|not really)\b", re.IGNORECASE)


class CriterionLink(BaseModel):
    ref: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=500)


class ObservationLink(BaseModel):
    kind: str = Field(min_length=1, max_length=64)
    turn: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=500)


class ExtractedObservation(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    assertion: str = Field(min_length=1, max_length=32)
    segment_id: str = Field(min_length=1, max_length=32)
    quote: str = Field(min_length=1, max_length=2000)
    period: str = Field(default="", max_length=200)
    setting: str = Field(default="", max_length=200)
    frequency: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=500)
    criterion_links: list[CriterionLink] = Field(default_factory=list)
    links: list[ObservationLink] = Field(default_factory=list)
    review_status: str = "pending"


class ExtractionResult(BaseModel):
    observations: list[ExtractedObservation] = Field(min_length=1, max_length=10)


@lru_cache(maxsize=1)
def load_taxonomy() -> dict:
    """Parse the draft taxonomy (same minimal subset shape as topics)."""
    path = Path(__file__).parent / "taxonomy" / TAXONOMY_FILE
    meta: dict[str, str] = {}
    codes: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- id:"):
            current = {"id": s.split(":", 1)[1].strip()}
            codes[current["id"]] = current
        elif current is not None and ":" in s and not s.startswith("-"):
            k, _, v = s.partition(":")
            current[k.strip()] = v.strip().strip('"')
        elif ":" in s and not s.startswith(" "):
            k, _, v = s.partition(":")
            meta[k.strip()] = v.strip()
    if tuple(codes) != PLAN_ORDER:
        raise RuntimeError(f"taxonomy code order mismatch: {tuple(codes)}")
    return {"meta": meta, "codes": codes}


def extractor_instructions() -> str:
    codes = load_taxonomy()["codes"]
    lines = [
        "You extract grounded observations from one interview turn. "
        "Output JSON ONLY: {\"observations\": [...]}.",
        "Rules:",
        "- One observation per distinct reported fact; several per turn is fine.",
        "- code must be one of: " + ", ".join(codes),
        "- assertion is present, explicitly-denied, or uncertain — never missing "
        "(missing information is simply not emitted).",
        "- segment_id must be an existing segment ID; quote must be an EXACT "
        "character-for-character substring of that segment, copied verbatim.",
        "- Quote the SHORTEST span that supports the observation — usually one "
        "sentence, never the whole answer. Split distinct facts into separate "
        "observations, each with its own minimal quote.",
        "- note is one sentence saying what the quote shows about this topic "
        "(e.g. denies difficulty sitting still; attributes it to caffeine). "
        "Grounded only: no new facts, no causes, no diagnosis, no probability, "
        "no severity language.",
        "- period/setting/frequency only when the person stated them; never infer.",
        "- criterion_links are candidate suggestions with rationale, separate "
        "from the observation; they are not findings.",
        "- If this turn contradicts an earlier turn, emit both observations and "
        "add a links entry {kind: 'possible-contradiction', turn, note}. "
        "Never merge or discard either side.",
        "- No diagnosis, no probability, no severity language.",
    ]
    return "\n".join(lines)


def extraction_prompt(objective: str, segments: list[dict]) -> str:
    lines = [f"Turn objective code: {objective}", "Segments:"]
    for s in segments:
        lines.append(f"[{s['id']}] ({s['role']}): {s['text']}")
    lines.append('Reply with JSON ONLY: {"observations": [{...}]}.')
    return "\n".join(lines)


def classify_dummy(answer: str) -> str:
    """Test-only heuristic assertion. Deterministic; real judgment is the model path."""
    return {
        "present-like": "present",
        "denial-like": "explicitly-denied",
        "uncertain-like": "uncertain",
    }.get(polarity(answer), "present")


def _minimal_span(text: str, needle: str | None) -> str:
    """Shortest sentence containing the needle, else the first sentence.

    Keeps quotes tight (one sentence) while staying an exact substring of
    the stored segment. Test-path mimic of the live minimal-span rule.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not sentences:
        return text
    if needle:
        for s in sentences:
            if needle in s.lower():
                return s
    return sentences[0]


def _first_cue(text: str, patterns: tuple[str, ...]) -> str:
    """First matching cue phrase in fixed pattern order (deterministic)."""
    lowered = text.lower()
    for p in patterns:
        if re.search(p, lowered):
            m = re.search(p, lowered)
            return m.group(0) if m else ""
    return ""


_PERIOD_CUES = (
    r"childhood", r"\bschool\b", r"\byears\b", r"\bmonths?\b", r"\bweeks?\b",
    r"\bsince\b", r"\bago\b", r"recently", r"lately", r"these days",
    r"when i was", r"age \d+", r"primary school", r"teenage", r"over the years",
    r"this (week|month|year)", r"last (week|month|year)", r"\byesterday\b",
)
_SETTING_CUES = (
    r"\bwork\b", r"\boffice\b", r"\bmeeting\w*\b", r"\bhome\b", r"\bclass\b",
    r"\bdriving\b", r"\bshop\w*\b", r"\bbed\b", r"\bkitchen\b", r"\bgym\b",
    r"\btrain\b", r"\bbus\b", r"\bparty\b", r"at (the )?(desk|table|counter)",
)
_FREQUENCY_CUES = (
    r"\boften\b", r"\balways\b", r"\bnever\b", r"\brarely\b", r"\bsometimes\b",
    r"\busually\b", r"\bdaily\b", r"\bweekly\b", r"\bmonthly\b",
    r"every (day|week|month|morning|night)", r"\bconstantly\b", r"\bregularly\b",
    r"times a (week|month|day)", r"\bcouple of times\b",
)


def dummy_extract(objective: str, segments: list[dict], answer: str) -> ExtractionResult:
    """Deterministic stub extraction: assertion heuristic + exact segment quote."""
    answer_segs = [s for s in segments if s["role"] == "A"]
    target = None
    needle: str | None = None
    if answer_segs:
        m = _UNCERTAIN_RE.search(answer) or _DENIAL_RE.match(answer.strip())
        if m:
            needle = m.group(0).lower()
            target = next((s for s in answer_segs if needle in s["text"].lower()), answer_segs[0])
        else:
            target = answer_segs[0]
    else:
        target = segments[0]
    assertion = classify_dummy(answer)
    explainer = {
        "present": "Describes difficulty relevant to this topic; the quote is the supporting span.",
        "explicitly-denied": "States this is not an issue for them; the quote is the supporting span.",
        "uncertain": "Expresses uncertainty on this topic; the quote is the supporting span.",
    }[assertion]
    # WS2-B: the hermetic path fills dimension fields from explicit cues
    # only (no inference). Vague answers stay missing and earn a targeted
    # follow-up; detailed answers fill in. Deterministic by construction.
    return ExtractionResult(
        observations=[
            ExtractedObservation(
                code=objective,
                assertion=assertion,
                segment_id=target["id"],
                quote=_minimal_span(target["text"], needle),
                period=_first_cue(answer, _PERIOD_CUES),
                setting=_first_cue(answer, _SETTING_CUES),
                frequency=_first_cue(answer, _FREQUENCY_CUES),
                note=explainer,
            )
        ]
    )


def validate_observations(
    codes: dict, segments: list[dict], result: ExtractionResult
) -> ExtractionResult:
    """Enforce code/assertion/quote integrity. Raises LLMError on any violation."""
    by_id = {s["id"]: s["text"] for s in segments}
    for obs in result.observations:
        if obs.code not in codes:
            raise LLMError(
                "malformed_output",
                f"Observation cites unknown code {obs.code!r}. Check the model or use LLM_PROVIDER=dummy.",
            )
        if obs.assertion not in ALLOWED_ASSERTIONS:
            raise LLMError(
                "malformed_output",
                f"Observation has invalid assertion {obs.assertion!r}; "
                "must be present, explicitly-denied, or uncertain.",
            )
        seg_text = by_id.get(obs.segment_id)
        if seg_text is None:
            raise LLMError(
                "malformed_output",
                f"Observation cites missing segment {obs.segment_id!r}. "
                "Quotes must reference exact existing source spans.",
            )
        if not obs.quote or obs.quote not in seg_text:
            raise LLMError(
                "malformed_output",
                f"Quote for {obs.segment_id!r} does not match the stored text. "
                "Altered quotes are rejected.",
            )
    return result


async def extract_turn(
    *,
    objective: str,
    segments: list[dict],
    answer: str,
    session_id: str,
    cfg: LLMConfig | None = None,
) -> tuple[ExtractionResult, dict]:
    """Extract observations for one answered turn. Returns (result, extractor_info).

    Raises LLMError on model failure — callers must keep the saved turn and
    degrade gracefully (evidence pending), never fail the interview loop.
    """
    cfg = cfg or load_config()
    extractor_info = {
        "extractor": EXTRACTOR_VERSION,
        "taxonomy": TAXONOMY_VERSION,
        "provider": cfg.provider,
        "model": cfg.model or "dummy-stub",
    }
    codes = load_taxonomy()["codes"]
    if objective not in codes:
        raise LLMError("planner_error", f"Unknown objective {objective!r}.", status=500)
    if require_effective_provider(cfg) == "dummy":
        return validate_observations(codes, segments, dummy_extract(objective, segments, answer)), extractor_info
    prompt = extraction_prompt(objective, segments)
    agent, session = build_agent(cfg, extractor_instructions(), session_id)
    last_error: LLMError | None = None
    current = prompt
    for attempt in (1, 2, 3):
        try:
            text, _, _ = await run_agent_text(
                cfg, agent, session, current, dict(extractor_info), session_id,
                timeout_s=cfg.extractor_timeout_s,
            )
        except LLMError as exc:
            # Same transient policy as the interviewer: one retry on a
            # timeout/provider blip (same prompt), then give up gracefully.
            if exc.code in ("timeout", "provider_error") and attempt == 1:
                log.warning("transient extractor failure, retrying once: %s", exc.code)
                continue
            raise
        try:
            data = json.loads(text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
            result = ExtractionResult.model_validate(data)
            return validate_observations(codes, segments, result), extractor_info
        except (ValueError, LLMError) as exc:
            last_error = (
                exc if isinstance(exc, LLMError) else LLMError("malformed_output", f"Extractor output invalid: {exc}")
            )
            if attempt == 3:
                break
            current = (
                "Your previous reply was not valid JSON with an observations array "
                "using exact quotes. Reply with JSON ONLY.\n\n" + prompt
            )
            log.warning("malformed extractor output (attempt %d), retrying once", attempt)
    assert last_error is not None
    raise last_error


async def append_evidence_version(db, *, assessment_id: str, turn: int, result: ExtractionResult, info: dict, covered: list[str], gaps: list[str]) -> dict:
    """Append a new version to an existing per-turn evidence doc (corrections).

    WS5 "Fix my last answer": the original version is never rewritten; the
    correction re-extraction is stored as a new latest version, so reviewers
    see both. No-op (returns existing) when there is no evidence doc yet —
    the batch job's _extract_missing will extract the turn including its
    correction segments.
    """
    from datetime import datetime, timezone

    existing = await db["evidence"].find_one({"_id": f"{assessment_id}:turn:{turn}"})
    if existing is None:
        return {}
    now = datetime.now(timezone.utc)
    observations = []
    for i, o in enumerate(result.observations):
        dumped = o.model_dump()
        dumped["obs_index"] = i
        observations.append(dumped)
    version = len(existing.get("versions", [])) + 1
    await db["evidence"].update_one(
        {"_id": f"{assessment_id}:turn:{turn}"},
        {
            "$push": {
                "versions": {
                    "version": version,
                    "taxonomy_version": TAXONOMY_VERSION,
                    "extractor": info,
                    "observations": observations,
                    "coverage": {"covered": covered, "gaps": gaps},
                    "created_at": now,
                    "correction_of": version - 1,
                }
            },
            "$set": {"updated_at": now},
        },
    )
    return await db["evidence"].find_one({"_id": f"{assessment_id}:turn:{turn}"})


async def upsert_evidence(db, *, assessment_id: str, turn: int, result: ExtractionResult, info: dict, covered: list[str], gaps: list[str]) -> dict:
    """Idempotent per-turn evidence write. Replay-safe: existing turn docs are kept."""
    from datetime import datetime, timezone

    existing = await db["evidence"].find_one({"_id": f"{assessment_id}:turn:{turn}"})
    if existing is not None:
        return existing
    now = datetime.now(timezone.utc)
    observations = []
    for i, o in enumerate(result.observations):
        dumped = o.model_dump()
        dumped["obs_index"] = i
        observations.append(dumped)
    doc = {
        "_id": f"{assessment_id}:turn:{turn}",
        "assessment_id": assessment_id,
        "turn": turn,
        "status": "complete",
        "versions": [
            {
                "version": 1,
                "taxonomy_version": TAXONOMY_VERSION,
                "extractor": info,
                "observations": observations,
                "coverage": {"covered": covered, "gaps": gaps},
                "created_at": now,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db["evidence"].insert_one(doc)
    except Exception:
        existing = await db["evidence"].find_one({"_id": f"{assessment_id}:turn:{turn}"})
        if existing is not None:
            return existing
        raise
    return doc
