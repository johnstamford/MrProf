"""Feature 15: frozen synthetic demo report set.

Drives the four profiles in sim/profiles.py through the real API using the
scripted DummyPatient and the server dummy LLM (fast, hermetic — see
sim/driver.py + sim/patient.py), then freezes one JSON per profile into
web/public/demo/<id>.json plus an index.json manifest.

Each file is the demo source of truth: {meta, screening, briefing}.
Ground-truth profile/persona instructions never reach the viewer beyond
what the interview saw (answers + derived evidence). Re-running re-freezes
the whole set with new version stamps. sim/runs/ stays gitignored; the
frozen demo JSONs are committed.

Usage (from repo root):
  docker compose exec -e LLM_PROVIDER=dummy api python -m sim.export_demo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Force the hermetic dummy provider before importing the app (mirrors tests).
os.environ["LLM_PROVIDER"] = "dummy"

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.extraction import TAXONOMY_VERSION  # noqa: E402
from app.interview import MAX_TURNS, SKILL_VERSION, TOPIC_VERSION  # noqa: E402
from app.main import app  # noqa: E402
from sim.driver import _new_key, _post  # noqa: E402
from sim.patient import DummyPatient  # noqa: E402
from sim.persona import extract_persona, validate_persona  # noqa: E402
from sim.profiles import PROFILES, get_profile  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
OUTDIR = REPO / "web" / "public" / "demo"

HEADLINES = {
    "vague-01": "Vague short answers",
    "denier-01": "Denies difficulties, offers an alternative explanation",
    "contradictor-01": "Gives conflicting accounts across turns",
    "recall-01": "Incomplete recall with partial detail",
}

PROVES = {
    "vague-01": "Follow-ups turn thin answers into checkable evidence.",
    "denier-01": "Denials are recorded as denied — never flipped into absence of evidence.",
    "contradictor-01": "Contradictions stay visible, with both accounts retained.",
    "recall-01": "\u201cI cannot remember\u201d is respected and logged as a gap, not a finding.",
}


async def main_async(outdir: Path) -> int:
    from app.db import get_db

    outdir.mkdir(parents=True, exist_ok=True)
    # NOTE: run_journey mints a random password per run and does not return it,
    # so this exporter replays the journey inline (same driver calls) to retain
    # the password for report fetching. Isolation rules still hold: only
    # {answer_text, base_version, idempotency_key} payloads reach the API.
    import uuid


    index = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for profile in PROFILES:
            persona = extract_persona(profile)
            assert validate_persona(persona, profile) == []
            patient = DummyPatient(persona)

            password = f"demo export {uuid.uuid4().hex[:8]}"
            auth = {"Authorization": f"Bearer {password}"}
            created = await client.post("/assessments", json={"password": password})
            created.raise_for_status()
            aid = created.json()["assessment_id"]
            version = created.json()["version"]

            scr = await _post(
                client, f"/assessments/{aid}/screening",
                {"answers": profile["screening"], "base_version": version,
                 "idempotency_key": _new_key("demo-scr")}, auth,
            )
            version = scr.json()["version"]
            st = await _post(
                client, f"/assessments/{aid}/interview/start",
                {"base_version": version, "idempotency_key": _new_key("demo-start")}, auth,
            )
            version = st.json()["version"]
            question = st.json()["question"]

            turns = 0
            lat_ms: list[float] = []
            while True:
                answer_text = patient.answer(question["text"], question["turn"], question["objective"])
                t1 = asyncio.get_event_loop().time()
                res = await _post(
                    client, f"/assessments/{aid}/interview/answer",
                    {"answer_text": answer_text, "base_version": version,
                     "idempotency_key": _new_key("demo-ans")}, auth,
                )
                lat_ms.append((asyncio.get_event_loop().time() - t1) * 1000)
                body = res.json()
                version = body["version"]
                turns += 1
                if body["completed"]:
                    break
                question = body.get("question")
                if question is None:
                    # Batch assessment running: poll until follow-up or completion.
                    for _ in range(120):
                        await asyncio.sleep(2)
                        chk = await client.get(f"/assessments/{aid}/interview/assessment", headers=auth)
                        chk.raise_for_status()
                        ab = chk.json()
                        if ab["status"] == "followup" and ab.get("question"):
                            question = ab["question"]
                            break
                        if ab["status"] == "complete":
                            question = None
                            break
                    if question is None and ab["status"] == "complete":
                        break
                    if question is None:
                        raise RuntimeError(f"assessment poll timed out for {profile['id']}")
                if turns > MAX_TURNS + 5:
                    raise RuntimeError(f"turn cap exceeded for {profile['id']}")

            rep = await client.get(f"/assessments/{aid}/screening/report", headers=auth)
            rep.raise_for_status()
            screening = rep.json()
            br = await client.get(f"/assessments/{aid}/interview/report", headers=auth)
            br.raise_for_status()
            briefing = br.json()

            finished = datetime.now(timezone.utc)
            frozen = {
                "meta": {
                    "synthetic": True,
                    "watermark": "SYNTHETIC DEMO \u2014 not a real person",
                    "profile_id": profile["id"],
                    "headline": HEADLINES[profile["id"]],
                    "proves": PROVES[profile["id"]],
                    "person_behaviors": profile["behaviors"],
                    "screening_score": screening["score"],
                    "screening_method": screening["scoring_method"],
                    "model": {"provider": "dummy", "model": "dummy-stub"},
                    "skill_version": SKILL_VERSION,
                    "topic_version": TOPIC_VERSION,
                    "taxonomy_version": TAXONOMY_VERSION,
                    "patient_kind": "dummy",
                    "turns": turns,
                    "exported_at": finished.isoformat(),
                    "latency_ms": {
                        "mean": round(sum(lat_ms) / len(lat_ms), 1) if lat_ms else 0,
                        "max": round(max(lat_ms), 1) if lat_ms else 0,
                    },
                    "cost": "0 (dummy provider \u2014 no model spend)",
                    "note": "Generated through the real API with a scripted synthetic patient. "
                            "Quotes are exact interview output, never hand-edited.",
                },
                "screening": screening,
                "briefing": briefing,
            }
            dest = outdir / f"{profile['id']}.json"
            dest.write_text(json.dumps(frozen, indent=2, sort_keys=True, default=str), encoding="utf-8")
            print(f"froze {dest.name}: score={screening['score']} turns={turns} "
                  f"topics={len(briefing.get('topics', []))}")
            index.append({
                "id": profile["id"],
                "headline": HEADLINES[profile["id"]],
                "proves": PROVES[profile["id"]],
                "screening_score": screening["score"],
                "screening_method": screening["scoring_method"],
                "turns": turns,
                "exported_at": finished.isoformat(),
            })

            # Clean up: demo assessments must not linger in the dev database.
            db = get_db()
            for col in ("assessments", "transcripts", "evidence", "reports"):
                await db[col].delete_many({"assessment_id": aid})

    (outdir / "index.json").write_text(
        json.dumps({"synthetic": True,
                    "watermark": "SYNTHETIC DEMO \u2014 not a real person",
                    "demos": index}, indent=2, sort_keys=True), encoding="utf-8")
    print(f"index: {outdir / 'index.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze the synthetic demo report set.")
    parser.add_argument("--out", default=str(OUTDIR), help="output dir for frozen demo JSON")
    args = parser.parse_args(argv)
    return asyncio.run(main_async(Path(args.out)))


if __name__ == "__main__":
    sys.exit(main())
