"""Assessment identity: unguessable IDs, single-use display secrets, bcrypt hashes.

IDs are lookup keys, never authorization. Every protected endpoint must call
`require_assessment` — a valid ID with a wrong/missing secret gets a 401,
an unknown ID a 404.
"""

import secrets

import bcrypt

ID_PREFIX = "a_"


def new_assessment_id() -> str:
    return ID_PREFIX + secrets.token_urlsafe(16)


def new_access_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_secret(secret: str) -> str:
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()


def verify_secret(secret: str, secret_hash: str) -> bool:
    try:
        return bcrypt.checkpw(secret.encode(), secret_hash.encode())
    except (ValueError, TypeError):
        return False
