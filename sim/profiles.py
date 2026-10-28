"""Feature 8/9: synthetic patient profiles (SPIT-shaped, hand-authored draft set).

Four personas covering the required behaviors: vague answers, denials,
contradictions, incomplete recall, and alternative explanations. Each
profile carries ground-truth facts (evaluation-only: never sent to the
interviewer), uncertainty markers that must survive persona extraction,
and scripted answers for the hermetic dummy patient.

Scripted answers are written the way a real person types: full sentences,
a few per answer, with natural hedging and asides. Vagueness is expressed
through missing specifics (no dates, no numbers, drifting off-topic), not
through fragments. Keys match topics v0.3 objectives.
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
            "Loses the thread of conversations and drifts off.",
            "Fidgets with pens and phone when made to sit through things.",
        ],
        "uncertain": ["Cannot say when these difficulties began."],
        "contradictions": [],
        "style": (
            "Answer in full sentences, the way you would talk to someone — a few "
            "sentences each time. Stay vague about specifics: hedge, drift slightly "
            "off-topic, never give dates or numbers. Do not answer in fragments."
        ),
        "script": {
            "attention-focus": {
                "answer": (
                    "I lose the thread of things quite a lot, like someone will be "
                    "talking and I realise I missed the middle bit. It is worse when "
                    "there is background noise or I am tired, though I could not really "
                    "say by how much."
                ),
                "basis": "fact:2",
            },
            "organization": {
                "answer": (
                    "My way of organizing things is mostly piles — piles of post, piles "
                    "of tabs open, that sort of thing. Every so often I have a big "
                    "sort-out and it feels great for about a week."
                ),
                "basis": "behavior:vague",
            },
            "task-completion": {
                "answer": (
                    "Honestly it is mostly bills and that kind of paperwork. I put the "
                    "envelopes on the counter meaning to deal with them, and then somehow "
                    "it is weeks later and there is a late fee. It just never quite feels "
                    "like the right moment to sit down with them."
                ),
                "basis": "fact:0",
            },
            "forgetfulness": {
                "answer": (
                    "I am always hunting for my keys or my glasses, that kind of thing. "
                    "They turn up in silly places. I do not know if that is worse than "
                    "average or everyone does it."
                ),
                "basis": "behavior:vague",
            },
            "restlessness": {
                "answer": (
                    "When I am trying to wind down at night my mind just stays busy, going "
                    "over random stuff from the day. I will be lying there thinking about an "
                    "email I forgot to send or something someone said, and then suddenly it "
                    "is really late."
                ),
                "basis": "fact:1",
            },
            "impulsivity": {
                "answer": (
                    "I suppose I can be a bit quick to jump in, especially when I am "
                    "excited about something. Whether that is more than most people, I "
                    "could not really say."
                ),
                "basis": "behavior:vague",
            },
            "childhood-onset": {
                "answer": (
                    "I do not really remember much about school in that way. I got through "
                    "it, I think my reports were fine, but I could not tell you anything "
                    "specific about what I was like."
                ),
                "basis": "uncertain",
            },
            "persistence-course": {
                "answer": (
                    "I really could not say when this started or whether it has changed. "
                    "It feels like it has just always been like this, but if you asked me "
                    "to point to a year or how old I was, I genuinely cannot."
                ),
                "basis": "uncertain",
            },
            "settings": {
                "answer": (
                    "It is probably a bit of everything, home and out and about. I have "
                    "never really compared, to be honest. It is just there in the background."
                ),
                "basis": "behavior:vague",
            },
            "impact-work": {
                "answer": (
                    "Work is mostly okay, though the odd thing slips. Nothing dramatic, "
                    "just the occasional missed email or turning up flustered. I muddle through."
                ),
                "basis": "behavior:vague",
            },
            "impact-relationships": {
                "answer": (
                    "I think people notice I drift off sometimes. Nobody has made a big "
                    "thing of it. My sister teases me about never listening, but that is "
                    "just sisters, probably."
                ),
                "basis": "fact:2",
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
            "background-goals": {
                "answer": (
                    "I am here because I keep wondering about it, really. Nobody sent me, "
                    "I just thought it was worth looking into. I do not know what happens "
                    "next, I have never done anything like this before."
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
            "attention-focus": {
                "answer": (
                    "No, concentrating is fine for me. I can read a long report or sit "
                    "through a film without any trouble. This has never been an issue."
                ),
                "basis": "fact:0",
            },
            "organization": {
                "answer": (
                    "No, organization is not a problem for me. Everything has its place "
                    "and I keep a tidy calendar. People at work comment on it."
                ),
                "basis": "behavior:denial",
            },
            "task-completion": {
                "answer": (
                    "No, starting tasks is honestly fine for me. Once I decide to do "
                    "something I just get on with it. I have never really had that problem "
                    "people talk about with staring at a task and not beginning."
                ),
                "basis": "fact:0",
            },
            "forgetfulness": {
                "answer": (
                    "No, I rarely forget things. Keys, wallet, phone — I always know where "
                    "they are. My memory is perfectly good."
                ),
                "basis": "behavior:denial",
            },
            "restlessness": {
                "answer": (
                    "If I am restless it is the coffee, honestly. I am on about four or "
                    "five cups on a night shift and then I wonder why I am bouncing my leg. "
                    "That is a lifestyle thing, not anything else."
                ),
                "basis": "fact:1",
            },
            "impulsivity": {
                "answer": (
                    "No, I am a patient person. I wait my turn and think before I speak. "
                    "Nobody would call me impulsive."
                ),
                "basis": "behavior:denial",
            },
            "childhood-onset": {
                "answer": (
                    "No, nothing was ever flagged at school. Good reports, no complaints, "
                    "nothing anyone ever raised. There is nothing to dig up there."
                ),
                "basis": "behavior:denial",
            },
            "persistence-course": {
                "answer": (
                    "No, there is no course to describe, because there has never been a "
                    "problem. Things have been steady all along."
                ),
                "basis": "behavior:denial",
            },
            "settings": {
                "answer": (
                    "No difference anywhere. Home, work, out with friends — all the same, "
                    "all fine."
                ),
                "basis": "behavior:denial",
            },
            "impact-work": {
                "answer": (
                    "No, work is fine, my reviews have always been decent. Nothing is "
                    "falling through the cracks as far as I can tell, and nobody has ever "
                    "suggested otherwise."
                ),
                "basis": "behavior:denial",
            },
            "impact-relationships": {
                "answer": (
                    "No, my relationships are good. No complaints from anyone. We get on "
                    "well and I am present when it matters."
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
            "background-goals": {
                "answer": (
                    "Honestly I am mostly here because my partner suggested it. I do not "
                    "have goals as such — I expect to be told there is nothing to find. No "
                    "previous assessments, nothing in the family that I know of."
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
            "Says school was never a problem (childhood).",
            "Later describes repeating a year after missing coursework (work impact).",
            "Fidgets in long meetings.",
        ],
        "uncertain": ["Unsure whether childhood was affected."],
        "contradictions": [[0, 1]],
        "style": (
            "Answer in full sentences, a few per answer. Answer each question on its "
            "own; do not try to reconcile with earlier answers."
        ),
        "script": {
            "attention-focus": {
                "answer": (
                    "I zone out in the middle of things more than I would like. Someone "
                    "will be explaining something and I will realise I only caught half of "
                    "it. It is embarrassing when they notice."
                ),
                "basis": "behavior:vague",
            },
            "organization": {
                "answer": (
                    "Organizing things is not my strong point. I have tried planners and "
                    "apps and they work until I forget to open them, which takes about "
                    "three days."
                ),
                "basis": "behavior:vague",
            },
            "task-completion": {
                "answer": (
                    "At work I miss deadlines more than I would like to admit. Someone "
                    "will ask where a report is and I will realise I never even started it, "
                    "even though I meant to all week."
                ),
                "basis": "behavior:vague",
            },
            "forgetfulness": {
                "answer": (
                    "I forget stupid little things all the time — why I walked into a room, "
                    "where I put my phone while I am holding it. It drives my partner mad."
                ),
                "basis": "behavior:vague",
            },
            "restlessness": {
                "answer": (
                    "In long meetings I fidget quite a lot, clicking pens and shifting "
                    "about in my chair. An hour sat still feels endless to me."
                ),
                "basis": "fact:2",
            },
            "impulsivity": {
                "answer": (
                    "I do jump in a bit. If I have the answer I will just say it rather than "
                    "waiting. Sometimes that lands badly and I wish I had held back."
                ),
                "basis": "behavior:vague",
            },
            "childhood-onset": {
                "answer": (
                    "School was never a problem. I got through it like everyone else, and "
                    "I do not remember any big issues with teachers or grades back then."
                ),
                "basis": "fact:0",
            },
            "persistence-course": {
                "answer": (
                    "Over the years it has been up and down, I think. Some jobs it was "
                    "worse, some stretches were okay. I could not map it out exactly, but "
                    "it has definitely been there a long time."
                ),
                "basis": "behavior:vague",
            },
            "settings": {
                "answer": (
                    "It is worst at work, where there are deadlines and people watching. "
                    "At home it matters less, though the flat is chaos. So it shows up "
                    "differently depending on the pressure."
                ),
                "basis": "behavior:vague",
            },
            "impact-work": {
                "answer": (
                    "Actually, I repeated a year after missing so much coursework that "
                    "they held me back. I had sort of forgotten about that until now. A "
                    "whole year gone, because I just had not handed things in."
                ),
                "basis": "fact:1",
            },
            "impact-relationships": {
                "answer": (
                    "My partner says I do not listen, and they are probably right. I will "
                    "nod along and then have no idea what was agreed. We argue about it "
                    "more than I would like."
                ),
                "basis": "behavior:vague",
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
            "background-goals": {
                "answer": (
                    "I am here because work suggested an assessment after the missed "
                    "deadlines piled up. I want to know what is going on, and whether "
                    "there is anything that actually helps."
                ),
                "basis": "fact:1",
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
            "Keeps losing keys around the house.",
        ],
        "uncertain": ["Cannot recall when the teacher comment happened.", "Cannot recall duration."],
        "contradictions": [],
        "style": (
            "Answer in full sentences, a few per answer. Give partial detail where you "
            "have it; say plainly what you cannot recall. Never invent dates."
        ),
        "script": {
            "attention-focus": {
                "answer": (
                    "I drift off in the middle of conversations, especially on calls. I will "
                    "realise I have no idea what was just decided and have to ask someone "
                    "afterwards, which is awkward."
                ),
                "basis": "behavior:vague",
            },
            "organization": {
                "answer": (
                    "My system is basically organised chaos. I know where most things are, "
                    "but nobody else could find anything. It falls apart whenever I am busy."
                ),
                "basis": "behavior:vague",
            },
            "task-completion": {
                "answer": (
                    "This month alone I have missed two team deadlines, which is pretty "
                    "bad. Both times I knew exactly what I had to do, I just kept putting "
                    "off starting until there was not enough time left."
                ),
                "basis": "fact:1",
            },
            "forgetfulness": {
                "answer": (
                    "Keys are the big one — I lose them around the house constantly. I have "
                    "a bowl by the door that is supposed to fix it, and half the time the "
                    "keys are anywhere but the bowl."
                ),
                "basis": "fact:2",
            },
            "restlessness": {
                "answer": (
                    "That is not really an issue for me. I can sit still fine, I do not "
                    "fidget or feel wired. It is more the getting-started side that is "
                    "the problem."
                ),
                "basis": "behavior:denial",
            },
            "impulsivity": {
                "answer": (
                    "I do not think I am impulsive. I mull things over, sometimes too much — "
                    "that is half the problem with starting. Deciding takes me ages."
                ),
                "basis": "behavior:vague",
            },
            "childhood-onset": {
                "answer": (
                    "I do remember a teacher saying I daydreamed in class, but I could not "
                    "tell you when that was or how old I was. It might have been primary "
                    "school. Honestly, I cannot recall."
                ),
                "basis": "uncertain",
            },
            "persistence-course": {
                "answer": (
                    "I cannot say how long this has been going on. The work stuff is recent "
                    "and clear, but before that it is all a blur. I cannot recall any "
                    "duration, really."
                ),
                "basis": "uncertain",
            },
            "settings": {
                "answer": (
                    "Work is where it shows, because there are deadlines and witnesses. At "
                    "home nobody is keeping score, so it matters less, though the flat "
                    "shows it."
                ),
                "basis": "fact:1",
            },
            "impact-work": {
                "answer": (
                    "Those two missed deadlines this month led to a formal warning at work, "
                    "so it is serious now. My manager basically said it cannot happen again, "
                    "which is fair enough."
                ),
                "basis": "fact:1",
            },
            "impact-relationships": {
                "answer": (
                    "I do not think it affects my relationships much. My friends know I am "
                    "flaky about replying to messages, but nobody has ever made a thing of it."
                ),
                "basis": "behavior:vague",
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
            "background-goals": {
                "answer": (
                    "I am here because of the warning at work — I need to understand what "
                    "is going on before it gets worse. Nobody in my family has been through "
                    "anything like this as far as I know."
                ),
                "basis": "fact:1",
            },
        },
    },
]


def get_profile(profile_id: str) -> dict:
    for p in PROFILES:
        if p["id"] == profile_id:
            return p
    raise KeyError(f"unknown profile {profile_id!r}; known: {[p['id'] for p in PROFILES]}")
