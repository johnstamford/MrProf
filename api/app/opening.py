"""F13-min: opening gates (invite code, consent) read from the environment.

- PUBLIC_INVITE_CODE: when set (non-empty), creating an assessment
  requires the matching invite code. The 2-day opening runs with a code;
  local dev runs without one.
- REQUIRE_CONSENT=1: creating an assessment requires explicit consent
  (consent_accepted + current CONSENT_VERSION). The web UI always sends
  it; the server enforces it when the opening flag is on.
"""

from __future__ import annotations

import hmac
import os


def invite_required() -> bool:
    return bool((os.environ.get("PUBLIC_INVITE_CODE") or "").strip())


def check_invite(provided: str | None) -> bool:
    """True when no code is configured, or the provided code matches."""
    expected = (os.environ.get("PUBLIC_INVITE_CODE") or "").strip()
    if not expected:
        return True
    return hmac.compare_digest((provided or "").strip(), expected)


def consent_required() -> bool:
    return (os.environ.get("REQUIRE_CONSENT") or "").strip() == "1"
