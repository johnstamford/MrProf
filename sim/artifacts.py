"""Feature 8: sealed run artifacts. Five files per run, written once."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def save_run(outdir: str | Path, run: dict, profile: dict, persona: dict, versions: dict) -> Path:
    """Write profile/persona/run/reference/results + manifest. Returns run dir."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    dest = Path(outdir) / f"{run['profile_id']}-{run['patient_kind']}-{stamp}"
    dest.mkdir(parents=True, exist_ok=False)
    reference = {
        "profile_id": profile["id"],
        "screening": profile["screening"],
        "scripted_answers": {k: v["answer"] for k, v in persona["script"].items()},
        "ground_truth_facts": profile["facts"],
        "uncertain": profile["uncertain"],
        "contradictions": profile["contradictions"],
    }
    results = {
        "stop_reason": run["stop_reason"],
        "turns": len(run["turns"]),
        "patient_kind": run["patient_kind"],
        "patient_calls": run["patient_calls"],
        "api_calls": run["api_calls"],
        "latency_ms": run["latency_ms"],
        "duration_s": run["duration_s"],
        "versions": versions,
    }
    files = {
        "profile.json": profile,
        "reference_transcript.json": reference,
        "persona.json": persona,
        "run_transcript.json": {"assessment_id": run["assessment_id"], "turns": run["turns"]},
        "results.json": results,
    }
    manifest = {"run": run["assessment_id"], "files": {}}
    for name, payload in files.items():
        text = json.dumps(payload, indent=2, sort_keys=True)
        (dest / name).write_text(text, encoding="utf-8")
        manifest["files"][name] = _sha(text)
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return dest
