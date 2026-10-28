"""Feature 8: synthetic patient profiles (SPIT-shaped, hand-authored draft set).

Four personas covering the required behaviors: vague answers, denials,
contradictions, incomplete recall, and alternative explanations. Each
profile carries ground-truth facts (evaluation-only: never sent to the
interviewer), uncertainty markers that must survive persona extraction,
and scripted answers for the hermetic dummy patient.

Scripted answers are written the way a real person types: full sentences,
a few sentences per answer, with natural hedging and asides. Vagueness is
expressed through missing specifics (no dates, no numbers, drifting
off-topic), not through fragments — one-word answers would be rejected
by a real interview as too thin, so the simulator must not produce them
except where the behavior under test demands brevity.
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
        "style": (
            "Answer in full sentences, the way you would talk to someone — a few "
            "sentences each time. Stay vague about specifics: hedge, drift slightly "
            "off-topic, never give dates or numbers. Do not answer in fragments."
        ),
        "script": {
            "attention-tasks": {
                "answer": (
                    "Honestly it is mostly bills and that kind of paperwork. I put the "
                    "envelopes on the counter meaning to deal with them, and then somehow "
                    "it is weeks later and there is a late fee. It just never quite feels "
                    "like the right moment to sit down with them."
                ),
                "basis": "fact:0",
            },
            "restlessness": {
                "answer": (
                    "When I am trying to wind down at night my mind just stays busy, going "
                    "over random stuff from the day. I will be lying there thinking about "
                    "an email I forgot to send or something someone said, and then suddenly "
                    "it is really late."
                ),
                "basis": "fact:1",
            },
            "history-course": {
                "answer": (
                    "I really could not say when this started. It feels like it has just "
                    "always been like this, but if you asked me to point to a year or how "
                    "old I was, I genuinely cannot."
                ),
                "basis": "uncertain",
            },
            "impact-life": {
                "answer": (
                    "The late fees are the main thing, that is real money going out the "
                    "door for no reason. And then I feel bad about it, which somehow makes "
                    "it harder to open the next lot. It is a bit of a cycle."
                ),
                "basis": "fact:0",
            },
            "context-factors": {
                "answer": (
                    "My sleep is a bit all over the place, I suppose that does not help. "
                    "I could not really tell you how much of it is tiredness and how much "
                    "is just me, though."
                ),
                "basis": "behavior:vague",
            },
            "strategies": {
                "answer": (
                    "I have got phone reminders set for most things, which sort of works "
                    "when I actually look at them. Sometimes I just swipe them away and "
                    "forget anyway, so it is hit and miss."
                ),
                "basis": "behavior:vague",
            },
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
        "style": (
            "Answer in full sentences, a few per answer. Deny difficulties plainly "
            "where you have none. Attribute restlessness to coffee and night shifts."
        ),
        "script": {
            "attention-tasks": {
                "answer": (
                    "No, starting tasks is honestly fine for me. Once I decide to do "
                    "something I just get on with it. I have never really had that problem "
                    "people talk about with staring at a task and not beginning."
                ),
                "basis": "fact:0",
            },
            "restlessness": {
                "answer": (
                    "If I am restless it is the coffee, honestly. I am on about four or "
                    "five cups on a night shift and then I wonder why I am bouncing my leg. "
                    "That is a lifestyle thing, not anything else."
                ),
                "basis": "fact:1",
            },
            "history-course": {
                "answer": (
                    "There is nothing to look back on really, school and work have both "
                    "been fine. I cannot point to any period where this was an issue, "
                    "because there was not one."
                ),
                "basis": "behavior:denial",
            },
            "impact-life": {
                "answer": (
                    "No, work is fine, my reviews have always been decent. Nothing is "
                    "falling through the cracks as far as I can tell, and nobody has ever "
                    "suggested otherwise."
                ),
                "basis": "behavior:denial",
            },
            "context-factors": {
                "answer": (
                    "Like I said, it is the coffee and the shifts. When I am on days and "
                    "ease off the caffeine I am perfectly calm, so that tells me all I "
                    "need to know."
                ),
                "basis": "fact:1",
            },
            "strategies": {
                "answer": (
                    "I do not really use anything, no lists or reminders. I just remember "
                    "things. It has never been an issue, so I have never needed a system."
                ),
                "basis": "behavior:denial",
            },
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
        "style": (
            "Answer in full sentences, a few per answer. Answer each question on its "
            "own; do not reconcile with earlier answers."
        ),
        "script": {
            "attention-tasks": {
                "answer": (
                    "At work I miss deadlines more than I would like to admit. Someone "
                    "will ask where a report is and I will realise I never even started it, "
                    "even though I meant to all week."
                ),
                "basis": "behavior:vague",
            },
            "restlessness": {
                "answer": (
                    "In long meetings I fidget quite a lot, clicking pens and shifting "
                    "about in my chair. An hour sat still feels endless to me."
                ),
                "basis": "behavior:vague",
            },
            "history-course": {
                "answer": (
                    "School was never a problem. I got through it like everyone else, and "
                    "I do not remember any big issues with teachers or grades back then."
                ),
                "basis": "fact:0",
            },
            "impact-life": {
                "answer": (
                    "Actually, I repeated a year after missing so much coursework that "
                    "they held me back. I had sort of forgotten about that until now. A "
                    "whole year gone, because I just had not handed things in."
                ),
                "basis": "fact:1",
            },
            "context-factors": {
                "answer": (
                    "Whether any of this goes back to childhood, I am not sure. I honestly "
                    "cannot say if I was like this as a kid or if it started later."
                ),
                "basis": "uncertain",
            },
            "strategies": {
                "answer": (
                    "I try keeping lists, and they help for a day or two. Then I lose the "
                    "list, or stop looking at it, and I am back where I started."
                ),
                "basis": "behavior:vague",
            },
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
        "style": (
            "Answer in full sentences, a few per answer. Give partial detail where you "
            "have it; say plainly what you cannot recall. Never invent dates."
        ),
        "script": {
            "attention-tasks": {
                "answer": (
                    "This month alone I have missed two team deadlines, which is pretty "
                    "bad. Both times I knew exactly what I had to do, I just kept putting "
                    "off starting until there was not enough time left."
                ),
                "basis": "fact:1",
            },
            "restlessness": {
                "answer": (
                    "That is not really an issue for me. I can sit still fine, I do not "
                    "fidget or feel wired. It is more the getting-started side that is "
                    "the problem."
                ),
                "basis": "behavior:denial",
            },
            "history-course": {
                "answer": (
                    "I do remember a teacher saying I daydreamed in class, but I could not "
                    "tell you when that was or how old I was. It might have been primary "
                    "school. Honestly, I cannot recall."
                ),
                "basis": "uncertain",
            },
            "impact-life": {
                "answer": (
                    "Those two missed deadlines this month led to a formal warning at work, "
                    "so it is serious now. My manager basically said it cannot happen again, "
                    "which is fair enough."
                ),
                "basis": "fact:1",
            },
            "context-factors": {
                "answer": (
                    "My sleep has been pretty poor lately and I think that makes everything "
                    "worse. Whether it is the cause or just makes it harder, I do not "
                    "really know."
                ),
                "basis": "behavior:vague",
            },
            "strategies": {
                "answer": (
                    "I block time in my calendar for the boring admin stuff, and that helps "
                    "a bit when I stick to it. Half the time something else comes up and "
                    "the block just gets ignored, though."
                ),
                "basis": "behavior:vague",
            },
        },
    },
]


def get_profile(profile_id: str) -> dict:
    for p in PROFILES:
        if p["id"] == profile_id:
            return p
    raise KeyError(f"unknown profile {profile_id!r}; known: {[p['id'] for p in PROFILES]}")
