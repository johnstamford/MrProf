"""MrProf FastAPI entrypoint (Feature 2: assessment session + persistence)."""

import importlib.metadata
import logging

from fastapi import FastAPI

from .db import get_db
from .routes.assessments import router as assessments_router
from .routes.interview import router as interview_router
from .routes.screening import router as screening_router

log = logging.getLogger("mrprof")

app = FastAPI(title="MrProf API")
app.include_router(assessments_router)
app.include_router(screening_router)
app.include_router(interview_router)


@app.get("/health")
async def health() -> dict:
    """Liveness: the process is up. No dependency checks."""
    return {"ok": True, "service": "api"}


@app.get("/ready")
async def ready() -> dict:
    """Readiness: API can reach MongoDB."""
    try:
        await get_db().client.admin.command("ping")
        return {"ok": True, "mongo": "ok"}
    except Exception as exc:  # noqa: BLE001 - surfaced as JSON for readiness
        log.warning("readiness mongo ping failed: %s", type(exc).__name__)
        return {"ok": False, "mongo": "unreachable"}


@app.get("/spike/agent-framework")
async def agent_framework_spike() -> dict:
    """Feature 1 spike: pinned Agent Framework installs and a session blob
    round-trips through MongoDB. Full interview wiring lands in Feature 5."""
    try:
        version = importlib.metadata.version("agent-framework")
    except importlib.metadata.PackageNotFoundError:
        return {"ok": False, "installed": False, "reason": "agent-framework not installed"}

    probe = {"spike": "agent-session", "blob": {"turn": 0, "note": "roundtrip stub"}}
    try:
        col = get_db()["spike_sessions"]
        await col.delete_many({"spike": "agent-session"})
        await col.insert_one(probe)
        found = await col.find_one({"spike": "agent-session"}, {"_id": 0})
        await col.delete_many({"spike": "agent-session"})
        ok = found is not None and found.get("blob") == probe["blob"]
        return {"ok": ok, "installed": True, "version": version, "mongo_roundtrip": "ok" if ok else "mismatch"}
    except Exception as exc:  # noqa: BLE001 - surfaced as JSON for the spike
        return {"ok": False, "installed": True, "version": version, "mongo_roundtrip": type(exc).__name__}
