"""MongoDB access. The database is the durable source of truth."""

import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://mongo:27017/mrprof")
MONGODB_DB = os.environ.get("MONGODB_DB", "mrprof")

_client: AsyncIOMotorClient | None = None


def get_db(name: str | None = None) -> AsyncIOMotorDatabase:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    return _client[name or MONGODB_DB]
