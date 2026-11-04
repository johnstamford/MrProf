"""Feature 8/9: synthetic patient profiles (SPIT-shaped, hand-authored draft set).

Four personas covering the required behaviors: vague answers, denials,
contradictions, incomplete recall, and alternative explanations. Each
profile carries ground-truth facts (evaluation-only: never sent to the
interviewer), uncertainty markers that must survive persona extraction,
and scripted answers for the hermetic dummy patient.

Scripted answers are written the way real people type: full sentences of
varying length, hedging, asides, self-corrections. Vagueness is expressed
through missing specifics (no dates, no numbers, drifting off-topic), not
through fragments. Each objective also carries a `followup` variant used
when the interview re-asks the same objective: it elaborates in the same
voice without adding new facts, so frozen demos never repeat a paragraph
verbatim. Keys match topics v0.3 objectives.
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
            "sentences each time, sometimes trailing off. Stay vague about specifics: "
            "hedge, drift slightly off-topic, never give dates or numbers. "
            "Do not answer in fragments."
        ),
        "script": {
            "attention-focus": {
                "answer": (
                    "I lose the thread of things quite a lot, to be honest. Like someone "
                    "will be talking and I realise I missed the middle bit entirely. It is "
                    "worse when there is background noise or I am tired, though I could "
                    "not really say by how much."
                ),
                "followup": (
                    "Sorry, I know that was a bit roundabout. The gist is just that I drift "
                    "off mid-conversation a lot, especially when I am already tired — I do "
                    "not really have a clearer way of putting it than that."
                ),
                "basis": "fact:2",
            },
            "organization": {
                "answer": (
                    "My way of organizing things is mostly piles, really — piles of post on "
                    "the counter, piles of tabs open on my laptop, that sort of thing. Every "
                    "so often I have a big sort-out and it feels great for about a week, "
                    "and then it all slides back."
                ),
                "followup": (
                    "I mean the piles thing mostly works until it does not. I will be "
                    "looking for one specific letter and realise it is somewhere in week "
                    "three of the pile, if that makes sense."
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
                "followup": (
                    "The bills thing is the classic example, yeah. It is not that I do not "
                    "know how to pay them, I just keep not doing it until the reminder "
                    "turns red, and then I feel silly about it."
                ),
                "basis": "fact:0",
            },
            "forgetfulness": {
                "answer": (
                    "I am always hunting for my keys or my glasses, that kind of thing. They "
                    "turn up in silly places — on top of the fridge, in a coat I have not "
                    "worn for weeks. I do not know if that is worse than average or "
                    "everyone does it."
                ),
                "followup": (
                    "The keys thing happens most mornings, honestly. I have tried the bowl "
                    "by the door and everything, but half the time the keys are anywhere "
                    "but the bowl."
                ),
                "basis": "behavior:vague",
            },
            "restlessness": {
                "answer": (
                    "When I am trying to wind down at night my mind just stays busy, going "
                    "over random stuff from the day. I will be lying there thinking about an "
                    "email I forgot to send or something someone said, and then suddenly it "
                    "is really late and I am still awake."
                ),
                "followup": (
                    "It is more the mental busy-ness than tossing and turning, if that "
                    "distinction makes sense. My body is tired but my head just will not "
                    "switch off."
                ),
                "basis": "fact:1",
            },
            "impulsivity": {
                "answer": (
                    "I suppose I can be a bit quick to jump in, especially when I am "
                    "excited about something. Whether that is more than most people, I "
                    "could not really say — nobody has ever pulled me up on it, exactly."
                ),
                "followup": (
                    "Like if I already know the answer I will just blurt it out rather than "
                    "wait my turn. It is not a big deal, just something I notice about myself."
                ),
                "basis": "behavior:vague",
            },
            "childhood-onset": {
                "answer": (
                    "I do not really remember much about school in that way. I got through "
                    "it, I think my reports were fine — probably said something like "
                    "'could try harder', which, well. But I could not tell you anything "
                    "specific about what I was like back then."
                ),
                "followup": (
                    "I have asked my mum about it before and even she just says I was "
                    "'lively'. That could mean anything, could it not? I genuinely cannot "
                    "recall specifics."
                ),
                "basis": "uncertain",
            },
            "persistence-course": {
                "answer": (
                    "I really could not say when this started or whether it has changed. It "
                    "feels like it has just always been like this, but if you asked me to "
                    "point to a year or how old I was, I genuinely cannot."
                ),
                "followup": (
                    "It is one of those things where you cannot tell if it got worse or you "
                    "just notice it more now. Sorry, I know that is not very helpful."
                ),
                "basis": "uncertain",
            },
            "settings": {
                "answer": (
                    "It is probably a bit of everything, home and out and about. I have "
                    "never really compared, to be honest. It is just there in the background "
                    "wherever I am."
                ),
                "followup": (
                    "If I had to pick, maybe it is a bit worse out of the house, where there "
                    "is more going on. At home I can at least leave the piles where they are."
                ),
                "basis": "behavior:vague",
            },
            "impact-work": {
                "answer": (
                    "Work is mostly okay, though the odd thing slips. The occasional missed "
                    "email or turning up flustered because I left late again. I muddle "
                    "through, and nobody has had a serious word with me about it."
                ),
                "followup": (
                    "Nothing dramatic at work, just low-level scruffiness. I get the job done "
                    "but it is never as smooth as it looks from the outside, if I am honest."
                ),
                "basis": "behavior:vague",
            },
            "impact-relationships": {
                "answer": (
                    "I think people notice I drift off sometimes. Nobody has made a big "
                    "thing of it. My sister teases me about never listening, but that is "
                    "just sisters, probably."
                ),
                "followup": (
                    "My sister is the only one who really mentions it, and she is joking — "
                    "mostly. I do wonder sometimes if friends notice more than they say."
                ),
                "basis": "fact:2",
            },
            "context-factors": {
                "answer": (
                    "My sleep is a bit all over the place, I suppose that does not help. I "
                    "could not really tell you how much of it is tiredness and how much is "
                    "just me, though. They all blur together."
                ),
                "followup": (
                    "Bad nights definitely make the next day worse, that much I can say. "
                    "But the underlying stuff is there even when I have slept fine, I think."
                ),
                "basis": "behavior:vague",
            },
            "strategies": {
                "answer": (
                    "I have got phone reminders set for most things, which sort of works "
                    "when I actually look at them. Sometimes I just swipe them away and "
                    "forget anyway, so it is hit and miss."
                ),
                "followup": (
                    "The reminders that work best are the really annoying ones I cannot "
                    "swipe away easily. Anything polite I just dismiss without thinking."
                ),
                "basis": "behavior:vague",
            },
            "background-goals": {
                "answer": (
                    "I am here because I keep wondering about it, really. Nobody sent me, "
                    "I just thought it was worth looking into. I do not know what happens "
                    "next — I have never done anything like this before, so be gentle with me."
                ),
                "followup": (
                    "I suppose what I want is just to understand whether this is a thing "
                    "with a name or just how I am. Either answer would be useful, honestly."
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
            "Answer in full sentences, a few per answer — brisk and matter-of-fact. "
            "Deny difficulties plainly where you have none. Attribute restlessness "
            "to coffee and night shifts. Do not hedge what you are sure about."
        ),
        "script": {
            "attention-focus": {
                "answer": (
                    "No, concentrating is fine for me. I can read a long report or sit "
                    "through a film without any trouble at all. This has honestly never "
                    "been an issue in my life."
                ),
                "followup": (
                    "Really, focus is one of my stronger suits. Give me something boring and "
                    "I will still get through it — it has never felt like effort."
                ),
                "basis": "fact:0",
            },
            "organization": {
                "answer": (
                    "No, organization is not a problem for me. Everything has its place "
                    "and I keep a tidy calendar. People at work actually comment on it, "
                    "which always makes me laugh given why I am here."
                ),
                "followup": (
                    "I will die on this hill: my systems work. Inbox zero most Fridays, "
                    "keys on the hook by the door. It is just how I operate."
                ),
                "basis": "behavior:denial",
            },
            "task-completion": {
                "answer": (
                    "No, starting tasks is honestly fine for me. Once I decide to do "
                    "something I just get on with it. I have never really had that problem "
                    "people talk about where you stare at a task and cannot begin."
                ),
                "followup": (
                    "Starting has never been the issue, finishing either. I am a just-do-it "
                    "person, for better or worse — sometimes I start things I should not."
                ),
                "basis": "fact:0",
            },
            "forgetfulness": {
                "answer": (
                    "No, I rarely forget things. Keys, wallet, phone — I always know where "
                    "they are. My memory is perfectly good, ask anyone who knows me."
                ),
                "followup": (
                    "I genuinely cannot remember the last time I lost something important. "
                    "It is just not something that happens to me."
                ),
                "basis": "behavior:denial",
            },
            "restlessness": {
                "answer": (
                    "If I am restless it is the coffee, honestly. I am on about four or "
                    "five cups on a night shift and then I wonder why I am bouncing my leg. "
                    "That is a lifestyle thing, not anything else."
                ),
                "followup": (
                    "Like I said — cut the coffee on my days off and I am perfectly calm. "
                    "That tells me everything I need to know about where the jitters come from."
                ),
                "basis": "fact:1",
            },
            "impulsivity": {
                "answer": (
                    "No, I am a patient person. I wait my turn and think before I speak. "
                    "Nobody who knows me would call me impulsive, I am fairly confident of that."
                ),
                "followup": (
                    "If anything I am too cautious. I will sit on a decision for a week where "
                    "other people would just go for it."
                ),
                "basis": "behavior:denial",
            },
            "childhood-onset": {
                "answer": (
                    "No, nothing was ever flagged at school. Good reports, no complaints, "
                    "nothing anyone ever raised. There is genuinely nothing to dig up there — "
                    "I was a boringly normal kid that way."
                ),
                "followup": (
                    "I even asked my parents before coming here, and they laughed. No detentions, "
                    "no concerned teachers, nothing. School was smooth sailing."
                ),
                "basis": "behavior:denial",
            },
            "persistence-course": {
                "answer": (
                    "No, there is no course to describe, because there has never been a "
                    "problem. Things have been steady all along — same person at fifteen "
                    "as at thirty, more or less."
                ),
                "followup": (
                    "Steady is the word. No ups and downs to report, nothing that started or "
                    "stopped. I know that is probably not what this questionnaire wants to hear."
                ),
                "basis": "behavior:denial",
            },
            "settings": {
                "answer": (
                    "No difference anywhere. Home, work, out with friends — all the same, "
                    "all fine. I do not have a 'bad setting' because there is nothing going wrong."
                ),
                "followup": (
                    "Same everywhere, like I said. I am consistent, I will give myself that much."
                ),
                "basis": "behavior:denial",
            },
            "impact-work": {
                "answer": (
                    "No, work is fine, my reviews have always been decent. Nothing is "
                    "falling through the cracks as far as I can tell, and nobody has ever "
                    "suggested otherwise. My manager would tell me straight."
                ),
                "followup": (
                    "Exceeds expectations two years running, for what it is worth. Whatever "
                    "this assessment is looking for, it is not showing up in my appraisals."
                ),
                "basis": "behavior:denial",
            },
            "impact-relationships": {
                "answer": (
                    "No, my relationships are good. No complaints from anyone. We get on "
                    "well and I am present when it matters — birthdays remembered, promises kept."
                ),
                "followup": (
                    "Honestly my partner would be the first to tell you if I was checked out. "
                    "They are not shy like that. All good on that front."
                ),
                "basis": "behavior:denial",
            },
            "context-factors": {
                "answer": (
                    "Like I said, it is the coffee and the shifts. When I am on days and "
                    "ease off the caffeine I am perfectly calm, so that tells me all I "
                    "need to know. Fix the rota and the espresso and there is nothing left."
                ),
                "followup": (
                    "I even did the experiment — one week decaf on annual leave, calm as you "
                    "like. Case closed, as far as I am concerned."
                ),
                "basis": "fact:1",
            },
            "strategies": {
                "answer": (
                    "I do not really use anything, no lists or reminders. I just remember "
                    "things. It has never been an issue, so I have never needed a system — "
                    "why fix what is not broken?"
                ),
                "followup": (
                    "No apps, no notebooks, nothing stuck to the fridge. My head does the job "
                    "fine on its own."
                ),
                "basis": "behavior:denial",
            },
            "background-goals": {
                "answer": (
                    "Honestly I am mostly here because my partner suggested it. I do not "
                    "have goals as such — I expect to be told there is nothing to find. No "
                    "previous assessments, nothing in the family that I know of."
                ),
                "followup": (
                    "Happy to go through the motions, but my expectation is a clean bill of "
                    "health. Then I can tell my partner I told them so."
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
            "Answer in full sentences, a few per answer, earnest and forthcoming. "
            "Answer each question on its own; do not try to reconcile with earlier "
            "answers. People misremember — let the accounts stand as you give them."
        ),
        "script": {
            "attention-focus": {
                "answer": (
                    "I zone out in the middle of things more than I would like. Someone "
                    "will be explaining something and I will realise I only caught half of "
                    "it. It is embarrassing when they notice, which they do."
                ),
                "followup": (
                    "It is the worst on calls, actually — no faces to anchor me, and suddenly "
                    "everyone is agreeing to something and I have no idea what. I just nod along."
                ),
                "basis": "behavior:vague",
            },
            "organization": {
                "answer": (
                    "Organizing things is not my strong point. I have tried planners and "
                    "apps and they work until I forget to open them, which takes about "
                    "three days. Then it is back to chaos."
                ),
                "followup": (
                    "The longest I ever stuck with a planner was maybe a fortnight, and I was "
                    "so proud of myself. Then one busy week and it was over."
                ),
                "basis": "behavior:vague",
            },
            "task-completion": {
                "answer": (
                    "At work I miss deadlines more than I would like to admit. Someone "
                    "will ask where a report is and I will realise I never even started it, "
                    "even though I meant to all week. The intention is there, the doing is not."
                ),
                "followup": (
                    "Last month was bad for this — two things I just never started until someone "
                    "chased me. I had weeks. I cannot explain where the weeks went."
                ),
                "basis": "behavior:vague",
            },
            "forgetfulness": {
                "answer": (
                    "I forget stupid little things all the time — why I walked into a room, "
                    "where I put my phone while I am holding it. It drives my partner mad, "
                    "and honestly it drives me a bit mad too."
                ),
                "followup": (
                    "Yesterday I went upstairs for my wallet, came down with a book, and had to "
                    "go back up. My partner just watched the whole thing happen."
                ),
                "basis": "behavior:vague",
            },
            "restlessness": {
                "answer": (
                    "In long meetings I fidget quite a lot, clicking pens and shifting "
                    "about in my chair. An hour sat still feels endless to me — I am counting "
                    "down the minutes by halfway."
                ),
                "followup": (
                    "I have broken so many pen lids in meetings. People must think I am bored, "
                    "but I am usually trying quite hard to listen — my body just will not sit still."
                ),
                "basis": "fact:2",
            },
            "impulsivity": {
                "answer": (
                    "I do jump in a bit. If I have the answer I will just say it rather than "
                    "waiting. Sometimes that lands badly and I wish I had held back, especially "
                    "in front of senior people."
                ),
                "followup": (
                    "I interrupted our director twice in one meeting last year. I still cringe "
                    "thinking about it — the words were out before I decided to say them."
                ),
                "basis": "behavior:vague",
            },
            "childhood-onset": {
                "answer": (
                    "School was never a problem. I got through it like everyone else, and "
                    "I do not remember any big issues with teachers or grades back then. "
                    "Honestly it all seems fine in hindsight."
                ),
                "followup": (
                    "School was never a problem, as I said — no detentions, "
                    "no interventions, nothing my parents were called in for. Just normal school."
                ),
                "basis": "fact:0",
            },
            "persistence-course": {
                "answer": (
                    "Over the years it has been up and down, I think. Some jobs it was "
                    "worse, some stretches were okay. I could not map it out exactly, but "
                    "it has definitely been there a long time."
                ),
                "followup": (
                    "The stressful jobs were always worse — tight deadlines and everything "
                    "falling apart at once. Quieter stretches I barely noticed it. So it comes "
                    "and goes, I suppose."
                ),
                "basis": "behavior:vague",
            },
            "settings": {
                "answer": (
                    "It is worst at work, where there are deadlines and people watching. "
                    "At home it matters less, though the flat is chaos. So it shows up "
                    "differently depending on the pressure."
                ),
                "followup": (
                    "Work is where it counts because other people depend on me. At home the only "
                    "victim is my own kitchen, which can wait."
                ),
                "basis": "behavior:vague",
            },
            "impact-work": {
                "answer": (
                    "Actually, I repeated a year after missing so much coursework that "
                    "they held me back. I had sort of forgotten about that until now. A "
                    "whole year gone, because I just had not handed things in."
                ),
                "followup": (
                    "Yeah, I repeated a year — that is the biggest concrete thing, looking back. "
                    "Mountains of missed coursework. I am not sure how I forgot to mention that first."
                ),
                "basis": "fact:1",
            },
            "impact-relationships": {
                "answer": (
                    "My partner says I do not listen, and they are probably right. I will "
                    "nod along and then have no idea what was agreed. We argue about it "
                    "more than I would like."
                ),
                "followup": (
                    "We had a proper row about it last month — I agreed to something about their "
                    "family visit and then looked blank when it came up again. That one stung."
                ),
                "basis": "behavior:vague",
            },
            "context-factors": {
                "answer": (
                    "Whether any of this goes back to childhood, I am not sure. I honestly "
                    "cannot say if I was like this as a kid or if it started later. The early "
                    "years are a blur."
                ),
                "followup": (
                    "I keep going back and forth on the childhood question. Some days I think "
                    "it was always there, other days I think I am imagining it. I cannot settle it."
                ),
                "basis": "uncertain",
            },
            "strategies": {
                "answer": (
                    "I try keeping lists, and they help for a day or two. Then I lose the "
                    "list, or stop looking at it, and I am back where I started. It is a "
                    "bit of a cycle at this point."
                ),
                "followup": (
                    "I currently have three lists on the go and I am ignoring all of them. "
                    "There is probably something I was supposed to buy on one of them."
                ),
                "basis": "behavior:vague",
            },
            "background-goals": {
                "answer": (
                    "I am here because work suggested an assessment after the missed "
                    "deadlines piled up. I want to know what is going on, and whether "
                    "there is anything that actually helps. I am taking this seriously."
                ),
                "followup": (
                    "Work paying for the referral concentrated my mind, put it that way. I do "
                    "not want to be the person who keeps dropping things — I want to fix it."
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
            "Answer in full sentences, a few per answer, trying genuinely to be helpful. "
            "Give partial detail where you have it; say plainly what you cannot recall. "
            "Never invent dates. It is fine to be frustrated about the gaps."
        ),
        "script": {
            "attention-focus": {
                "answer": (
                    "I drift off in the middle of conversations, especially on calls. I will "
                    "realise I have no idea what was just decided and have to ask someone "
                    "afterwards, which is awkward every single time."
                ),
                "followup": (
                    "It happened again this morning, actually — a whole decision made while I "
                    "was miles away, and I had to message a colleague after to ask what we agreed."
                ),
                "basis": "behavior:vague",
            },
            "organization": {
                "answer": (
                    "My system is basically organised chaos. I know where most things are, "
                    "but nobody else could find anything. It falls apart whenever I am busy, "
                    "which is, well, most of the time lately."
                ),
                "followup": (
                    "Under pressure the 'system' is just piles with extra steps. I tell myself "
                    "I will file things properly at the weekend, and then the weekend has other ideas."
                ),
                "basis": "behavior:vague",
            },
            "task-completion": {
                "answer": (
                    "This month alone I have missed two team deadlines, which is pretty "
                    "bad. Both times I knew exactly what I had to do, I just kept putting "
                    "off starting until there was not enough time left."
                ),
                "followup": (
                    "Both deadlines were things I had weeks for — that is the part I cannot get "
                    "past. It was not workload, it was just me not starting."
                ),
                "basis": "fact:1",
            },
            "forgetfulness": {
                "answer": (
                    "Keys are the big one — I lose them around the house constantly. I have "
                    "a bowl by the door that is supposed to fix it, and half the time the "
                    "keys are anywhere but the bowl."
                ),
                "followup": (
                    "Found them in the bathroom yesterday. The bathroom! I have no explanation "
                    "for that one and I have stopped trying to find one."
                ),
                "basis": "fact:2",
            },
            "restlessness": {
                "answer": (
                    "That is not really an issue for me. I can sit still fine, I do not "
                    "fidget or feel wired. It is more the getting-started side that is "
                    "the problem — once I am going, I am going."
                ),
                "followup": (
                    "Still no restlessness to report, even thinking about it harder. Stillness is "
                    "easy; starting is hard. That contrast is pretty consistent for me."
                ),
                "basis": "behavior:denial",
            },
            "impulsivity": {
                "answer": (
                    "I do not think I am impulsive. I mull things over, sometimes too much — "
                    "that is half the problem with starting. Deciding takes me ages, and then "
                    "the deadline has moved closer while I was deciding."
                ),
                "followup": (
                    "Overthinking rather than underthinking, that is me. I will research a "
                    "two-line email like it is a thesis, and meanwhile the real task sits there."
                ),
                "basis": "behavior:vague",
            },
            "childhood-onset": {
                "answer": (
                    "I do remember a teacher saying I daydreamed in class, but I could not "
                    "tell you when that was or how old I was. It might have been primary "
                    "school. Honestly, I cannot recall — it is infuriating."
                ),
                "followup": (
                    "I keep trying to place the teacher comment and I just cannot. A classroom, "
                    "daytime, that is all I have got. No name, no year, nothing. I am sorry."
                ),
                "basis": "uncertain",
            },
            "persistence-course": {
                "answer": (
                    "I cannot say how long this has been going on. The work stuff is recent "
                    "and clear, but before that it is all a blur. I cannot recall any "
                    "duration, really, much as I would like to give you one."
                ),
                "followup": (
                    "If you pushed me I would be guessing, and I do not want to guess at this. "
                    "The honest answer is still: I do not know how long."
                ),
                "basis": "uncertain",
            },
            "settings": {
                "answer": (
                    "Work is where it shows, because there are deadlines and witnesses. At "
                    "home nobody is keeping score, so it matters less, though the flat "
                    "shows it — just ask my kitchen table."
                ),
                "followup": (
                    "Home me and work me are the same person, just with different consequences. "
                    "Late at home means a cold dinner; late at work means a formal warning."
                ),
                "basis": "fact:1",
            },
            "impact-work": {
                "answer": (
                    "Those two missed deadlines this month led to a formal warning at work, "
                    "so it is serious now. My manager basically said it cannot happen again, "
                    "which is fair enough — I agree with them."
                ),
                "followup": (
                    "The warning letter is sitting on my desk as we speak. It is the reason I am "
                    "here, and the reason I am taking all of this seriously."
                ),
                "basis": "fact:1",
            },
            "impact-relationships": {
                "answer": (
                    "I do not think it affects my relationships much. My friends know I am "
                    "flaky about replying to messages, but nobody has ever made a thing of it. "
                    "We rub along fine."
                ),
                "followup": (
                    "My friends just factor in a two-day delay on all my replies at this point. "
                    "It is a running joke rather than a real problem, I think."
                ),
                "basis": "behavior:vague",
            },
            "context-factors": {
                "answer": (
                    "My sleep has been pretty poor lately and I think that makes everything "
                    "worse. Whether it is the cause or just makes it harder, I do not "
                    "really know. Probably a bit of both, if I am honest."
                ),
                "followup": (
                    "I have been going to bed late and scrolling, which I know does not help. "
                    "But even after a good night the focus stuff is still there, so sleep is not "
                    "the whole story."
                ),
                "basis": "behavior:vague",
            },
            "strategies": {
                "answer": (
                    "I block time in my calendar for the boring admin stuff, and that helps "
                    "a bit when I stick to it. Half the time something else comes up and "
                    "the block just gets ignored, though."
                ),
                "followup": (
                    "The calendar blocks work about half the time, which is better than nothing. "
                    "The failure mode is always the same: I move the block 'just this once'."
                ),
                "basis": "behavior:vague",
            },
            "background-goals": {
                "answer": (
                    "I am here because of the warning at work — I need to understand what "
                    "is going on before it gets worse. Nobody in my family has been through "
                    "anything like this as far as I know, so I am starting from zero."
                ),
                "followup": (
                    "I want to walk out of this process with a clear picture to take back to my "
                    "manager — not excuses, just an honest account of what is happening."
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
