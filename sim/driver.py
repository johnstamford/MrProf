"""Feature 8: API driver. Runs a persona through the real interview endpoints.

Isolation is structural: the only payloads ever POSTed to answer endpoints
contain exactly {answer_text, base_version, idempotency_key}. Persona
briefs, facts, and ground truth never leave this process except as the
patient's own answer words. Caps: max turns, wall-clock budget, and a
stop reason recorded on every run.
"""

from __future__ import annotations

import asyncio
import time
import uuid

ALLOWED_ANSWER_KEYS = {"answer_text", "base_version", "idempotency_key"}


def _new_key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _post(client, url: str, payload: dict, headers: dict | None = None):
    """POST with one retry on 5xx using the SAME payload (same idempotency
    key) — the designed safe-retry path. 4xx still fails fast."""
    last = None
    for attempt in (1, 2):
        res = await client.post(url, json=payload, headers=headers)
        if res.status_code < 500:
            res.raise_for_status()
            return res
        last = res
        await asyncio.sleep(2 * attempt)
    assert last is not None
    last.raise_for_status()
    raise AssertionError("unreachable")


async def run_journey(
    client,
    base: str,
    persona: dict,
    patient,
    screening: list[str],
    max_turns: int = 30,
    time_budget_s: int = 600,
) -> dict:
    """Drive create -> screening -> interview start/answers until completion.

    `client` is any httpx-like client (ASGI transport in tests, real HTTP
    in manual runs). The driver mints its own password and uses it for
    every call. Returns the run record (transcript + results).
    """
    started_at = time.monotonic()
    deadline = started_at + time_budget_s
    latencies_ms: list[float] = []
    turns: list[dict] = []
    stop_reason = "complete"

    password = f"sim patient {uuid.uuid4().hex[:8]}"
    auth = {"Authorization": f"Bearer {password}"}
    created = await client.post(f"{base}/assessments", json={"password": password})
    created.raise_for_status()
    assessment_id = created.json()["assessment_id"]
    version = created.json()["version"]

    t0 = time.monotonic()
    scr = await _post(
        client, f"{base}/assessments/{assessment_id}/screening",
        {"answers": screening, "base_version": version, "idempotency_key": _new_key("sim-scr")},
        auth,
    )
    latencies_ms.append((time.monotonic() - t0) * 1000)
    scr.raise_for_status()
    version = scr.json()["version"]

    if time.monotonic() > deadline:
        stop_reason = "time_budget"
        return _record(base, assessment_id, persona, patient, turns, latencies_ms, stop_reason, started_at)

    t0 = time.monotonic()
    st = await _post(
        client, f"{base}/assessments/{assessment_id}/interview/start",
        {"base_version": version, "idempotency_key": _new_key("sim-start")},
        auth,
    )
    latencies_ms.append((time.monotonic() - t0) * 1000)
    st.raise_for_status()
    version = st.json()["version"]
    question = st.json()["question"]

    while True:
        if len(turns) >= max_turns:
            stop_reason = "turn_cap"
            break
        if time.monotonic() > deadline:
            stop_reason = "time_budget"
            break
        maybe_async = patient.answer(question["text"], question["turn"], question["objective"])
        answer_text = await maybe_async if asyncio.iscoroutine(maybe_async) else maybe_async
        payload = {"answer_text": answer_text, "base_version": version, "idempotency_key": _new_key("sim-ans")}
        assert set(payload) == ALLOWED_ANSWER_KEYS, "driver isolation: answer payload keys fixed"
        t0 = time.monotonic()
        res = await _post(
            client, f"{base}/assessments/{assessment_id}/interview/answer", payload, auth
        )
        latencies_ms.append((time.monotonic() - t0) * 1000)
        res.raise_for_status()
        body = res.json()
        turns.append(
            {
                "turn": question["turn"],
                "objective": question["objective"],
                "question": question["text"],
                "answer": answer_text,
                "completed_after": body["completed"],
            }
        )
        version = body["version"]
        if body["completed"]:
            break
        question = body["question"]

    return _record(base, assessment_id, persona, patient, turns, latencies_ms, stop_reason, started_at)


def _record(base, assessment_id, persona, patient, turns, latencies_ms, stop_reason, started_at) -> dict:
    return {
        "assessment_id": assessment_id,
        "profile_id": persona["profile_id"],
        "patient_kind": patient.kind,
        "patient_calls": patient.calls,
        "turns": turns,
        "stop_reason": stop_reason,
        "api_calls": len(latencies_ms),
        "latency_ms": {
            "mean": sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0,
            "max": max(latencies_ms) if latencies_ms else 0,
        },
        "duration_s": time.monotonic() - started_at,
        "artifacts_base": base,
    }
