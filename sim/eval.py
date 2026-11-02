"""F12-min regression: 4 profiles x 2 hermetic runs with threshold checks.

Hermetic by default (DummyPatient + server dummy LLM via ASGI, no network,
no cost) so the gate is reproducible. Live-model runs stay manual acceptance
only (sim/run.py --live).

Thresholds (FEATURE_PLAN F12-min):
  - 100% quote-exactness (every evidence quote is an exact substring of its
    cited transcript segment)
  - 0 banned-language hits in system-generated copy
  - 8/8 runs complete (stop_reason == complete)
  - latency/cost logged (no threshold, recorded for the report)

Each run is sealed via sim/artifacts.save_run into sim/runs/<...>/ (gitignored),
including credentials.json (assessment_id + password) so the operator can
resume the assessment in the UI for review. A summary markdown + JSON report
is written to docs/eval/f12min-<stamp>.{md,json}.

Usage (from repo root):
  python -m sim.eval
  python -m sim.eval --out sim/runs --report docs/eval
  docker compose exec api python -m sim.eval
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Hermetic dummy provider before importing the app (mirrors tests/export_demo).
os.environ["LLM_PROVIDER"] = "dummy"

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.extraction import TAXONOMY_VERSION  # noqa: E402
from app.interview import MAX_TURNS, SKILL_VERSION, TOPIC_VERSION  # noqa: E402
from app.main import app  # noqa: E402
from sim.artifacts import save_run  # noqa: E402
from sim.driver import run_journey  # noqa: E402
from sim.patient import DummyPatient  # noqa: E402
from sim.persona import extract_persona, validate_persona  # noqa: E402
from sim.profiles import PROFILES  # noqa: E402

# Banned substrings in system-generated copy (test_report + test_briefing lists).
BANNED_REPORT = ["diagnos", "probab", "%", "severe", "severity", "mild", "moderate", "rules out", "rule out"]
BANNED_BRIEFING = ["you have adhd", "probability", "severity", "mild", "moderate", "severe", "%"]

REPEATS = 2


def _check_quotes(evidence: dict, transcript: dict) -> tuple[int, int, list[str]]:
    seg_text = {s["id"]: s["text"] for s in transcript.get("segments", [])}
    total = 0
    exact = 0
    misses: list[str] = []
    for turn in evidence.get("turns", []):
        for obs in turn.get("observations", []):
            total += 1
            seg = seg_text.get(obs.get("segment_id", ""), "")
            if obs.get("quote") and obs["quote"] in seg:
                exact += 1
            else:
                misses.append(f"turn {turn.get('turn')} seg {obs.get('segment_id')}: {obs.get('quote', '')[:80]!r}")
    return exact, total, misses


def _check_banned(screening: dict, briefing: dict) -> list[str]:
    hits: list[str] = []
    sys_text = " ".join([
        screening.get("explanation", ""),
        (screening.get("interview_offer") or {}).get("note", ""),
    ]).lower()
    for word in BANNED_REPORT:
        if word in sys_text:
            hits.append(f"screening report contains {word!r}")
    brief_text = " ".join([
        briefing.get("banner", ""),
        briefing.get("completion_note", ""),
    ]).lower()
    note_text = " ".join(
        o.get("note", "")
        for topic in briefing.get("topics", [])
        for turn in topic.get("turns", [])
        for o in turn.get("observations", [])
    ).lower()
    for word in BANNED_BRIEFING:
        if word in brief_text:
            hits.append(f"briefing copy contains {word!r}")
    for word in BANNED_BRIEFING:
        if word in note_text:
            hits.append(f"observation note contains {word!r}")
    return hits


async def _evaluate_run(client: AsyncClient, profile: dict, rep: int) -> dict:
    persona = extract_persona(profile)
    issues = validate_persona(persona, profile)
    assert issues == [], f"persona invalid for {profile['id']}: {issues}"
    run = await run_journey(client, "", persona, DummyPatient(persona), profile["screening"])
    aid = run["assessment_id"]
    auth = {"Authorization": f"Bearer {run['password']}"}
    base = f"/assessments/{aid}"

    scr = await client.get(f"{base}/screening/report", headers=auth)
    scr.raise_for_status()
    screening = scr.json()
    br = await client.get(f"{base}/interview/report", headers=auth)
    br.raise_for_status()
    briefing = br.json()
    tr = await client.get(f"{base}/interview/transcript", headers=auth)
    tr.raise_for_status()
    transcript = tr.json()
    ev = await client.get(f"{base}/interview/evidence", headers=auth)
    ev.raise_for_status()
    evidence = ev.json()

    exact, total, misses = _check_quotes(evidence, transcript)
    banned = _check_banned(screening, briefing)
    return {
        "profile_id": profile["id"],
        "repeat": rep,
        "assessment_id": aid,
        # NOTE: password is returned for local review only (console +
        # gitignored credentials.json). It must never be written into the
        # committed docs/eval report.
        "password": run["password"],
        "stop_reason": run["stop_reason"],
        "turns": len(run["turns"]),
        "complete": run["stop_reason"] == "complete",
        "observations": total,
        "quotes_exact": exact,
        "quote_rate": (exact / total) if total else 1.0,
        "quote_misses": misses,
        "banned_hits": banned,
        "latency_mean_ms": round(run["latency_ms"]["mean"], 1),
        "latency_max_ms": round(run["latency_ms"]["max"], 1),
        "duration_s": round(run["duration_s"], 1),
        "briefing_latency": briefing.get("latency_summary", {}),
        "screening_score": screening.get("score"),
        "run": run,
        "versions": {
            "skill": SKILL_VERSION,
            "topics": TOPIC_VERSION,
            "taxonomy": TAXONOMY_VERSION,
            "interviewer": {"provider": "dummy", "model": "dummy-stub"},
            "patient": "dummy",
            "max_turns": MAX_TURNS,
        },
    }


async def _main_async(outdir: Path, reportdir: Path) -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    results: list[dict] = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for profile in PROFILES:
            for rep in (1, 2):
                print(f"eval {profile['id']} run {rep}/{REPEATS} ...", flush=True)
                res = await _evaluate_run(client, profile, rep)
                dest = save_run(
                    str(outdir), res["run"], profile,
                    extract_persona(profile), res["versions"],
                )
                res["artifacts"] = str(dest)
                # Don't retain the full turn transcript in the summary JSON;
                # the sealed run dir + review credentials are the source.
                del res["run"]
                results.append(res)
                print(f"  -> {res['stop_reason']} turns={res['turns']} "
                      f"quotes={res['quotes_exact']}/{res['observations']} "
                      f"banned={len(res['banned_hits'])} dir={dest.name}", flush=True)

    total_runs = len(results)
    completed = sum(1 for r in results if r["complete"])
    total_obs = sum(r["observations"] for r in results)
    total_exact = sum(r["quotes_exact"] for r in results)
    total_banned = sum(len(r["banned_hits"]) for r in results)
    pass_completion = completed == total_runs
    pass_quotes = total_obs > 0 and total_exact == total_obs
    pass_banned = total_banned == 0
    passed = pass_completion and pass_quotes and pass_banned

    mean_lat = round(sum(r["latency_mean_ms"] for r in results) / total_runs, 1) if total_runs else 0
    max_lat = round(max((r["latency_max_ms"] for r in results), default=0), 1)

    report = {
        "stamp": stamp,
        "gate": "F12-min",
        "fixtures": {"skill": SKILL_VERSION, "topics": TOPIC_VERSION, "taxonomy": TAXONOMY_VERSION,
                      "interviewer": "dummy", "patient": "dummy", "repeats": REPEATS},
        "thresholds": {"quote_exactness": "100%", "banned_hits": 0, "completion": f"{total_runs}/{total_runs}"},
        "summary": {"runs": total_runs, "completed": completed, "observations": total_obs,
                     "quotes_exact": total_exact, "banned_hits": total_banned,
                     "latency_mean_ms": mean_lat, "latency_max_ms": max_lat,
                     "passed": passed},
        "runs": [{k: v for k, v in r.items() if k != "password"} for r in results],
    }
    reportdir.mkdir(parents=True, exist_ok=True)
    (reportdir / f"f12min-{stamp}.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    lines = [f"# F12-min regression — {stamp}", "",
             f"Fixtures: skill `{SKILL_VERSION}`, topics `{TOPIC_VERSION}`, taxonomy `{TAXONOMY_VERSION}`, "
             "interviewer `dummy`, patient `dummy`.", "",
             "## Thresholds",
             f"- completion: {completed}/{total_runs} {'PASS' if pass_completion else 'FAIL'}",
             f"- quote-exactness: {total_exact}/{total_obs} {'PASS' if pass_quotes else 'FAIL'}",
             f"- banned-language hits: {total_banned} {'PASS' if pass_banned else 'FAIL'}",
             f"- latency: mean {mean_lat} ms, max {max_lat} ms (logged, no threshold)", "",
             "## Runs (review: resume on `/start` with code + password from the local gitignored credentials.json)", ""]
    for r in results:
        lines.append(f"- {r['profile_id']} run {r['repeat']}: {r['stop_reason']} turns={r['turns']} "
                     f"quotes={r['quotes_exact']}/{r['observations']} banned={len(r['banned_hits'])} "
                     f"code=`{r['assessment_id']}` (password in local gitignored sim/runs/{Path(r['artifacts']).name}/credentials.json) "
                     f"dir=`{Path(r['artifacts']).name}`")
    misses = [m for r in results for m in r["quote_misses"]]
    banned_all = [b for r in results for b in r["banned_hits"]]
    if misses:
        lines += ["", "## Quote misses"] + [f"- {m}" for m in misses]
    if banned_all:
        lines += ["", "## Banned hits"] + [f"- {b}" for b in banned_all]
    lines += ["", "Synthetic data only — success does not establish clinical validity or real-user timing.", ""]
    md_path = reportdir / f"f12min-{stamp}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{'PASS' if passed else 'FAIL'}: {completed}/{total_runs} complete, "
          f"quotes {total_exact}/{total_obs}, banned {total_banned}")
    print(f"report: {md_path}")
    print("Review credentials are in each run dir (credentials.json) and listed above. "
          "sim/runs/*/ is gitignored — never commit passwords or answers.")
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the F12-min hermetic regression.")
    parser.add_argument("--out", default="sim/runs", help="sealed run output dir (gitignored)")
    parser.add_argument("--report", default="docs/eval", help="summary report dir (committed)")
    args = parser.parse_args(argv)
    return asyncio.run(_main_async(Path(args.out), Path(args.report)))


if __name__ == "__main__":
    sys.exit(main())
