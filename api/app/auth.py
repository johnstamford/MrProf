"""Assessment identity: unguessable IDs, single-use display secrets, bcrypt hashes.

IDs are lookup keys, never authorization. Every protected endpoint must call
`require_assessment` — a valid ID with a wrong/missing secret gets a 401,
an unknown ID a 404.
"""

import secrets

import bcrypt

ID_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/l: typable codes
ID_LENGTH = 8  # 31^8 ≈ 852B: not practically enumerable, still human-usable
ID_ATTEMPTS = 10

MIN_PASSWORD_LEN = 10


def new_assessment_id() -> str:
    return "".join(secrets.choice(ID_ALPHABET) for _ in range(ID_LENGTH))


def hash_secret(secret: str) -> str:
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt()).decode()


def verify_secret(secret: str, secret_hash: str) -> bool:
    try:
        return bcrypt.checkpw(secret.encode(), secret_hash.encode())
    except (ValueError, TypeError):
        return False
