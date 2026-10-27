# MrProf — Ordered Feature Plan

Planning baseline: 26 October 2026. All features below are planned, not implemented.

Read `PROJECT_OVERVIEW.md` first. Build one feature at a time, keep changes focused, and update this plan with implementation status, verification evidence, and remaining limitations. Do not infer that a working prototype is clinically validated or ready for real-user data.

## Milestones

- **A — Working prototype:** Features 1–6 produce a short end-to-end journey using synthetic inputs.
- **B — Evaluated hackathon MVP:** Features 7–12 add evidence traceability, broader interview coverage, review, and repeatable evaluation.
- **C — Public MVP stretch goal:** Features 13–14 prepare and release access for real people answering as themselves.

## 1. Project and Docker setup

**Deliver:** Next.js/React frontend, Python/FastAPI backend, MongoDB, Docker Compose, environment examples, health checks, and setup instructions.

**Acceptance:**
- One documented command starts the local stack from a fresh checkout with documented prerequisites.
- Frontend reaches the backend through the intended route; backend reaches MongoDB.
- Database survives ordinary container restarts through a persistent volume.
- MongoDB is not exposed publicly; secrets are excluded from source control.
- Dependency versions are pinned and the currently supported Agent Framework integration approach is identified.

**Depends on:** None. Pick routine package/tooling defaults and document them.

## 2. Assessment session and persistence

**Deliver:** Assessment creation, stage/status model, access mechanism, durable progress, and resume behavior.

**Decision needed first:** Assessment-key access versus registration; access-secret recovery and ownership. Do not equate an assessment ID with permission to read it.

**Acceptance:**
- User can start, close the browser, restart services, and resume without losing saved progress.
- An unauthorized visitor cannot read, submit to, or retrieve another assessment/report.
- Duplicate submissions and stale concurrent updates cannot create duplicate turns or overwrite newer state.
- Access secrets are not exposed in ordinary logs or analytics.

**Depends on:** 1.

**Status (27 Oct 2026): ✅ done — implemented and verified.**
- `docker compose up --build` starts web → api → mongo; `/api/health` → `{"ok":true}`,
  `/ready` → `{"ok":true,"mongo":"ok"}`, web page reports both reachable.
- Agent Framework spike green: `agent-framework==1.23.0` installed, session-blob
  Mongo round-trip `ok` via `GET /spike/agent-framework`. Note: requires
  `fastapi==0.141.1` (`agent-framework-ag-ui` caps `fastapi<0.142`).
- Persistence verified: seeded doc survived `down`/`up` via `mrprof_mongo_data`
  named volume; probe cleaned up afterwards.
- MongoDB publishes no ports; api bound to `127.0.0.1:8000` only; `.env` ignored,
  no secrets in repo.
- Remaining: model/provider choice + interview wiring (Feature 5).

## 3. Six-question ASRS screening

**Deliver:** Official fixed instrument, frequency controls, attribution, answer validation, deterministic scoring, and persisted scoring metadata.

**Decision needed first:** Select original 0–6 or summed 0–24 scoring using the official documentation.

**Acceptance:**
- Official wording, instructions, response options, and attribution are preserved.
- All six answers are required for a valid result; missing values are not scored as zero.
- Boundary and representative scoring cases match the selected official rules, including question-specific thresholds if using the original method.
- Stored result identifies instrument, scoring method/version, answers, and completion time.
- No LLM scores or rewrites the instrument.

**Depends on:** 2.

## 4. Screening report and interview transition

**Deliver:** Immediate screening report, explanation, and optional continuation to stage two.

**Acceptance:**
- Report can be reopened from the saved assessment.
- Both positive and below-threshold results offer the interview.
- Copy explains the screening result without diagnosis, exclusion, probability percentages, or unsupported severity claims.
- Report clearly identifies the selected scoring method.
- Screening answers are available to the later interview without requiring re-entry.

**Depends on:** 3.

## 5. Interview API and configurable model connection

**Deliver:** FastAPI interview endpoints, Microsoft Agent Framework execution, server-side provider configuration, and structured Pydantic outputs.

**Acceptance:**
- One submitted answer is durably saved and produces one next question through the real API/model path.
- Provider, model, base URL, and server-side credential reference are configurable.
- Provider-specific structured-output behavior is checked; unsupported capability produces an actionable error rather than silent malformed data.
- Timeouts, malformed output, retries, and model failures do not lose the saved answer or generate duplicate turns.
- Credentials remain server-side; request/model cost limits are bounded.

**Depends on:** 2. Can be developed after 4 without requiring full interview content.

## 6. First complete interview journey

**Deliver:** One-question UI, a small versioned topic set, basic objective selection, persistence, completion, and an initial report.

**Acceptance:**
- A synthetic user completes screening → short interview → two reports.
- Questions use the screening/history context and avoid obvious repetition.
- Save-and-resume works between interview questions.
- Completion is explicit; uncovered topics are shown as gaps.
- Initial briefing distinguishes patient statements from system interpretation and makes no diagnostic conclusion.

**Depends on:** 4–5.

**Milestone A:** Runnable prototype. The short flow is not represented as comprehensive assessment coverage.

## 7. Transcript and evidence engine

**Deliver:** Taxonomy v0.1, original transcripts, stable segmentation, evidence extraction, citations, coverage records, and version metadata.

**Decision needed first:** Define initial codes, inclusion/exclusion rules, examples, and mapping to evidence objectives. Seek clinical review rather than claiming validity from software tests.

**Acceptance:**
- Original wording and formatting are preserved independently of extracted evidence.
- Every observation references exact existing source spans; altered or missing quotes are rejected.
- Denial, uncertainty, missing information, and candidate criterion mapping remain distinct.
- Re-extraction creates versioned outputs without changing original responses.
- Contradictory observations remain inspectable rather than silently merged.
- Hand-reviewed synthetic examples check semantic support, not merely citation existence.

**Depends on:** 6.

## 8. Synthetic patient test runner

**Deliver:** SPIT-based patient preparation, persona extraction, simulator, API driver, saved transcripts, and reproducible configuration.

**Acceptance:**
- A simulated patient completes the real screening/interview API journey.
- Original profile, reference transcript, persona, run transcript, and results are stored separately.
- The interviewer cannot access evaluation ground truth or persona instructions.
- Persona extraction is checked for invented details and lost uncertainty.
- Runs have turn/time/cost limits and record model/content versions.
- Cases include vague answers, denials, contradictions, incomplete recall, and alternative explanations.

**Depends on:** 6–7. Use synthetic data exclusively.

## 9. Full planned adaptive interview coverage

**Deliver:** Expanded clinical-topic mapping, YAML objectives, interview skills, gap prioritization, and bounded completion logic.

**Acceptance:**
- Coverage definitions systematically address the 18 symptom items plus onset/history, duration, settings, impact, and relevant alternative explanations.
- One response can satisfy several information objectives where actually supported.
- Frequent screening responses do not automatically establish symptoms or causation.
- Topics can close through useful evidence, clear denial, or documented inability to provide information.
- Every question has an internal objective, reason, and source content version.
- Completed reports distinguish explored topics from missing evidence and clinician judgments still needed.

**Depends on:** 7–8. Compare candidate changes using the synthetic runs.

## 10. Interview quality and recovery controls

**Deliver:** Question validation, repetition limits, neutral clarification, interruption handling, and a defined risk-disclosure behavior for the intended deployment.

**Acceptance:**
- Repeated, leading, compound, off-objective, and already-answered questions are handled through bounded validation/regeneration.
- Unhelpful answers trigger limited clarification, then a recorded gap or a clear user choice.
- “Cannot remember” is respected; uncertainty is not converted into absence or invented detail.
- Failed model calls and interruptions leave a resumable assessment.
- Synthetic risk scenarios follow a documented, clinician-designed process; no implication of live monitoring is made.

**Depends on:** 9. Real-user release remains blocked on resolving the real-world response process in feature 13.

## 11. Final reports and basic clinician review

**Deliver:** Final screening and evidence reports, source navigation, review annotations/corrections, and download behavior.

**Decision needed:** HTML/download format, PDF priority, and minimum clinician-review scope. Multi-patient dashboard is optional unless explicitly added to MVP scope.

**Acceptance:**
- Both reports remain available separately after completion.
- Findings link to supporting transcript passages and show source type.
- Denials, uncertainty, contradictions, and incomplete coverage are visible.
- A reviewer can accept/amend/reject interpretations without changing the original transcript or screening result.
- Unreviewed outputs cannot appear clinician-approved.
- Report access follows assessment authorization; no public-by-default report links.

**Depends on:** 7 and 9–10.

## 12. Independent evaluation and refinement

**Deliver:** Ground-truth evaluation, fixed regression cases, benchmark summaries, and documented limitations.

**Decision needed:** Metrics, denominators, and passing thresholds before treating a benchmark as a release gate. Initial sample proposal: 10 personas × 3 runs.

**Acceptance:**
- Measure discovered relevant facts, unsupported findings, citation support, contradictions, repetition, question counts, stopping behavior, failures, latency, and cost.
- Independent checks include human-reviewed samples rather than relying solely on an LLM evaluator's score.
- Compare versions without changing fixtures or passing criteria silently.
- Fix material failures and document unresolved limitations.
- Verify deterministic scoring, authorization, persistence, and the complete journey with focused checks.
- Treat question/time targets as hypotheses. Synthetic runs do not establish human completion time or clinical validity.

**Depends on:** 8–11.

**Milestone B:** Evaluated synthetic-data hackathon MVP, with remaining clinical limitations explicit.

## 13. Public-demo readiness — real-user stretch goal

**Deliver:** Defined and implemented real-user data handling, public access controls, abuse protection, consent, and deployment configuration.

**Decisions needed before opening access:**
- Confirm access/identity model and recovery behavior.
- Define anonymisation/redaction versus identifiable storage; no-account access alone is not anonymity.
- Define retention, deletion, backups, model-provider data handling, and permitted logging/analytics.
- Define and review the process for risk disclosures and explain whether anyone is monitoring submissions.

**Acceptance:**
- Users can understand what is collected, where it goes, who can access it, how long it stays, and how to delete it.
- Cross-assessment access is rejected for all answer/report/review endpoints.
- Deletion and retention behavior are verified across linked records and any retained copies according to the stated policy.
- Frontend is reachable through HTTPS/Cloudflare Tunnel; MongoDB is not publicly exposed.
- Rate/input limits, bounded retries, model budgets, and error recovery work.
- Secrets and sensitive answers are absent from routine logs, analytics, source control, and public fixtures.
- Deployment is checked using synthetic data before admitting real-user information.

**Depends on:** 12 and the privacy/clinical decisions above. A synthetic-only demo can launch without claiming this milestone.

## 14. MVP polish and launch

**Deliver:** Mobile/accessibility polish, honest progress messaging, reliable demo cases, setup/operating documentation, and an invitation-sharing flow if included.

**Acceptance:**
- A new visitor can complete both stages in one sitting or resume later and retrieve both reports.
- Actual usability testing measures completion time, abandonment, comprehension, and usefulness; estimates are revised accordingly.
- Progress messages do not promise an exact remaining count when the interview can branch.
- Keyboard navigation, labeled controls, loading states, and failure/retry states work.
- Share action invites others to try the experience without exposing personal answers, access keys, or reports.
- Final demo is rehearsed with known synthetic scenarios and clear limitations.
- Release notes identify completed features, unresolved issues, and whether real-user access is enabled.

**Depends on:** 13 for public real-user launch; 12 for a synthetic-data demonstration.

**Milestone C:** Public MVP stretch goal, if the agreed readiness conditions are met.

## Implementation handoff

For each feature, ask OpenCode to read the overview and this plan, inspect existing code, implement only the selected feature and necessary dependencies, and run focused verification against its acceptance criteria. Ask it to report changes, verification results, decisions, and incomplete items. Checkpoint working milestones in Git.

Resolve product-affecting open decisions with the project owner. Routine reversible implementation choices can be made and documented. Do not add billing, prescribing, EHR integration, automated diagnosis, an 18Q instrument, or a complex agent-per-symptom architecture without an explicit scope change.
