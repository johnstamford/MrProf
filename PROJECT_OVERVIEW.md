# MrProf — Project Overview and Design Choices

Planning baseline: 26 October 2026. No application has been implemented yet.

## How to use this document

Read this file before implementing features in `FEATURE_PLAN.md`. It records the product direction agreed during planning. Distinguish agreed choices, provisional targets, and open decisions; do not silently turn proposals into requirements. Update both documents when an implementation decision changes the plan.

OpenCode with Muse 1.3 is the intended development setup. This does not determine which models the application itself uses.

## Product and purpose

MrProf helps adults complete ADHD screening and prepare a traceable account of their experiences for clinician review. Its core is an adaptive evidence-gathering workflow, rather than a general advice chatbot.

The system gathers and organizes patient-reported information. It does not diagnose ADHD, rule it out, prescribe treatment, or declare diagnostic criteria clinically satisfied. A qualified clinician makes those judgments.

Initial audiences:

- Adults preparing for an ADHD assessment.
- Clinicians and ADHD clinics reviewing pre-appointment information.
- Hackathon visitors exploring the experience.

Core demo: vague answer → targeted follow-up → useful evidence → clinician briefing with a supporting transcript citation.

## Agreed user journey

Two stages can be completed in one sitting, with save-and-resume available.

1. Start or resume an assessment.
2. Complete the six fixed ASRS v1.1 screening questions.
3. Receive an immediate screening report.
4. Choose whether to continue into the adaptive interview, regardless of screening result.
5. Answer one personalized question at a time.
6. Receive the interview evidence report and retain access to both reports.

The screening answers inform the interview, so the system should not ask users to repeat information unnecessarily. The interview must investigate relevant gaps and contradictory information rather than simply confirm the screening impression.

Provisional usability targets, to validate rather than advertise as established facts:

- Approximately 15–25 interview questions, including follow-ups.
- Approximately 20–30 minutes for both stages together.
- Shorter demonstration scenarios may cover fewer objectives, with incomplete coverage clearly identified.
- Scope must be adjusted if these targets cannot produce a useful briefing. Do not force completion or claim full clinical coverage to meet a time limit.

## Stage 1: ASRS v1.1 six-question screening

Use the ASRS v1.1 6Q instrument for adults 18+. It is distinct from ASRS-5, which has different permission requirements.

- Obtain the official instrument and retain its exact wording, instructions, response options, and attribution.
- Use its discrete frequency responses; do not invent a continuous slider, paraphrase questions with an LLM, or adapt the instrument dynamically.
- Calculate scores deterministically in application code, never through an LLM.
- Require all six answers before calculating a valid result. Missing answers are not zero scores.
- Record the instrument version, scoring method, responses, result, and completion date.

Two published scoring approaches were identified. Selection remains open:

| Approach | Calculation | Positive screening threshold |
|---|---|---|
| Original | Count responses meeting the official question-specific thresholds | At least 4 of 6 |
| Summed | Never=0, Rarely=1, Sometimes=2, Often=3, Very often=4; sum six responses | At least 14 of 24 |

The February 2024 Harvard update discusses the summed approach as more robust for research and prevalence estimation. Do not conflate the methods or present both as interchangeable numeric scores. Implement the selected method from the official source and label it explicitly.

Screening report:

- Instrument and scoring method.
- Answer summary and applicable score/threshold result.
- Plain-language explanation that a positive screen suggests further assessment may be useful, and a result below threshold does not exclude ADHD.
- Clear route to the optional interview for either result.
- No diagnosis, disease probability percentage, or unsupported severity label.

NYU's published terms permit free clinical, non-clinical, and commercial use of the six-question v1.1 screener with attribution, allowing electronic versions but no other modifications. Recheck the terms when implementing. The full 18-item checklist is outside the MVP and has separate licensing requirements.

## Stage 2: Adaptive interview design

Use a stateful interview harness with explicit evidence objectives.

| Component | Responsibility |
|---|---|
| Interview agent | Ask a clear, neutral question for the selected objective |
| Evidence extraction agent | Extract grounded observations, source spans, uncertainty, and candidate topic links |
| Deterministic planner | Select objectives using coverage, gaps, contradictions, and probing limits |
| Application rules | Enforce response validation, persistence, completion, retry limits, and configured escalation behavior |
| Report generator | Assemble a briefing grounded in stored evidence |

Content organization:

- `SKILL.md` and examples describe how the application agent interviews.
- YAML topic definitions describe what evidence to gather and when exploration can stop.
- Version skills, topics, taxonomy, and prompts.
- These application skill files are distinct from instructions for the coding agent.

Interview principles:

- Ask one primary question at a time; avoid hiding several questions inside one prompt.
- Start open-ended and use targeted follow-ups for missing information.
- Extract several observations from a detailed answer where appropriate.
- Do not equate reported difficulties with ADHD causation.
- Accept denials and uncertainty; do not repeatedly pressure users for examples or memories they cannot provide.
- Clarify conflicting accounts neutrally and retain unresolved conflicts.
- Limit repeated probing and regenerate invalid questions only within bounded retries.
- Record an internal objective and reason for each question.
- Interview completion means the planned information gathering ended, with gaps documented; it does not mean sufficient evidence for diagnosis.

## Evidence model — proposed baseline, not yet clinically reviewed

Keep three linked layers:

1. **Evidence:** what was actually reported, its context, and exact transcript source.
2. **Coverage:** which objectives were explored, remaining gaps, and unresolved issues.
3. **Clinical review:** candidate criterion links and clinician acceptance, amendment, or rejection.

Proposed taxonomy families:

| Family | Examples |
|---|---|
| Reported behavior | Sustaining attention, organization, task completion, forgetfulness, restlessness, interrupting |
| Development and course | Childhood experiences, onset, duration, persistence, changes over time |
| Functional impact | Work, education, relationships, daily living |
| Context and possible contributors | Sleep, mood, anxiety, substances, medication, physical health |
| Coping and support | Reminders, family support, extra effort, avoidance |
| Background and goals | Presenting concerns, assessment goals, previous assessments, family history |

Each observation should support:

- Stable ID and taxonomy version.
- Descriptive observation and one or more codes.
- Assertion: reported present, explicitly denied, or uncertain.
- Life period, setting, frequency, timeline, concrete example, and consequences where supplied.
- Source type: self-report, patient recounting another person, direct informant, or document.
- Message/segment IDs and exact supporting text spans.
- Candidate criterion links with rationale, separate from the observation.
- Review status and unresolved links to conflicting observations.
- Explicit missing values, rather than inferred or fabricated facts.

Preserve the original answer, paragraph breaks, and lists. Create deterministic logical segments with permanent IDs and stable human-readable section/line references. Validate that citations exist and that stored quotes match the original text. Existence checks alone do not establish that an interpretation is supported.

Clinical coverage needs systematic exploration of symptoms, childhood history, persistence, settings, impact, and other explanations. A self-report interview cannot independently supply documentary corroboration, a clinician's mental-state examination, or diagnostic judgment. Do not treat absent corroboration as a negative finding. The taxonomy and coverage mapping need qualified clinical review before claims of clinical adequacy.

## Technology stack

| Layer | Planned choice |
|---|---|
| Development | VS Code + OpenCode, using Muse 1.3 |
| Frontend | Next.js + React |
| Backend API | Python + FastAPI |
| Agent orchestration | Microsoft Agent Framework |
| Model connectivity | Standard OpenAI-compatible endpoints; configurable local, OpenRouter, or other compatible providers |
| Structured data | JSON and Pydantic |
| Database | MongoDB |
| Interview content | Versioned Markdown skills and YAML topic definitions |
| Local deployment | Docker Compose |
| Public access | Cloudflare Tunnel |
| Synthetic patient generation | SPIT Generation, adapted into a separate test system |

Pin supported dependency versions during setup. Verify current Microsoft Agent Framework interfaces before implementation; no specific session serialization API is fixed by this plan. CSS framework, Python package manager, testing libraries, and exact models remain implementation decisions.

## Request lifecycle and state

Patient UI → FastAPI → load MongoDB state → extract evidence → update coverage → select objective → generate/validate question → persist result → return the next question.

- MongoDB is the durable source of truth; do not depend on a continuously running in-memory agent per patient.
- Initially supply full conversation context where model limits permit. Detect context limits explicitly; do not silently truncate. Later context optimization is separate work.
- Persist any necessary Agent Framework session state alongside the assessment and restore it per request.
- Include per-assessment concurrency control and idempotent submission behavior so retries and double clicks do not duplicate turns or overwrite state.
- Keep model credentials on the backend and out of the frontend and repository.
- Record model/provider and prompt/content versions to support debugging and evaluation.

Four core MongoDB collections:

| Collection | Responsibility |
|---|---|
| `assessments` | Stage/status, screening result, interview coverage, progress, version, and agent-session data as needed |
| `transcripts` | Original questions/answers and stable numbered segments |
| `evidence` | Extracted observations, citations, uncertainty, and review state |
| `reports` | Versioned screening and interview reports |

Link records with `assessment_id`. Additional collections may be introduced for a concrete need. IDs identify records; IDs alone are not authorization.

## Reports and review

- Report 1 is a fixed, reproducible screening summary.
- Report 2 summarizes patient-reported experiences with supporting citations, context, denials, uncertainties, contradictions, and unexplored topics.
- Retain both reports separately; a combined download is optional.
- Render HTML first. PDF export and its priority remain open.
- Basic clinician review should allow inspection of sources and recorded corrections without silently rewriting the original transcript or screening answers.
- Public users receive their own reports. An unreviewed report must not appear clinician-approved.
- A multi-patient clinic dashboard is proposed; its minimum scope remains open.

## Testing and evaluation

Separate the patient simulator from the production interview harness.

SPIT profile/transcript generation → persona extraction → patient simulator → real FastAPI interview endpoints → independent evaluation.

- Preserve the original synthetic profile as evaluation ground truth.
- Preserve the generated reference transcript and extracted persona as separate artifacts.
- The simulated patient sees the roleplay persona; the interviewer sees only normal user inputs and screening answers. Ground truth is not passed to the interviewer.
- Validate persona extraction so it does not erase uncertainty or invent history.
- Include communication-style variations, denials, incomplete recall, contradictions, and non-ADHD explanations.
- Evaluate coverage, groundedness, citation accuracy, unsupported claims, repetition, stopping behavior, consistency, time, and cost.
- Initial benchmark proposal: 10 personas × 3 runs. Metrics and passing thresholds remain open.
- Synthetic success does not establish clinical validity or predict real-user completion time. Later usability and clinician review are separate validation steps.

Use focused automated checks for scoring, access, state consistency, citations, and the complete journey. Simulator evaluation complements rather than replaces these checks. Test libraries are not yet selected.

## Deployment, real-user stretch goal, and privacy

The core hackathon MVP is evaluated with synthetic patients. A stretch goal is public access for real people answering as themselves, supporting adoption and the hackathon's virality criteria. Public access is a separate readiness milestone.

- Run services through Docker Compose; expose the intended frontend route through Cloudflare Tunnel with HTTPS.
- Keep FastAPI/MongoDB private to the service network except through intended application routes. Do not publish MongoDB publicly.
- Choose assessment-key access versus accounts before implementing user access. Optional later account linking is only a proposal.
- If using assessment keys, generate strong random secrets; distinguish access secrets from assessment IDs and handle expiry/revocation/recovery deliberately.
- A no-account interview is not necessarily anonymous: answers can identify people. Resolve anonymisation/redaction separately from access control.
- Define consent, collected identifiers, model-provider data handling, retention, deletion, access isolation, backups, and logging before real-user launch.
- Keep transcripts, access secrets, and sensitive answers out of ordinary logs and analytics.
- Add rate limits, input limits, and bounded model use before public access.
- Do not include real participant data in source control, demo fixtures, public reports, or share links.
- Sharing should invite others to try the app; sharing personal answers/reports is not a default feature.
- Handling risk disclosures needs a qualified, designed process before real-user use; collecting a disclosure does not mean it has been clinically assessed or monitored.

## Open decisions

1. ASRS scoring method and exact versioned implementation source.
2. Assessment keys versus registration; recovery and ownership model.
3. Evidence-code definitions, clinical mapping, topic definitions, completion rules, and clinical reviewer.
4. Exact application models, provider compatibility, and model/session implementation details.
5. Evaluation metrics and pass thresholds.
6. Final report layout, PDF priority, and clinician-review/dashboard scope.
7. Real-user privacy, consent, retention, deletion, provider handling, and risk-disclosure workflow.
8. Public-demo launch scope and non-sensitive adoption metrics.

## Source references

These sources informed planning; they do not validate the product. Verify current instruments, interfaces, and terms before implementation.

- NICE NG87, assessment and diagnosis: https://www.nice.org.uk/guidance/ng87/chapter/recommendations
- UKAAN Adult ADHD Assessment Quality Assurance Standard: https://www.frontiersin.org/journals/psychiatry/articles/10.3389/fpsyt.2024.1380410/full
- NIMH ADHD overview: https://www.nimh.nih.gov/health/publications/attention-deficit-hyperactivity-disorder-what-you-need-to-know
- ASRS v1.1 6Q official instrument and usage terms: https://license.tov.med.nyu.edu/product/asrs6Qscreener
- ASRS v1.1 scoring update: https://www.hcp.med.harvard.edu/ncs/ftpdir/adhd/ASRS_v1.1_screener%286Q%29_scoring_update.pdf
- ASRS instrument directory: https://www.hcp.med.harvard.edu/ncs/asrs_2025.php
- ASRS 18Q licensing: https://license.tov.med.nyu.edu/product/asrs-v11-18-question-symptom-checklist
- SPIT Generation: https://github.com/ubcbraincircuits/SPIT_Generation
