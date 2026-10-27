# MrProf — Locked Plan (27 Oct 2026 discussion)

Source docs: `PROJECT_OVERVIEW.md`, `FEATURE_PLAN.md` in repo (unchanged).
This file records decisions from plan walkthrough 1–14.

## Locked choices
- DB: MongoDB, collections `assessments, transcripts, evidence, reports` by `assessment_id`.
- Feature 3 scoring: summed 0–24 (Never0/Rarely1/Sometimes2/Often3/VeryOften4), >=14 positive. Store raw answers. Label `ASRS-v1.1-6Q summed-0-24`.
- Resume: store `next_question + coverage version + session blob` atomically on submit. `GET /interview/next` is read-only (question | complete | need_answer).
- Caps: 30 turns/assessment hard cap, max 3 probes/topic, target 15–25. Progress = topics `3 of 8 areas`, never fake countdown.
- Gaps: 1 question → 1 objective. No 4-in-1 bundling. Uncovered stays as gap; valid completion.
- Report 2: summary (unreviewed banner) → topics with `[Q L]` citations + 1-line summary → numbered transcript (`Q12.S1`, global L). Quote must equal source slice.
- PDF: HTML + print CSS only for MVP.
- Simulator: `sim/` Python, persona → real FastAPI, 5 artifacts sealed, start 4 personas x1, caps turns/time/cost.
- Eval 12: auto metrics (coverage, citation precision, unsupported, repeats, turns, latency, cost, stop reasons) + human spot-check. `sim/eval.py → eval_vN.json`.
- Public 13 gated: consent, retention/deletion, Tunnel HTTPS web-only, mongo private, rate/input limits, no secrets in logs, synthetic dry-run.

## Features 1–14 order
1. Docker: web→api→mongo, 1 command, health checks, pinned versions, Agent Framework save/restore spike.
2. Session: `assessment_id` + `access_secret` (hash only, Bearer), version + idempotency_key atomic write, no recovery in MVP.
3. ASRS 6Q fixed text + attribution, 6 required, deterministic code score.
4. Screening report fixed template, both results → interview, answers forwarded.
5. Interview API: `POST /answer` (submit answer → next Q), `GET /next` (resume), `GET /assessments/{id}`. Server-side creds, structured Pydantic, 1 regen, bounded cost.
6. First journey: 1-Q UI, 5–6 YAML topics, explicit complete with gaps.
7. Evidence: immutable transcripts, `s{turn}-{n}` segments, versioned extractions, reviewer touches review only.
8. Simulator as above.
9. Full coverage ~12–15 objectives, priority screening-flagged + contradiction, stop on evidence/denial/2x can't-recall.
10. Quality: validator (compound/leading/repeat/off-objective), neutral fallback, accept can't-remember, risk safe-completion text.
11. Final reports: 2 HTML versioned, clickable citations, source types, accept/amend/reject per obs, unreviewed banner.
12. Evaluation as above.
13. Public readiness as above.
14. Polish: mobile/a11y, honest progress, share blank flow only, rehearsed demos.

## Next
Implement Feature 1 in build mode. Needs: official ASRS text, model/provider choice at 3/5.
