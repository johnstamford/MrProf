# AGENTS.md

Greenfield repo (baseline 26 Oct 2026): no app code exists yet. `README.md` is `TBD`.

## Sources of truth

- Read `PROJECT_OVERVIEW.md` before `FEATURE_PLAN.md` before any implementation.
- Build one feature at a time in plan order; implement only the selected feature + necessary dependencies.
- Distinguish agreed choices vs provisional targets vs open decisions — never silently promote a proposal to a requirement.
- After each feature, update `FEATURE_PLAN.md` with status, verification evidence, and remaining limitations. Checkpoint working milestones in git.
- Out of scope without explicit scope change: billing, prescribing, EHR integration, automated diagnosis, 18-item ASRS, agent-per-symptom architecture.
- Explicit owner-authorized scope exception (Nov 2026, hackathon demo only): an experimental *provisional sketch* panel (`api/app/provisional.py`, `PROVISIONAL_SKETCH` env: `demo-only` default / `on` / `off`). Deterministic pattern summary, never a diagnosis, no probability/severity; frozen synthetic demos carry it, real journeys only with `on` (local judging only). Must be `demo-only`/`off` for any real-user opening; strip before clinical use. Revisit/remove post-hackathon.

## Planned stack (not yet implemented — verify, don't assume)

Next.js/React + Python/FastAPI + MongoDB via Docker Compose; Microsoft Agent Framework; OpenAI-compatible endpoints; Pydantic; Cloudflare Tunnel. Pin dependency versions during Feature 1 setup. Verify current Agent Framework session-serialization API before using it — the plan fixes none. No build/test/lint commands exist yet; Feature 1 defines the one-command local start.

## Hard domain rules (will fail acceptance if broken)

- ASRS v1.1 6Q only (distinct from ASRS-5). Preserve official wording, instructions, discrete frequency responses, attribution. No continuous slider, no LLM paraphrase/rewrite, no dynamic adaptation.
- Score deterministically in code, never via LLM. All 6 answers required — missing is not zero. Stored result must record instrument, scoring method/version, answers, completion time.
- Scoring method is an open decision: original 0–6 (≥4 positive, question-specific thresholds) vs summed 0–24 (≥14 positive). Implement one from the official source, label it explicitly, never conflate.
- Never claim diagnosis, exclusion, disease probability %, or severity labels. Positive screen = "further assessment may be useful"; below threshold ≠ no ADHD. Always offer the interview regardless of screening result.
- Interview: one question at a time, internal objective + reason logged per question. Accept denials/uncertainty; never pressure for memories, infer causation, or convert "cannot remember" into absence. Retain unresolved contradictions; completion = gathering ended with gaps documented.

## State, evidence, reports

- MongoDB is durable source of truth; no in-memory agent per patient. Collections: `assessments`, `transcripts`, `evidence`, `reports`, linked by `assessment_id`.
- Per-assessment concurrency control + idempotent submissions (retries/double-clicks must not duplicate turns or overwrite newer state).
- IDs are not authorization. Assessment keys (vs accounts) still undecided — never equate ID with permission.
- Preserve original answers verbatim (paragraph breaks, lists) with stable segment IDs. Every observation cites exact existing source spans; validate quote match, reject altered/missing quotes. Keep distinct: present / explicitly denied / uncertain / missing. Candidate criterion links stay separate from observations with rationale. Re-extraction versions outputs, never rewrites originals. Reviewer can accept/amend/reject without touching transcript/screening; unreviewed output must never look clinician-approved.
- Keep credentials server-side only. Keep secrets, transcripts, and sensitive answers out of logs, analytics, fixtures, and git. MongoDB never publicly exposed.

## Testing

- Synthetic data only until Feature 13 readiness is explicitly met. Never commit real participant data.
- Simulator (SPIT-based profiles → persona → simulator → real FastAPI endpoints → independent evaluation) stays separate from the interview harness. Ground-truth profile/persona instructions never reach the interviewer.
- Focused checks first: scoring boundaries, auth isolation, persistence/resume, citation validity, full journey. Simulator runs (proposed 10 personas × 3, limits on turns/time/cost) complement, don't replace, these. Synthetic success ≠ clinical validity or real-user timing.
