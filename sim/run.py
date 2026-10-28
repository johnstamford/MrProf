"""Feature 8 CLI: run one synthetic persona through the real API.

Dummy (scripted patient; interviewer follows the server config):
  docker compose exec api python -m sim.run --profile vague-01
Live roleplay (model patient + live server interviewer):
  docker compose exec -e SIM_LIVE=1 api python -m sim.run --profile vague-01 --live

Artifacts land in sim/runs/<profile>-<kind>-<stamp>/ (gitignored).
Note: patient kind is a CLI choice; the interviewer/extractor always use
the API server's own LLM config (client code must never select the model).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import httpx


async def _amain(profile_id: str, live: bool, base: str, outdir: str) -> int:
    from sim.artifacts import save_run
    from sim.driver import run_journey
    from sim.patient import DummyPatient, ModelPatient
    from sim.persona import extract_persona, validate_persona
    from sim.profiles import get_profile

    profile = get_profile(profile_id)
    persona = extract_persona(profile)
    issues = validate_persona(persona, profile)
    if issues:
        print(f"persona invalid: {issues}")
        return 2
    patient = ModelPatient(persona, session_id=f"sim-{profile_id}") if live else DummyPatient(persona)
    async with httpx.AsyncClient(base_url=base, timeout=120) as client:
        run = await run_journey(client, "", persona, patient, profile["screening"])
    from app.extraction import TAXONOMY_VERSION
    from app.interview import MAX_TURNS, SKILL_VERSION, TOPIC_VERSION
    from app.llm import load_config

    cfg = load_config()
    versions = {
        "skill": SKILL_VERSION,
        "topics": TOPIC_VERSION,
        "taxonomy": TAXONOMY_VERSION,
        "interviewer": {"provider": cfg.provider, "model": cfg.model or "dummy-stub"},
        "patient": patient.kind,
        "max_turns": MAX_TURNS,
    }
    dest = save_run(outdir, run, profile, persona, versions)
    print(f"profile={profile_id} patient={patient.kind} turns={len(run['turns'])} "
          f"stop={run['stop_reason']} mean_latency_ms={run['latency_ms']['mean']:.0f}")
    print(f"artifacts: {dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a synthetic patient journey.")
    parser.add_argument("--profile", required=True, help="profile id (see sim/profiles.py)")
    parser.add_argument("--live", action="store_true",
                        help="LLM roleplay patient (costs model calls; interviewer uses server config)")
    parser.add_argument("--base", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--out", default="sim/runs", help="artifact output dir")
    args = parser.parse_args(argv)
    live = args.live or os.environ.get("SIM_LIVE") == "1"
    return asyncio.run(_amain(args.profile, live, args.base, args.out))


if __name__ == "__main__":
    sys.exit(main())
