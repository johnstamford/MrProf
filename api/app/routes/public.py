"""F13-min public endpoints: consent text and opening config (no auth)."""

from fastapi import APIRouter

from ..consent import CONSENT_VERSION, build_consent
from ..llm import load_config
from ..opening import consent_required, invite_required

router = APIRouter(tags=["public"])


@router.get("/consent")
async def get_consent() -> dict:
    """Single source of truth for consent wording + configured model."""
    cfg = load_config()
    return build_consent(cfg.provider, cfg.model)


@router.get("/config")
async def get_config() -> dict:
    """What the start page must ask for: invite code and consent gates."""
    return {
        "invite_required": invite_required(),
        "consent_required": consent_required(),
        "consent_version": CONSENT_VERSION,
    }
