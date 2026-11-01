"""F13-min: consent text for the bounded 2-day real-user opening.

Single source of truth served by GET /consent; the web /consent page
renders from the API so wording and version cannot drift. Interim
wording for a research prototype — full privacy review stays
post-hackathon (F13 full).
"""

from __future__ import annotations

CONSENT_VERSION = "2026-11-01-v1"

SECTIONS: tuple[dict[str, str], ...] = (
    {
        "heading": "What is collected",
        "body": (
            "Your 6 screening answers, your interview answers in your own words, "
            "and the two reports generated from them (screening summary and "
            "evidence briefing with exact quotes). Your assessment code and a "
            "password hash are stored so you can resume; the password itself is "
            "never stored."
        ),
    },
    {
        "heading": "Where it goes and who can access it",
        "body": (
            "Answers travel to this project's backend and database on the "
            "operator's machine, and to the configured language-model provider "
            "to phrase interview questions and extract evidence. Only you can "
            "open your assessment (code plus password); the operator can see "
            "stored records for maintenance and deletion. There are no accounts "
            "and no password reset — lose the code or password and the "
            "assessment cannot be retrieved."
        ),
    },
    {
        "heading": "No monitoring",
        "body": (
            "No one reviews your answers in real time and this project offers "
            "no crisis support. If you feel unsafe, contact your local "
            "emergency number or a crisis helpline directly; you can stop the "
            "interview at any time."
        ),
    },
    {
        "heading": "Retention and deletion",
        "body": (
            "Records are kept until you delete them: with your code and "
            "password you can delete the assessment and all linked records "
            "(transcript, evidence, reports). The operator wipes the database "
            "when the short opening ends. Nothing you enter is committed to "
            "source control, analytics, or logs."
        ),
    },
    {
        "heading": "Research prototype, not clinical",
        "body": (
            "MrProf organizes what you report so a clinician can review it. "
            "It does not diagnose, rule anything out, or estimate probabilities. "
            "Topics and evidence codes are drafts and have not been clinically "
            "reviewed. A synthetic example briefing is available without "
            "entering anything about yourself."
        ),
    },
)


def build_consent(provider: str, model: str) -> dict:
    """Consent payload naming the actual configured model endpoint."""
    return {
        "version": CONSENT_VERSION,
        "provider": provider,
        "model": model or "dummy-stub",
        "model_note": (
            "Interview questions are phrased by this model through an "
            "OpenAI-compatible endpoint; your answers are sent to it for that "
            "purpose. Credentials stay server-side."
        ),
        "sections": list(SECTIONS),
    }
