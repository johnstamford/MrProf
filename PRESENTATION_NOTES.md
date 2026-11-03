# MrProf — Presentation Notes (F14, 3 Nov 2026)

## 60-second demo (vague answer → follow-up → citation)

1. Open `/demo/vague-01` (frozen synthetic report, watermarked
   `SYNTHETIC DEMO — not a real person` on every surface).
2. Find a thin/vague answer (e.g. bills left on the counter, no dates given).
3. Show the follow-up it triggered, then the evidence card: one-sentence
   system note plus the shortest exact quote with `line N · segment ID`.
4. Click the quote/line link — it jumps to the same words in the full
   line-numbered transcript. Denials, uncertainty, tensions, gaps stay
   visible; nothing is rewritten.

Live version if asked: `/start` → screening (answer `Sometimes` to Q1–Q3,
`Often` to Q4 for a 4/6 positive) → `/report` → Continue to interview →
give a vague answer and watch the targeted follow-up arrive.

## What it does / does not do (say once)

- Organizes what the visitor reports so a clinician can review it, with
  every point traceable to exact transcript quotes.
- Does NOT diagnose, rule anything out, estimate probabilities, or assign
  severity. Topics/taxonomy are drafts, not clinically validated.
- Every briefing is an `UNREVIEWED — not clinician-approved` draft until a
  reviewer annotates it. Synthetic runs prove the pipeline, not clinical
  validity or real-user timing.

## 10-run metrics (F14 pass, hermetic dummy path — no network, no cost)

Report: `docs/eval/f14-10run-20261103T204353.{md,json}`
Fixtures: `skill-v0.4-draft`, `topics-v0.6-draft`, `taxonomy-v0.3-draft`.

| Metric | Result |
|---|---|
| Completion | **10/10** (8 full + 2 taster) |
| Quote-exactness | **174/174 (100%)** — every evidence quote an exact substring of its cited segment |
| Banned-language hits | **0** (no diagnosis/probability/severity wording in system copy) |
| Full-journey turns | 19, 19, 20, 20, 20, 20, 20, 20 (cap 30, never hit) |
| Taster turns | 8, 8 |
| Observations | 174 total (~17–20 full, 8 taster per run) |
| Screening scores | vague 3/6, denier 0/6, contradictor 3/6, recall 3/6 (both repeats identical) |
| Report reopen | 10/10 — screening + briefing retrievable after completion |
| Briefing shape | 10/10 front sheet + areas present; coverage-detail lines on covered topics |
| Latency (ASGI in-process, NOT real-user timing) | mean ~197 ms, max ~232 ms per turn |
| Backend suite | 107 passed, 1 skipped |

Coverage depth worth calling out: denier runs carry only 4 coverage-detail
lines vs 10–12 on substantive personas — the dimension matrix visibly
distinguishes "denied, complete" from "reported with detail."

## Journey numbers to quote

- Screening: 6 fixed ASRS v1.1 questions, deterministic `original-0-6`
  scoring (≥4 positive), resubmission-safe and versioned.
- Interview: full = 14 objectives + ≤6 follow-ups (19–20 turns observed);
  taster = 6 objectives + ≤2 follow-ups (8 turns observed).
- Review step: every journey passes through user review-and-confirm before
  any briefing is generated (direct report GET before confirm → 404).
- Abandonment in synthetic runs: 0/10 (simulated patients always finish —
  say this explicitly; it is NOT a human-usability claim).

## Reviewing the 10 runs (local only)

Each run is resumable at `http://localhost:3000/start` with its code +
password. Codes are listed here; **passwords live only in the gitignored
local run dirs** (`sim/runs/<run>/credentials.json`) — never committed,
matching the F12-min pattern. Nothing below opens without the local file.

| Persona | Mode | Turns | Code | Password in |
|---|---|---|---|---|
| vague-01 | full | 20 | `3GT8KWF8` | `sim/runs/vague-01-dummy-20261103T204405/credentials.json` |
| vague-01 | full | 20 | `2KE94UMC` | `sim/runs/vague-01-dummy-20261103T204418/credentials.json` |
| denier-01 | full | 19 | `WKX8KMQR` | `sim/runs/denier-01-dummy-20261103T204430/credentials.json` |
| denier-01 | full | 19 | `XPMRDKQM` | `sim/runs/denier-01-dummy-20261103T204442/credentials.json` |
| contradictor-01 | full | 20 | `AZT5546M` | `sim/runs/contradictor-01-dummy-20261103T204454/credentials.json` |
| contradictor-01 | full | 20 | `M8RGS8CU` | `sim/runs/contradictor-01-dummy-20261103T204507/credentials.json` |
| recall-01 | full | 20 | `KPU2DTEM` | `sim/runs/recall-01-dummy-20261103T204519/credentials.json` |
| recall-01 | full | 20 | `A8EEUVDU` | `sim/runs/recall-01-dummy-20261103T204531/credentials.json` |
| vague-01 | taster | 8 | `YADUMY67` | `sim/runs/vague-01-dummy-20261103T204541/credentials.json` |
| denier-01 | taster | 8 | `AQWZ3CPH` | `sim/runs/denier-01-dummy-20261103T204551/credentials.json` |

Caveat for reviewers: these are synthetic dummy-patient runs (scripted
answers, stub phrasing) — good for checking report shape and citations,
not interview quality.

## Honest limitations (one slide, then move on)

- Draft topics/taxonomy, no clinical validation; interim
  psychology-student view only.
- Live-model turns take ~10–17 s each (the 197 ms above is the hermetic
  stub, not what a judge would feel on a live stack).
- No PDF beyond print CSS; no clinician dashboard; no password recovery.
- Risk support is a static non-monitored signpost (full workflow deferred).
- Real-user opening: invite-link + consent-gated 2-day opening only,
  disabled by default (`docs/opening.md`).

## If asked…

- "Does it diagnose?" — No. Positive screen = "further assessment may be
  useful"; below threshold = "does not exclude ADHD or other conditions."
- "Why not test on real people?" — Synthetic-only until F13 readiness;
  no real participant data in the repo, ever.
- "Can I share my report?" — By design, no. Sharing invites others to try
  the app (`/demo` gallery); reports open only with the owner's code +
  password.
- Provisional sketch (`PROVISIONAL_SKETCH`): experimental deterministic
  pattern summary, hackathon demo-only exception — `demo-only`/`off` for
  any real-user opening, revisit/remove post-hackathon.
