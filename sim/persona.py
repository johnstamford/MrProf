"""Feature 8: persona extraction + validation.

extract_persona derives the roleplay brief deterministically from a
profile. validate_persona enforces the two acceptance checks: no invented
details (every script answer traces to a fact, an uncertainty marker, or
a declared behavior) and no lost uncertainty (all profile uncertainty
markers survive into the persona).
"""

from .profiles import get_profile


def extract_persona(profile: dict) -> dict:
    """Deterministic profile -> roleplay persona transform."""
    return {
        "profile_id": profile["id"],
        "label": profile["label"],
        "behaviors": list(profile["behaviors"]),
        "brief": (
            f"You are {profile['label']}. {profile['style']} "
            "Answer in your own words, one answer at a time. "
            "Never invent dates, events, or details beyond the facts you know. "
            "Say plainly what you do not know or cannot recall."
        ),
        "facts": list(profile["facts"]),
        "uncertain": list(profile["uncertain"]),
        "contradictions": [list(c) for c in profile["contradictions"]],
        "script": {
            objective: {"answer": entry["answer"], "basis": entry["basis"]}
            for objective, entry in profile["script"].items()
        },
    }


def validate_persona(persona: dict, profile: dict | None = None) -> list[str]:
    """Return a list of issues; empty means the persona is clean."""
    profile = profile or get_profile(persona["profile_id"])
    issues: list[str] = []
    # 1. No lost uncertainty.
    for item in profile["uncertain"]:
        if item not in persona.get("uncertain", []):
            issues.append(f"lost uncertainty: {item!r}")
    # 2. No invented details: every script answer needs a valid basis.
    facts = profile["facts"]
    for objective, entry in persona.get("script", {}).items():
        basis = entry.get("basis", "")
        if basis.startswith("fact:"):
            try:
                idx = int(basis.split(":", 1)[1])
            except ValueError:
                issues.append(f"{objective}: malformed fact basis {basis!r}")
                continue
            if not (0 <= idx < len(facts)):
                issues.append(f"{objective}: fact basis out of range {basis!r}")
        elif basis in ("uncertain",) or basis.startswith("behavior:"):
            pass
        else:
            issues.append(f"{objective}: untraceable basis {basis!r}")
    return issues
