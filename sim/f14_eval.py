"""F14 10-run metrics pass: original 4 profiles x2 full + 2 taster runs.

Pinned to the original four personas so the 10-run presentation snapshot
stays comparable over time; new personas are covered by the F12-min
regression (which iterates all of PROFILES).

Hermetic (DummyPatient + server dummy LLM via ASGI, no network/cost).
Reuses sim/eval.py checks; adds mode split + F14 presentation metrics
(turn distribution, observations, screening scores, reopen checks).

Usage (from repo root):
  docker compose exec api python -m sim.f14_eval
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ["LLM_PROVIDER"] = "dummy"

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.extraction import TAXONOMY_VERSION  # noqa: E402
from app.interview import SKILL_VERSION, TOPIC_VERSION  # noqa: E402
from app.main import app  # noqa: E402
from sim.artifacts import save_run  # noqa: E402
from sim.driver import run_journey  # noqa: E402
from sim.eval import _check_banned, _check_quotes  # noqa: E402
from sim.patient import DummyPatient  # noqa: E402
from sim.persona import extract_persona, validate_persona  # noqa: E402
from sim.profiles import PROFILES  # noqa: E402

# 10 runs: 8 full (pinned 4 profiles x2) + 2 taster spot-checks.
F14_PROFILE_IDS = ["vague-01", "denier-01", "contradictor-01", "recall-01"]
TASTER_EXTRA = ["vague-01", "denier-01"]


async def _run_one(client: AsyncClient, profile: dict, mode: str, rep: int) -> dict:
    persona = extract_persona(profile)
    issues = validate_persona(persona, profile)
    assert issues == [], f"persona invalid for {profile['id']}: {issues}"
    run = await run_journey(client, "", persona, DummyPatient(persona), profile["screening"], mode=mode)
    aid = run["assessment_id"]
    auth = {"Authorization": f"Bearer {run['password']}"}
    base = f"/assessments/{aid}"
    scr = (await client.get(f"{base}/screening/report", headers=auth)).json()
    br = (await client.get(f"{base}/interview/report", headers=auth)).json()
    tr = (await client.get(f"{base}/interview/transcript", headers=auth)).json()
    ev = (await client.get(f"{base}/interview/evidence", headers=auth)).json()
    # F14 reopen check: both reports retrievable after completion.
    scr2 = await client.get(f"{base}/screening/report", headers=auth)
    br2 = await client.get(f"{base}/interview/report", headers=auth)
    exact, total, misses = _check_quotes(ev, tr)
    banned = _check_banned(scr, br)
    # Briefing shape checks (presentation-relevant, not thresholds).
    topics = br.get("topics", [])
    obs_count = sum(len(t.get("turns", [])) for t in topics)
    has_front = bool(br.get("front_sheet"))
    has_areas = bool(br.get("areas"))
    cov_lines = sum(1 for t in topics if t.get("coverage_detail"))
    return {
        "profile_id": profile["id"],
        "mode": mode,
        "repeat": rep,
        "assessment_id": aid,
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
        "screening_score": scr.get("score"),
        "reopen_ok": scr2.status_code == 200 and br2.status_code == 200,
        "briefing_topics": len(topics),
        "briefing_obs_turns": obs_count,
        "front_sheet": has_front,
        "areas": has_areas,
        "coverage_lines": cov_lines,
        "run": run,
        "versions": {"skill": SKILL_VERSION, "topics": TOPIC_VERSION, "taxonomy": TAXONOMY_VERSION,
                     "interviewer": "dummy", "patient": "dummy"},
    }


async def _main_async(outdir: Path, reportdir: Path) -> int:
    by_id = {p["id"]: p for p in PROFILES}
    profiles = [by_id[pid] for pid in F14_PROFILE_IDS]
    plan = [(p, "full", rep) for p in profiles for rep in (1, 2)]
    plan += [(by_id[pid], "taster", 1) for pid in TASTER_EXTRA]
    assert len(plan) == 10
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    results: list[dict] = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for profile, mode, rep in plan:
            print(f"f14 {profile['id']} {mode} rep {rep} ...", flush=True)
            res = await _run_one(client, profile, mode, rep)
            dest = save_run(str(outdir), res["run"], profile, extract_persona(profile), res["versions"])
            res["artifacts"] = str(dest)
            del res["run"]
            results.append(res)
            print(f"  -> {res['stop_reason']} turns={res['turns']} "
                  f"quotes={res['quotes_exact']}/{res['observations']} banned={len(res['banned_hits'])}", flush=True)
    full = [r for r in results if r["mode"] == "full"]
    taster = [r for r in results if r["mode"] == "taster"]
    completed = sum(1 for r in results if r["complete"])
    total_obs = sum(r["observations"] for r in results)
    total_exact = sum(r["quotes_exact"] for r in results)
    total_banned = sum(len(r["banned_hits"]) for r in results)
    passed = completed == 10 and total_exact == total_obs and total_banned == 0
    mean_lat = round(sum(r["latency_mean_ms"] for r in results) / len(results), 1)
    max_lat = round(max(r["latency_max_ms"] for r in results), 1)
    report = {
        "stamp": stamp, "gate": "F14-10run",
        "fixtures": {"skill": SKILL_VERSION, "topics": TOPIC_VERSION, "taxonomy": TAXONOMY_VERSION,
                     "interviewer": "dummy", "patient": "dummy"},
        "thresholds": {"quote_exactness": "100%", "banned_hits": 0, "completion": "10/10"},
        "summary": {"runs": 10, "completed": completed,
                     "full": {"n": len(full), "turns": [r["turns"] for r in full]},
                     "taster": {"n": len(taster), "turns": [r["turns"] for r in taster]},
                     "observations": total_obs, "quotes_exact": total_exact,
                     "banned_hits": total_banned, "latency_mean_ms": mean_lat,
                     "latency_max_ms": max_lat,
                     "reopen_ok": all(r["reopen_ok"] for r in results),
                     "front_sheet": all(r["front_sheet"] for r in results),
                     "passed": passed},
        "runs": results,
    }
    reportdir.mkdir(parents=True, exist_ok=True)
    (reportdir / f"f14-10run-{stamp}.json").write_text(json.dumps(report, indent=2, sort_keys=True))
    lines = [f"# F14 10-run metrics — {stamp}", "",
             f"Fixtures: skill `{SKILL_VERSION}`, topics `{TOPIC_VERSION}`, taxonomy `{TAXONOMY_VERSION}`, "
             "interviewer `dummy` (hermetic ASGI, no network/cost), patient `dummy`.", "",
             "## Thresholds (same as F12-min)",
             f"- completion: {completed}/10 {'PASS' if completed == 10 else 'FAIL'}",
             f"- quote-exactness: {total_exact}/{total_obs} {'PASS' if total_exact == total_obs else 'FAIL'}",
             f"- banned-language hits: {total_banned} {'PASS' if total_banned == 0 else 'FAIL'}",
             f"- latency (logged, not gated): mean {mean_lat} ms, max {max_lat} ms (ASGI in-process, not real-user timing)", "",
             "## Turn counts",
             f"- full (n={len(full)}): {sorted(r['turns'] for r in full)}",
             f"- taster (n={len(taster)}): {sorted(r['turns'] for r in taster)}", "",
             "## Runs", ""]
    for r in results:
        lines.append(f"- {r['profile_id']} {r['mode']} rep {r['repeat']}: {r['stop_reason']} turns={r['turns']} "
                     f"obs={r['observations']} quotes={r['quotes_exact']}/{r['observations']} "
                     f"banned={len(r['banned_hits'])} screen={r['screening_score']} reopen={'ok' if r['reopen_ok'] else 'FAIL'}")
    misses = [m for r in results for m in r["quote_misses"]]
    banned_all = [b for r in results for b in r["banned_hits"]]
    if misses:
        lines += ["", "## Quote misses"] + [f"- {m}" for m in misses]
    if banned_all:
        lines += ["", "## Banned hits"] + [f"- {b}" for b in banned_all]
    lines += ["", "Synthetic data only — pipeline metrics, not clinical validity or real-user timing.", ""]
    md_path = reportdir / f"f14-10run-{stamp}.md"
    md_path.write_text("\n".join(lines))
    print(f"\n{'PASS' if passed else 'FAIL'}: {completed}/10 complete, quotes {total_exact}/{total_obs}, banned {total_banned}")
    print(f"report: {md_path}")
    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="F14 10-run metrics pass.")
    ap.add_argument("--out", default="sim/runs")
    ap.add_argument("--report", default="docs/eval")
    args = ap.parse_args(argv)
    return asyncio.run(_main_async(Path(args.out), Path(args.report)))


if __name__ == "__main__":
    import sys
    sys.exit(main())
