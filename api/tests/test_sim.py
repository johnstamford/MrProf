"""Feature 8 focused checks: persona validation, driver isolation, dummy journeys.

Hermetic: DummyPatient + ASGI transport, no network, no model calls.
Live roleplay is manual-only (sim/run.py --live).
"""

import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("MONGODB_DB", "mrprof")

from app.main import app  # noqa: E402
from sim.artifacts import save_run  # noqa: E402
from sim.driver import ALLOWED_ANSWER_KEYS, run_journey  # noqa: E402
from sim.patient import DummyPatient  # noqa: E402
from sim.persona import extract_persona, validate_persona  # noqa: E402
from sim.profiles import PROFILES, get_profile  # noqa: E402


@pytest.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    from app.db import get_db

    for name in await get_db().client.list_database_names():
        if name.startswith("mrprof_test_"):
            await get_db().client.drop_database(name)


def test_profiles_cover_required_behaviors():
    assert len(PROFILES) == 4
    have = {b for p in PROFILES for b in p["behaviors"]}
    for required in ("vague", "denials", "contradictions", "incomplete-recall", "alternative-explanations"):
        assert required in have, required
    for p in PROFILES:
        assert len(p["screening"]) == 6
        assert p["script"] and p["facts"] is not None


def test_persona_validation_clean_and_violations():
    for p in PROFILES:
        assert validate_persona(extract_persona(p), p) == []

    persona = extract_persona(get_profile("recall-01"))
    persona["uncertain"] = []  # drop what must be preserved
    issues = validate_persona(persona, get_profile("recall-01"))
    assert any("lost uncertainty" in i for i in issues)

    persona = extract_persona(get_profile("vague-01"))
    persona["script"]["task-completion"] = {"answer": "x", "basis": "fact:99"}
    assert any("out of range" in i for i in validate_persona(persona, get_profile("vague-01")))

    persona = extract_persona(get_profile("vague-01"))
    persona["script"]["task-completion"] = {"answer": "x", "basis": "made-up"}
    assert any("untraceable" in i for i in validate_persona(persona, get_profile("vague-01")))


@pytest.mark.parametrize("profile_id", [p["id"] for p in PROFILES])
async def test_dummy_journey_completes_with_isolation(client, profile_id):
    profile = get_profile(profile_id)
    persona = extract_persona(profile)
    assert validate_persona(persona, profile) == []
    patient = DummyPatient(persona)
    run = await run_journey(client, "", persona, patient, profile["screening"])
    assert run["stop_reason"] == "complete"
    # 14 openers; a bounded probe fires only for thin answers or tension.
    assert len(run["turns"]) in (14, 15)
    assert run["patient_calls"] == len(run["turns"])
    # Isolation: driver payload shape fixed; patient words only, never briefs.
    assert ALLOWED_ANSWER_KEYS == {"answer_text", "base_version", "idempotency_key"}
    for t in run["turns"]:
        assert "ground truth" not in t["answer"].lower()


async def test_contradiction_pair_flows_through_verbatim(client):
    profile = get_profile("contradictor-01")
    persona = extract_persona(profile)
    run = await run_journey(client, "", persona, DummyPatient(persona), profile["screening"])
    by_objective = {t["objective"]: t["answer"] for t in run["turns"]}
    assert "School was never a problem" in by_objective["childhood-onset"]
    assert "repeated a year" in by_objective["impact-work"]


async def test_artifacts_sealed(tmp_path, client):
    from app.extraction import TAXONOMY_VERSION
    from app.interview import MAX_TURNS, SKILL_VERSION, TOPIC_VERSION

    profile = get_profile("recall-01")
    persona = extract_persona(profile)
    run = await run_journey(client, "", persona, DummyPatient(persona), profile["screening"])
    dest = save_run(
        tmp_path, run, profile, persona,
        {"skill": SKILL_VERSION, "topics": TOPIC_VERSION, "taxonomy": TAXONOMY_VERSION,
         "interviewer": {"provider": "dummy"}, "patient": "dummy", "max_turns": MAX_TURNS},
    )
    names = {p.name for p in dest.iterdir()}
    assert names == {"profile.json", "reference_transcript.json", "persona.json",
                     "run_transcript.json", "results.json", "manifest.json", "credentials.json"}
    import hashlib
    import json

    manifest = json.loads((dest / "manifest.json").read_text())
    for name, sha in manifest["files"].items():
        assert hashlib.sha256((dest / name).read_bytes()).hexdigest() == sha
    # Ground truth sealed separately from the run transcript.
    ref = json.loads((dest / "reference_transcript.json").read_text())
    assert ref["ground_truth_facts"] == profile["facts"]
    results = json.loads((dest / "results.json").read_text())
    assert results["stop_reason"] == "complete" and results["turns"] in (14, 15)
    creds = json.loads((dest / "credentials.json").read_text())
    assert creds["assessment_id"] == run["assessment_id"] and creds["password"] == run["password"]
