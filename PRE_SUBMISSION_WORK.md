# MrProf — Pre-Submission Work Plan

Created: 3 Nov 2026. Owner-approved direction from the user-journey review of
2–3 Nov 2026. This plan sits on top of `FEATURE_PLAN.md` (Features 1–16 stand
as recorded there); it does not reopen them. Read `PROJECT_OVERVIEW.md` and
the hard domain rules in `AGENTS.md` first — everything below stays inside
them (ASRS untouched, deterministic scoring, no diagnosis language, verbatim
transcripts, exact quotes, present/denied/uncertain/missing kept distinct).

## Goal

A user finishes the journey holding a report they are **confident in** and
that has **good coverage** — where confidence comes from:

1. **Provenance** — every point traceable to their exact words (already built).
2. **Ownership** — the user checks, corrects, and confirms the report before
   it is final (WS1 — new).
3. **Coverage they can see filling in**, and gaps they can act on while still
   present (WS2).
4. **A report that reads like a document for a clinician**, not an evidence
   dump with telemetry in it (WS3).
5. **Limits stated once, plainly** — not repeated at every surface (WS4).
6. **Low friction at the known drop-off points** (WS5).

Explicitly not the goal: more disclaimers, more questions for their own sake,
or any new clinical claim. Topics/taxonomy stay `draft — not clinically
validated`; nothing here promotes them. No 18-item instrument, no diagnostic
criteria scoring, no severity/probability language.

## Working rules for all workstreams

- One workstream at a time, in the order below; checkpoint in git per WS.
- After each WS: focused tests first, then full suite
  (`docker compose exec api pytest tests -q`), `npm run build` in `web/`,
  and re-run F12-min (`sim/eval.py`) — the frozen gate (100% quote-exactness,
  0 banned-language hits, completion) must still PASS with unchanged
  thresholds. If briefing shape changes, re-freeze the demo set
  (`sim/export_demo.py`) in the same commit.
- Synthetic data only. No real answers in fixtures, logs, or commits.
- All new state transitions follow the existing pattern: version-checked
  atomic writes + idempotency keys; retries/double-clicks never duplicate
  turns, reviews, or reports.
- Update `FEATURE_PLAN.md` status and this file's checkboxes as WSs land.

---

## WS0 — Submission hygiene (do first, ~half a day)

The judging surface is currently weaker than the product.

- [x] Fill `README.md` (was `TBD`): one-command start
  (`docker compose up --build`), prerequisites, the 60-second demo script
  (vague answer → follow-up → citation), what the system does/does not do,
  and limitations stated once. Done 3 Nov 2026 (WS0).
- [x] Decide the fate of the uncommitted `web/components/briefing.tsx`
  change in the working tree (right-rail removal). WS3 supersedes it:
  reverted to a clean tree in WS0; WS3 redoes it properly. Done 3 Nov 2026.
- [x] Release notes stub: `docs/release-notes.md` — features done, known
  limitations (live-turn latency 10–17s, draft topics, no clinical
  validation), real-user opening disabled by default. Done 3 Nov 2026.

**Acceptance:** a judge can clone, start, and run the demo script from the
README alone.

---

## WS1 — User review-and-confirm step (the confidence step) ⭐

**Problem.** Today the last answer goes straight to batch assessment →
briefing (`api/app/assessment.py` builds the briefing; 
`web/app/interview/page.tsx` renders it). The user never confirms the report
represents them, never corrects a misread, and has no way to add the thing
they forgot. The report is done *to* them.

**Design.**

New interview status `review` between final batch assessment and briefing
generation:

1. Final batch runs as today (extraction, coverage, tensions) but, instead
   of building the briefing, stores the assessment and sets
   `interview.status = "review"`, briefing deferred.
2. New page state in `/interview` (phase `review`): **"Before we write your
   briefing"** showing, per topic:
   - status in plain words (Reported / Explicitly denied / Uncertain /
     Limited / Not covered — existing vocabulary),
   - the system's one-line observation notes with their exact quotes,
   - three affordances per topic: **Looks right** (default), **Add something**
     (free text appended for that topic), and per-observation
     **This isn't what I meant** (free-text correction).
   - One global box: **"Anything important we didn't ask about?"**
   - Optional top-up entry point (from WS2-C): "Answer 1–3 quick follow-ups
     for the thinnest areas" — or skip straight to confirm.
   - Confirm button: **"Looks right — build my briefing."**
3. Confirm (idempotent, version-checked) → briefing built as today, plus:
   - user additions stored as **new verbatim transcript segments** with
     stable IDs (objective `user-addendum`, clearly attributed, never merged
     into the original turns; originals byte-identical), extracted like any
     turn so they appear as cited evidence;
   - user corrections stored on the observation as `user_correction`
     (separate field from reviewer `review_note`; original note and quote
     untouched, both shown);
   - briefing records `user_confirmed_at` and renders the provenance line:
     *"Prepared from your answers · every point links to your transcript ·
     checked and confirmed by you on {date}."*
4. Resume support: closing the browser at `review` resumes at `review`
   (`GET .../interview/next` returns the review state; `/start` resume note
   says "Your briefing is waiting for your check").

**Hard rules preserved:** transcript/screening never rewritten; corrections
and additions are new versioned records; unconfirmed briefings are never
generated (so a half-checked report cannot leak); reviewer annotate
(F11-min) unchanged and distinct from user correction.

**Files (expected):** `api/app/assessment.py` (defer briefing),
`api/app/routes/interview.py` (review GET/confirm/add endpoints),
`api/app/models.py`, `api/app/briefing.py` (addendum + corrections +
provenance), `web/app/interview/page.tsx` (review phase), tests
(`tests/test_review_step.py`).

**Acceptance:**
- Journey cannot reach a briefing without passing through `review`
  (direct report GET before confirm → 404).
- Additions appear in briefing + transcript with exact quotes; originals
  byte-identical (test-asserted, same pattern as `test_review.py`).
- Confirm is idempotent: double-click/replay yields one briefing version.
- Resume from `review` works after service restart.

**Status (3 Nov 2026): ✅ done.** Batch ends at `review` (briefing only on
confirm); review page per plan (status chips, notes + quotes, Looks-right
default, per-topic Add, per-observation correction, global box, top-ups,
confirm); addenda as `probe: addendum` turns + verbatim segments + inline
extraction; observation-level `user_correction` via atomic single-field
update; confirm recomputes coverage/tensions fresh, crash-safe replay
repair; `user_confirmed_at` + provenance line; resume via persisted status.
`tests/test_review_step.py` (4 passed: no-briefing-before-confirm,
addition/correction/idempotent-confirm, top-ups, taster→full v2). Full suite
(104 passed) + `npm run build` green; demos re-frozen; F12-min re-run PASS.

**Size:** L. This is the flagship change; protect its scope.

---

## WS2 — Coverage: visible, deeper where it matters, actionable

Three layers, in priority order. All keep the hard cap
(`HARD_TURN_CAP = 30`, `MAX_FOLLOWUPS = 6`, taster 2) and the rule that
denials/uncertainty are complete answers, never probed.

### WS2-A — Visible coverage during the interview (S)

**Problem.** Only `Question N · M answered` is shown
(`web/app/interview/page.tsx`); over 14–23 turns users cannot tell where
they are, which is where abandonment happens.

**Change.** A compact 4-area progress rail on `/interview` (Daily
functioning / History and course / Settings and impact / Context and
background — the existing `FAMILIES` rollup), each area marked
done / current / upcoming, derived deterministically from answered
objectives. No total-question countdown (the count genuinely branches);
area-level progress is honest because round 1 always visits all four.
Taster mode shows the same rail with unvisited areas marked as taster gaps.

### WS2-B — Dimension-driven follow-ups (M) ⭐ the substantive fix

**Problem.** Coverage today is one open question per objective
(`api/app/topics/v0.4.yaml`); `build_followups`
(`api/app/assessment.py:118`) only chases tensions, then thin/pending
topics with a generic "invite one concrete detail." A topic can be marked
`covered` from a single substantive answer that has no example, no
frequency, no timeframe, and no setting — breadth without depth, and the
report cannot honestly show more.

**Change.** Make the batch follow-up queue dimension-aware, in code:

1. Define per-objective **evidence dimensions** in the topics YAML
   (topics-v0.5-draft; taxonomy unchanged). Default set for behaviour and
   impact objectives: `example` (a concrete occasion), `frequency`
   (how often), `period` (when / since when / life period), `setting`
   (where it shows up). Course objectives: `period`, `example`. Context/
   background: `example` only. This is an interview-coverage definition,
   not a clinical-criteria mapping, and is labelled as such.
2. New deterministic function `missing_dimensions(objective, observations,
   quality)` in `api/app/assessment.py`, computed from fields the
   extractor already stores (`period`, `setting`, `frequency` non-empty =
   filled; `example` = stored `answer_quality.has_example` or detail
   level 3). No new model calls.
3. Reorder the follow-up queue: (1) tensions (as today), (2) **present
   topics with missing dimensions** — ask for the single highest-value
   missing dimension (priority: example → frequency → period → setting),
   one question, phrased by the model from a dimension-specific reason
   string, e.g. *"You mentioned losing track of tasks — can you give one
   recent example of that?"*; (3) thin/pending (as today). Still one
   follow-up per objective, caps unchanged.
4. Briefing gains a per-topic **coverage detail** line built from the same
   matrix (e.g. "example ✓ · frequency ✓ · timeframe — · setting ✓"),
   rendered in WS3's evidence section. "Covered" in the report now means
   something checkable.
5. Dummy extractor path must fill the dimension fields deterministically
   so hermetic tests and F12-min stay meaningful.

**Non-goal:** expanding to per-symptom-item questioning (e.g. all 18 DSM
items). That is a clinical-design decision for the deferred clinical
review, not pre-submission work. What WS2-B claims is *interview* coverage
depth, never diagnostic-criteria coverage.

**Acceptance:** unit tests for `missing_dimensions` (each dimension
present/absent, denial/uncertain exempt); a dummy journey where a vague
present answer yields a dimension-targeted (not generic) follow-up; F12-min
still PASS; no turn-cap regressions (queue stays bounded, verified by the
existing cap tests).

### WS2-C — Gaps become actions at the review step (S, depends on WS1)

**Problem.** Gaps in the final report are labelled and left; taster users
get a permanently gappy report with no way back.

**Change.**
- In WS1's review screen, each Limited/Not-covered topic offers
  **"Add a short answer now"** (free text → stored exactly like a WS1
  addition for that objective, extracted, and the topic re-scored) — no
  re-entering the question loop.
- After a **taster** briefing, a banner offers **"Continue to the full
  interview"**: resumes the same assessment, asks the 8 unasked objectives
  (+ bounded follow-ups), then a fresh review step and briefing v2. Mode
  upgrade is a stored, version-checked transition (`taster → full`);
  briefing v1 retained. Full-mode users never see a downgrade offer.
- The closing report keeps gaps visible (WS3) but each gap now reads as
  *"not covered — you can add to this from your review page copy"* only
  pre-confirmation; post-confirmation gaps are simply listed once
  (see WS4 — no repeated "not a negative finding" glosses).

### WS2-D — Goals first (S, optional if time-boxed)

**Problem.** `background-goals` ("what brings you to this assessment") is
objective 14 of 14; late abandonment loses the most appointment-relevant
content.

**Change.** Ask a short goals opener first ("What brings you to this
assessment now, and what would you most like your clinician to
understand?"), stored against `background-goals`; its later slot becomes a
depth follow-up on background/family history only if not already covered.
Requires: `PLAN_ORDER` reorder in `api/app/interview.py` + topics/
taxonomy order kept in lock-step (both loaders assert order), and
`TASTER_OBJECTIVES` changed from `PLAN_ORDER[:6]` to an explicit tuple of
the six behaviour objectives. Update planner tests accordingly.

**Acceptance (WS2 overall):** synthetic journeys (dummy + one live spot
check) show: rail present, dimension follow-ups firing on vague-present
personas, no probing of denier/recall personas beyond today's behaviour,
turn counts within caps, F12-min PASS.

**Status (3 Nov 2026): ✅ done (incl. WS2-D).**
WS2-A: `ProgressRail` (done/current/upcoming/taster-gap, deterministic from
answered objectives; no countdown). WS2-B: dimensions in topics YAML
(v0.5 → v0.6 after reorder; taxonomy untouched in content), `missing_dimensions`
+ `objective_dimensions` in `api/app/interview.py`, queue reordered
(tensions → dimensions → thin/pending) with dimension-specific phrasing,
`coverage_detail_line` in briefing, dummy extractor cue-filling, dummy
interviewer quality backfill incl. end-of-round backfill for the unrated final
answer. WS2-C: per-topic/global "Add something" + per-observation correction
ride on WS1 endpoints; "Show follow-ups" top-ups (`POST review/topups`,
≤3, uncertain never probed); taster→full `POST continue` (version-checked,
briefing v1 retained, v2 after fresh review). WS2-D: goals opener first
(topics v0.6 + taxonomy v0.3 reordered in lock-step; explicit TASTER tuple;
later-slot depth subsumed by dimension follow-ups). `tests/test_ws2.py` (6
passed); turn-count assertions widened to the bounded 14–23 range; sim journeys
complete within caps. Full suite (104 passed) + `npm run build` green; demos
re-frozen; F12-min re-run PASS (see global verification).

---

## WS3 — Report: front sheet first, evidence second, no telemetry

Owner-approved in principle 3 Nov. All deterministic assembly from stored
evidence — no new LLM-generated claims.

- [x] **One-page front sheet** at the top of Section 1, assembled from
  existing stored fields only: why they came (background-goals quotes),
  screening result (score, method, threshold line), timeline snapshot
  (course observations with `period`), where impact lands (impact
  observations), relevant context (context/strategies), and **"Worth
  exploring together"** — the gaps, `unable` topics, and unresolved
  tensions phrased as open areas, not findings. Everything on the front
  sheet links down to its evidence card.
- [x] **Fix the area headline.** `family_rollup`
  (`api/app/briefing.py:90`) currently prioritises Uncertain over
  Reported, so one "can't remember" headlines a whole area. Change to
  dominant-status headline (largest count; tie-break Reported →
  Explicitly denied → Uncertain → Limited → Not covered), counts always
  shown (already done).
- [x] **De-duplicate the evidence section.** Topic sections lead with
  observation cards (quote + note + line link); the full Q&A per topic is
  removed from Section 2 (it remains, once, in the Section 3 transcript,
  which every quote already anchors to). Expected effect: report length
  roughly halves.
- [x] **Coverage detail per topic** (from WS2-B) rendered as a small
  dimension line under each topic heading.
- [x] **Remove user-surface telemetry:** answer-detail counts and the
  latency paragraph (`web/components/briefing.tsx` detail/latency block)
  move into the collapsed "How this was gathered" system notes; the
  per-card "(system interpretation, not a quote)" suffix is replaced by
  one section-level label: *"Why this is here — the system's one-line
  reading; the quote is your words."*
- [x] **Reviewer controls off the patient surface.** `onReview` is only
  wired when a reviewer mode is active (separate route or explicit
  `?review=1` with its own auth check); the patient's own briefing shows
  no Accept/Amend/Reject buttons and no "awaiting review" chips. Once a
  real review exists, show its outcome (accepted/amended + note) —
  that is information, not machinery. The unreviewed indicator stays as
  the single WS4 line.
- [x] **Print stylesheet:** front sheet prints as page 1 on its own;
  evidence + transcript follow. "Print / save PDF" becomes the primary
  export button; JSON download demoted to a secondary text link.

**Acceptance:** briefing JSON stays backward-compatible for frozen demos
(new fields optional/defaulted — the pattern already used for `areas`);
old briefings still render; banned-language tests pass; demos re-frozen.

**Status (3 Nov 2026): ✅ done.** Front sheet (`build_front_sheet`, all
stored fields, anchors to evidence cards); dominant-count headline with the
specified tie-break (test updated); Section 2 flattened to observation cards
+ turn-level corrections, Q&A once in transcript; `coverage_detail` line from
the WS2-B matrix (populated, rendered when present); telemetry collapsed into
"How this was gathered" (latency hidden on stub-speed runs; full 3-way answer
accounting after user feedback); section-level "Why this is here" label,
per-card suffix removed; reviewer controls only with `?review=1` (+ reviewer-mode
note; outcomes still shown); front sheet `print-page` + Print-primary/JSON-link.
Focused tests + full suite (104 passed) + `npm run build` green; demos re-frozen.

**Size:** M.

---

## WS4 — Disclaimer diet: say it once

Owner-agreed 3 Nov. Principle: **provenance replaces caveats.** Three
boundary statements survive, each doing distinct work; everything else is
deleted or demoted. Internal code comments, consent data-handling detail,
and test-enforced banned-language lists are untouched — this is about
user-surface repetition only.

| Surface | Keep | Remove / demote |
|---|---|---|
| Consent page + checkbox | Full text (data, no-monitoring, not-diagnosis) — the one substantive statement | — |
| Screening report | The result explanation itself (positive → further assessment may be useful; below threshold → does not exclude) | Any additional hedging around it |
| Briefing header | One line: *"Prepared from your answers for clinician review — unreviewed draft."* + WS1 provenance line once confirmed | — |
| Global footer (`web/app/layout.tsx`) | — | Delete the "Draft research prototype…" paragraph (consent + report lines carry it) |
| Landing page | One short "What this is / isn't" line inside the hero sub-copy | The "Limitations, stated plainly" box (`web/app/page.tsx`) |
| `/start` | Consent link + risk signpost | The "draft research prototype" paragraph (fold the useful half — "organizes what you report for a clinician" — into the What-is-this copy without the caveat framing) |
| `/interview` header | Risk note as a small persistent "Need support?" link | The "topics are a first draft, not a clinical assessment" sentence (`page.tsx` interview header); risk note rendered in full only on `/start`, not on loading/assessing/done states |
| Briefing body | Gaps listed once, factually ("Not covered: X, Y") | Sticky banner *and* chip *and* completion-note triplication → keep the chip only, move completion note into "How this was gathered"; topic-rail "not negative findings" footnote; per-status repeated glosses |
| Evidence cards | Section-level "Why this is here" label (WS3) | Per-card "(system interpretation, not a quote)" |

Version/draft identifiers (`topics-v0.4-draft`, skill/taxonomy versions)
stay in JSON metadata and system notes — out of user-facing copy.

**Acceptance:** banned-language and consent tests unchanged and green;
a manual count: the not-a-diagnosis boundary appears at most 3 times in a
full journey (consent, screening explanation, briefing line); no surface
loses information a user needs for safety (risk signpost still reachable
in ≤1 click from every interview state; ready state keeps a "Need support?"
expander, assessing/done states carry no full note (done briefing keeps its
support line)).

**Status (3 Nov 2026): ✅ done.** Footer paragraph deleted (footer removed);
landing hero carries the one-line is/isn't, Limitations box removed; `/start`
What-is-this folds the useful half without caveat framing, consent + full
risk signpost kept; `/interview` header drops the draft-topics sentence, full
risk note only on `/start`, loop uses the compact expander; briefing keeps the
UNREVIEWED chip only (sticky banner render removed, banner text shortened to
the one-liner in `api/app/briefing.py`), completion note moved into "How this
was gathered", gaps listed once, rail footnote + repeated "not negative
findings" glosses removed, `NotConcludedBox` no longer rendered.
Evidence-card section-level label deferred to WS3. Screening report needed no
change (already minimal). Focused tests (briefing/report/f10a/review: 20
passed) + `npm run build` green.

---

## WS5 — Friction fixes at known drop-off points

Owner-approved ("5 do") 3 Nov.

- [x] **Save-your-details card.** One `AccessCard` (download `.txt`: code,
  date, resume URL, no-reset line + copy-code button, warning once inside)
  used by both the created and resume boxes. Done 3 Nov 2026 (WS5).
- [x] **Skip / can't-remember controls.** Both buttons submit through the
  normal answer path; anchored `_SKIP_RE` classifies standalone skip-outs
  as uncertain-like (substantive answers mentioning "skip" unaffected).
  Done 3 Nov 2026 (WS5).
- [x] **Correct a previous answer — via WS1, not in-place edit.** In-loop
  "Fix my last answer" link on the immediately following question →
  `POST .../interview/correct` (latest turn only, version-checked,
  idempotent); correction stored as `turn.correction` + verbatim `T{n}-C{m}`
  segments, re-extracted as a new evidence version, rendered in the
  briefing against its topic. Full review-step correction is WS1. Done
  3 Nov 2026 (WS5).
- [x] **Screening report shows its working.** "Counted toward your score"
  ticks in `web/app/report/page.tsx` (+ `/demo/[id]` strip). Payload flag
  already existed. Done 3 Nov 2026 (WS5).
- [x] **Time expectation honesty.** `/start` now states question counts
  (6 screening; ~14 + follow-ups full; ~6 taster), no minutes. Done
  3 Nov 2026 (WS5).

**Acceptance:** skip/can't-remember journeys complete in dummy sims with
topics closed as uncertain; access-card download contains no password;
resume still requires code + password.

**Status (3 Nov 2026): ✅ done (incl. correction link).** Skip-outs close
topics as unable (unit + journey tested); "Fix my last answer" appends a
correction turn (original byte-identical, new evidence version, briefing
shows it; idempotent replay; 409 paths tested in `tests/test_ws5.py`:
4 passed). Access card carries code/date/URL, never the password. Full
suite + `npm run build` green (see global verification).

**Size:** S–M (the correction link is the only non-trivial piece; it can
slip to post-submission without blocking WS1).

---

## Sequence and timebox

Suggested order for a bounded pre-submission push (~3–4 focused days):

| Order | WS | Why here |
|---|---|---|
| 1 | WS0 hygiene | Judges read the README first; zero product risk |
| 2 | WS4 disclaimer diet | Small, and every later change inherits the cleaner voice |
| 3 | WS5 friction (minus correction link) | Small, independent, improves every test journey |
| 4 | WS3 report rework | Report shape settles before WS1 writes into it |
| 5 | WS2-A rail + WS2-B dimensions | Coverage data model lands before the review screen displays it |
| 6 | WS1 review step + WS2-C top-ups | Flagship; consumes WS2 coverage + WS3 briefing shape |
| 7 | WS2-D goals-first (optional) | Only if 1–6 are green with time in hand |

If time compresses, the cut line is: **WS0, WS4, WS3 (front sheet +
headline fix + telemetry removal), WS2-A, WS1 core (review + confirm +
addendum, without top-ups)** must land; WS2-B, WS2-C, WS2-D, and the WS5
correction link slip first, in that order.

## Global verification (before submission)

- [x] `docker compose exec api pytest tests -q` — all green (104 passed,
  1 skipped), incl. new tests for review step (`test_review_step.py`),
  dimensions (`test_ws2.py`), skip polarity + correction (`test_ws5.py`),
  mode upgrade (`test_review_step.py::test_taster_continue_to_full`).
- [x] F12-min re-run: PASS with frozen thresholds (8/8, quote-exactness
  158/158, 0 banned hits); report `docs/eval/f12min-20261103T181710.md`
  (fixtures: skill-v0.4, topics-v0.6, taxonomy-v0.3; 19–20 turns, within caps).
- [x] `npm run build` green; all routes 200 on the dev stack.
- [x] One live-model end-to-end journey (synthetic persona) exercising:
  screening → dimension follow-up → review with an addition and a
  correction → confirmed briefing → print preview page 1. (Done 3 Nov 2026:
  `vague-01` with model patient vs live interviewer, 20 turns, stop=complete,
  mean turn latency 1.4s. Follow-ups were dimension-targeted and grounded in
  prior answers — e.g. attention-focus "How often do you find you lose track
  of bills or tasks like that?" (frequency), forgetfulness "When did you
  first notice…?" (period). Review confirm via the driver path; addition +
  correction paths covered live-equivalently in `test_review_step.py`.
  Artifacts (with credentials) are local-only in `/tmp/live-spot-host/`,
  never committed.)
- [x] Demo set re-frozen and `/demo` spot-checked (4 personas still prove
  their distinct capabilities; vague persona now shows dimension
  follow-ups — 19–20 turns; front sheets + coverage lines verified in JSON).
- [x] Manual disclaimer count per WS4 acceptance (3 distinct boundary wordings:
  consent statement, screening explanation, unreviewed line).
- [x] `FEATURE_PLAN.md` updated with status/evidence for this plan; git
  checkpoints per WS (WS0, WS4, backend, frontend + verification); working tree clean.

**Status (3 Nov 2026): ✅ all workstreams landed and verified.** Live spot-check
result appended above (vague-01, model patient, 20 turns, complete, 1.4s mean
latency, dimension-targeted follow-ups).
Post-plan addition (owner request, same day): "Your account at a glance" recap
on the done screen — descriptive counts/lists only (reported / denied /
unsure / limited-or-not-covered + screening line + take-to-appointment note),
no interpretation. Excluded from print; reviewer mode hides it.

## Out of scope (unchanged)

Clinical review/validation of topics and taxonomy; 18-item ASRS; PDF
generation beyond print CSS; accounts; clinician dashboard; F10b risk
workflow; real-user opening changes (F13-min stands). Synthetic success
from any of this work is not clinical validity and must not be described
as such — once, in the README, per WS4.
