"""MrProf FastAPI entrypoint (Feature 1: health + readiness + Agent Framework spike)."""

import importlib.metadata
import logging
import os

from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

log = logging.getLogger("mrprof")
MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://mongo:27017/mrprof")

app = FastAPI(title="MrProf API")
_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    return _client


class Health(BaseModel):
    ok: bool
    service: str = "api"


@app.get("/health", response_model=Health)
async def health() -> Health:
    """Liveness: the process is up. No dependency checks."""
    return Health(ok=True)


@app.get("/ready")
async def ready() -> dict:
    """Readiness: API can reach MongoDB."""
    try:
        await get_client().admin.command("ping")
        return {"ok": True, "mongo": "ok"}
    except Exception as exc:  # noqa: BLE001 - surfaced as JSON for readiness
        log.warning("readiness mongo ping failed: %s", type(exc).__name__)
        return {"ok": False, "mongo": "unreachable"}


@app.get("/spike/agent-framework")
async def agent_framework_spike() -> dict:
    """Feature 1 spike: prove the pinned Agent Framework installs and a session
    blob round-trips through MongoDB alongside assessment state.

    Full interview wiring lands in Feature 5; this only locks the approach:
    persist session state in Mongo per assessment, restore per request.
    """
    try:
        version = importlib.metadata.version("agent-framework")
    except importlib.metadata.PackageNotFoundError:
        return {"ok": False, "installed": False, "reason": "agent-framework not installed"}

    probe = {"spike": "agent-session", "blob": {"turn": 0, "note": "roundtrip stub"}}
    try:
        col = get_client().get_default_database()["spike_sessions"]
        await col.delete_many({"spike": "agent-session"})
        await col.insert_one(probe)
        found = await col.find_one({"spike": "agent-session"}, {"_id": 0})
        await col.delete_many({"spike": "agent-session"})
        ok = found is not None and found.get("blob") == probe["blob"]
        return {"ok": ok, "installed": True, "version": version, "mongo_roundtrip": "ok" if ok else "mismatch"}
    except Exception as exc:  # noqa: BLE001 - surfaced as JSON for the spike
        return {"ok": False, "installed": True, "version": version, "mongo_roundtrip": type(exc).__name__}
