"""Feature 7 focused checks: transcripts, taxonomy, evidence extraction.

Run inside the api container: docker compose exec api pytest tests -q
Suite runs the dummy/heuristic extractor (no network); the live extractor
path is covered by the opt-in live smoke only.
"""

import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MONGODB_DB", "mrprof")

from app.extraction import (  # noqa: E402
    ExtractionResult,
    TAXONOMY_VERSION,
    classify_dummy,
    dummy_extract,
    load_taxonomy,
    validate_observations,
)
from app.interview import PLAN_ORDER  # noqa: E402
from app.llm import LLMError  # noqa: E402
from app.main import app  # noqa: E402
from app.transcripts import segment_text, split_paragraphs  # noqa: E402


@pytest.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    from app.db import get_db

    for name in await get_db().client.list_database_names():
        if name.startswith("mrprof_test_"):
            await get_db().client.drop_database(name)


async def _create(client, password: str | None = None) -> dict:
    password = password or f"correct horse {uuid.uuid4().hex[:8]}"
    res = await client.post("/assessments", json={"password": password})
    assert res.status_code == 201
    body = res.json()
    return {"assessment_id": body["assessment_id"], "password": password, **body}


def _auth(password: str) -> dict:
    return {"Authorization": f"Bearer {password}"}


def test_unit_segmentation_preserves_formatting_and_ids():
    text = "First paragraph.\n\n- item one\n- item two\n\nLast  paragraph   with  spaces."
    segs, nxt = segment_text(text, 2, "A", 4)
    assert [s["id"] for s in segs] == ["T2-A1", "T2-A2", "T2-A3"]
    assert [s["line"] for s in segs] == [4, 5, 6] and nxt == 7
    assert segs[1]["text"] == "- item one\n- item two"  # list kept in one segment
    assert segs[2]["text"] == "Last  paragraph   with  spaces."  # internal spacing kept
    # Deterministic: same input -> same segments.
    assert segment_text(text, 2, "A", 4)[0] == segs
    assert split_paragraphs("  \n\n  ") == []


def test_unit_taxonomy_loads_and_matches_plan():
    tax = load_taxonomy()
    assert tax["meta"]["version"] == TAXONOMY_VERSION
    assert "not clinically reviewed" in tax["meta"]["status"].lower()
    assert tuple(tax["codes"]) == PLAN_ORDER
    for oid, code in tax["codes"].items():
        assert code["includes"] and code["excludes"] and code["example_present"]


def test_unit_dummy_classifier_distinguishes_assertions():
    assert classify_dummy("I stare at forms for an hour") == "present"
    assert classify_dummy("No, starting tasks is fine") == "explicitly-denied"
    assert classify_dummy("Never, really") == "explicitly-denied"
    assert classify_dummy("I can't remember when it started") == "uncertain"
    assert classify_dummy("I don't know, maybe") == "uncertain"
    # Negation inside a reported difficulty is still present, not a denial.
    assert classify_dummy("I do not sleep well and everything is worse") == "present"


def _segs() -> list[dict]:
    return [
        {"id": "T1-Q1", "turn": 1, "role": "Q", "n": 1, "text": "What tasks are hardest?", "line": 1},
        {"id": "T1-A1", "turn": 1, "role": "A", "n": 1, "text": "Starting paperwork.", "line": 2},
        {"id": "T1-A2", "turn": 1, "role": "A", "n": 2, "text": "I never finish it.", "line": 3},
    ]


def test_unit_quote_validation_accepts_exact_rejects_altered():
    from app.extraction import ExtractedObservation

    codes = load_taxonomy()["codes"]
    good = ExtractionResult(
        observations=[
            ExtractedObservation(
                code="task-completion", assertion="present", segment_id="T1-A1", quote="Starting paperwork."
            )
        ]
    )
    assert validate_observations(codes, _segs(), good).observations[0].quote == "Starting paperwork."
    assert validate_observations(codes, _segs(), good).observations[0].review_status == "pending"

    for bad_obs in (
        {"code": "task-completion", "assertion": "present", "segment_id": "T1-A1", "quote": "Starting  paperwork."},
        {"code": "task-completion", "assertion": "present", "segment_id": "T9-Z9", "quote": "Starting paperwork."},
        {"code": "nope-code", "assertion": "present", "segment_id": "T1-A1", "quote": "Starting paperwork."},
        {"code": "task-completion", "assertion": "sometimes", "segment_id": "T1-A1", "quote": "Starting paperwork."},
    ):
        with pytest.raises(LLMError):
            validate_observations(
                codes,
                _segs(),
                ExtractionResult(observations=[ExtractedObservation(**bad_obs)]),
            )


def test_unit_contradictions_retained_not_merged():
    from app.extraction import ExtractedObservation, ObservationLink

    codes = load_taxonomy()["codes"]
    both = ExtractionResult(
        observations=[
            ExtractedObservation(
                code="impact-work",
                assertion="present",
                segment_id="T1-A1",
                quote="Starting paperwork.",
                links=[ObservationLink(kind="possible-contradiction", turn=2, note="Turn 2 denies impact.")],
            ),
            ExtractedObservation(
                code="impact-work", assertion="explicitly-denied", segment_id="T1-A2", quote="I never finish it."
            ),
        ]
    )
    kept = validate_observations(codes, _segs(), both)
    assert len(kept.observations) == 2
    assert {o.assertion for o in kept.observations} == {"present", "explicitly-denied"}
    # Candidate criterion links stay separate from observations.
    assert kept.observations[0].criterion_links == []


def test_unit_dummy_extract_quotes_exact_segment():
    res = dummy_extract("task-completion", _segs(), "Starting paperwork.\n\nI never finish it.")
    assert len(res.observations) == 1
    obs = res.observations[0]
    assert obs.segment_id == "T1-A1" and obs.quote == "Starting paperwork."
    assert obs.assertion == "present"


async def _answer(client, base, headers, text, version):
    res = await client.post(
        f"{base}/interview/answer",
        json={
            "answer_text": text,
            "base_version": version,
            "idempotency_key": f"fk7-{uuid.uuid4().hex[:8]}",
        },
        headers=headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


async def test_transcript_and_evidence_lifecycle(client):
    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"

    assert (await client.get(f"{base}/interview/transcript", headers=headers)).status_code == 404
    assert (await client.get(f"{base}/interview/evidence", headers=headers)).json() == {
        "assessment_id": created["assessment_id"],
        "turns": [],
    }

    multi = "First point here.\n\nSecond point:\n- one\n- two"
    started = await client.post(
        f"{base}/interview/start",
        json={"base_version": 1, "idempotency_key": f"fk7-start-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert started.status_code == 200
    version = started.json()["version"]

    first_key = f"fk7-replay-{uuid.uuid4().hex[:8]}"
    first = await client.post(
        f"{base}/interview/answer",
        json={"answer_text": multi, "base_version": version, "idempotency_key": first_key},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    version = first.json()["version"]

    # Transcript preserves wording and formatting independently of evidence.
    t = (await client.get(f"{base}/interview/transcript", headers=headers)).json()
    texts = [s["text"] for s in t["segments"]]
    assert any("stay focused" in x for x in texts)
    assert "First point here." in texts
    assert "Second point:\n- one\n- two" in texts
    ids = [s["id"] for s in t["segments"]]
    assert ids == ["T1-Q1", "T1-A1", "T1-A2", "T2-Q1"]
    assert [s["line"] for s in t["segments"]] == [1, 2, 3, 4]
    assert t["lines"] == 4

    # Evidence cites exact existing spans with distinct assertions.
    ev = (await client.get(f"{base}/interview/evidence", headers=headers)).json()
    assert len(ev["turns"]) == 1 and ev["turns"][0]["turn"] == 1
    assert ev["turns"][0]["taxonomy_version"] == TAXONOMY_VERSION
    assert ev["turns"][0]["extractor"]["provider"] == "dummy"
    obs = ev["turns"][0]["observations"][0]
    assert obs["review_status"] == "pending"
    seg_text = next(s["text"] for s in t["segments"] if s["id"] == obs["segment_id"])
    assert obs["quote"] in seg_text
    assert ev["turns"][0]["coverage"]["covered"] == [PLAN_ORDER[0]]
    assert PLAN_ORDER[0] not in ev["turns"][0]["coverage"]["gaps"]

    # Same-key replay neither duplicates transcript segments nor evidence.
    replay = await client.post(
        f"{base}/interview/answer",
        json={"answer_text": multi, "base_version": version - 1, "idempotency_key": first_key},
        headers=headers,
    )
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    t2 = (await client.get(f"{base}/interview/transcript", headers=headers)).json()
    assert len(t2["segments"]) == len(t["segments"])
    ev2 = (await client.get(f"{base}/interview/evidence", headers=headers)).json()
    assert len(ev2["turns"]) == 1


async def test_answer_survives_extraction_failure(client, monkeypatch):
    import app.routes.interview as ir

    async def boom(*a, **k):
        from app.llm import LLMError

        raise LLMError("provider_error", "simulated extractor outage", status=502)

    monkeypatch.setattr(ir, "extract_turn", boom)
    created = await _create(client)
    headers = _auth(created["password"])
    base = f"/assessments/{created['assessment_id']}"
    started = await client.post(
        f"{base}/interview/start",
        json={"base_version": 1, "idempotency_key": f"fk7-fail-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    version = started.json()["version"]
    body = await _answer(client, base, headers, "ordinary answer", version)
    assert body["turn_answered"] == 1 and body["completed"] is False
    # Turn saved and next question produced; evidence simply pending.
    nxt = (await client.get(f"{base}/interview/next", headers=headers)).json()
    assert nxt["question"]["turn"] == 2
    ev = (await client.get(f"{base}/interview/evidence", headers=headers)).json()
    assert ev["turns"] == []


async def test_transcript_evidence_auth_and_404(client):
    created = await _create(client)
    other = await _create(client)
    base = f"/assessments/{created['assessment_id']}"
    assert (await client.get(f"{base}/interview/transcript")).status_code == 401
    assert (await client.get(f"{base}/interview/evidence", headers=_auth(other["password"]))).status_code == 401
    assert (
        await client.get("/assessments/a_doesnotexist/interview/transcript", headers=_auth("x"))
    ).status_code == 404
