"""Feature 8: synthetic patient profiles (SPIT-shaped, hand-authored draft set).

Four personas covering the required behaviors: vague answers, denials,
contradictions, incomplete recall, and alternative explanations. Each
profile carries ground-truth facts (evaluation-only: never sent to the
interviewer), uncertainty markers that must survive persona extraction,
and scripted answers for the hermetic dummy patient.
"""

PROFILES = [
    {
        "id": "vague-01",
        "label": "Vague short-answer responder",
        "behaviors": ["vague", "short-answers"],
        "screening": ["sometimes", "sometimes", "never", "often", "rarely", "sometimes"],
        "facts": [
            "Often loses track of bills and pays them late.",
            "Describes the mind as busy when trying to rest.",
        ],
        "uncertain": ["Cannot say when these difficulties began."],
        "contradictions": [],
        "style": "Answer briefly, in a few words. Do not elaborate unless asked twice.",
        "script": {
            "attention-tasks": {"answer": "bills, mostly", "basis": "fact:0"},
            "restlessness": {"answer": "busy mind", "basis": "fact:1"},
            "history-course": {"answer": "not sure", "basis": "uncertain"},
            "impact-life": {"answer": "late fees", "basis": "fact:0"},
            "context-factors": {"answer": "dunno", "basis": "behavior:vague"},
            "strategies": {"answer": "phone reminders", "basis": "behavior:vague"},
        },
    },
    {
        "id": "denier-01",
        "label": "Denies difficulties, offers alternative explanation",
        "behaviors": ["denials", "alternative-explanations"],
        "screening": ["never", "rarely", "never", "never", "sometimes", "rarely"],
        "facts": [
            "Reports no real difficulty starting tasks.",
            "Attributes any restlessness to too much coffee and shift work.",
        ],
        "uncertain": [],
        "contradictions": [],
        "style": "Deny difficulties plainly where you have none. Attribute restlessness to coffee and shifts.",
        "script": {
            "attention-tasks": {"answer": "No, starting tasks is fine for me.", "basis": "fact:0"},
            "restlessness": {"answer": "Just coffee and night shifts, nothing else.", "basis": "fact:1"},
            "history-course": {"answer": "Nothing to look back on, really.", "basis": "behavior:denial"},
            "impact-life": {"answer": "No, work is fine.", "basis": "behavior:denial"},
            "context-factors": {"answer": "Coffee makes it worse, that is all.", "basis": "fact:1"},
            "strategies": {"answer": "Do not need any.", "basis": "behavior:denial"},
        },
    },
    {
        "id": "contradictor-01",
        "label": "Gives conflicting accounts across turns",
        "behaviors": ["contradictions", "vague"],
        "screening": ["often", "sometimes", "often", "sometimes", "never", "rarely"],
        "facts": [
            "Says school was never a problem (turn 3).",
            "Later describes repeating a year after missing coursework (turn 4).",
        ],
        "uncertain": ["Unsure whether childhood was affected."],
        "contradictions": [[0, 1]],
        "style": "Answer each question on its own; do not reconcile with earlier answers.",
        "script": {
            "attention-tasks": {"answer": "I miss deadlines at work quite a lot.", "basis": "behavior:vague"},
            "restlessness": {"answer": "I fidget in long meetings.", "basis": "behavior:vague"},
            "history-course": {"answer": "School was never a problem.", "basis": "fact:0"},
            "impact-life": {"answer": "I actually repeated a year after missing coursework.", "basis": "fact:1"},
            "context-factors": {"answer": "Not sure about childhood.", "basis": "uncertain"},
            "strategies": {"answer": "Lists, sometimes.", "basis": "behavior:vague"},
        },
    },
    {
        "id": "recall-01",
        "label": "Incomplete recall with partial detail",
        "behaviors": ["incomplete-recall", "uncertain"],
        "screening": ["sometimes", "often", "sometimes", "rarely", "never", "sometimes"],
        "facts": [
            "Remembers a teacher commenting on daydreaming, but not when.",
            "Current work impact is clear: missed two team deadlines this month.",
        ],
        "uncertain": ["Cannot recall when the teacher comment happened.", "Cannot recall duration."],
        "contradictions": [],
        "style": "Give partial detail where you have it; say plainly what you cannot recall. Never invent dates.",
        "script": {
            "attention-tasks": {"answer": "Missing team deadlines this month, two of them.", "basis": "fact:1"},
            "restlessness": {"answer": "Not really an issue for me.", "basis": "behavior:denial"},
            "history-course": {
                "answer": "A teacher said I daydreamed, but I cannot recall when.",
                "basis": "uncertain",
            },
            "impact-life": {"answer": "Those two missed deadlines caused a formal warning.", "basis": "fact:1"},
            "context-factors": {"answer": "Poor sleep makes it worse, I think.", "basis": "behavior:vague"},
            "strategies": {"answer": "Calendar blocks, they help a bit.", "basis": "behavior:vague"},
        },
    },
]


def get_profile(profile_id: str) -> dict:
    for p in PROFILES:
        if p["id"] == profile_id:
            return p
    raise KeyError(f"unknown profile {profile_id!r}; known: {[p['id'] for p in PROFILES]}")
