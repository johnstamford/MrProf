# MrProf — prepare for your ADHD assessment, in your own words

▶️ Project video: https://youtu.be/rBYZewVERxM

MrProf guides you through the official ASRS v1.1 6-question screening and a
one-question-at-a-time interview, then assembles a briefing grounded in your
exact words — quotes, line numbers, denials, uncertainty, and gaps included —
for a clinician to review.

What it does / does not do: MrProf organizes what you report so a clinician
can review it. It does not diagnose, rule anything out, estimate probabilities,
or assign severity; topics and evidence codes are drafts and have not been
clinically reviewed.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose v2). Nothing else required.
- No API key needed for the default stub. For live-model phrasing, set
  `LLM_PROVIDER=openai-compatible` plus `LLM_MODEL` / `LLM_BASE_URL` /
  `LLM_API_KEY` in `.env` (credentials stay server-side).

## One-command start

```sh
cp .env.example .env   # once; never commit .env
docker compose up --build
```

Open http://localhost:3000 — the landing page reports API/Mongo reachability.

Verify:

```sh
docker compose config
curl -s http://localhost:3000/api/health   # {"ok":true,"service":"api"}
curl -s http://127.0.0.1:8000/ready          # {"ok":true,"mongo":"ok"}
```

Journey routes: `/start` (code + password, consent) → `/screening` (6 fixed
questions) → `/report` (screening report + interview offer) → `/interview`
(full 14 objectives or 6-question taster) → briefing on completion.
`/demo` is the frozen synthetic gallery; `/consent` renders the consent text
from the API.

Persistence: close the browser and resume on `/start` with code + password.
`docker compose down` keeps data (named volume `mrprof_mongo_data`);
`docker compose down -v` deletes it. MongoDB publishes no ports in the
default stack; localhost-only DB/UI ports live in `docker-compose.dev.yml`.
Public HTTPS for the bounded opening lives in `docker-compose.opening.yml`
(see `docs/opening.md`).

## 60-second demo script (vague answer → follow-up → citation)

1. Open http://localhost:3000/demo/vague-01 — frozen synthetic report
   (`SYNTHETIC DEMO — not a real person` watermark on every surface).
2. Find a thin/vague answer (e.g. bills left on the counter, no dates given).
3. See the follow-up it triggered and the tightened evidence card: one-sentence
   system note plus the shortest exact quote with `line N · segment ID`.
4. Click the quote/line link — it jumps to the same words in the full
   line-numbered transcript. Denials, uncertainty, tensions, and gaps stay
   visible; nothing is rewritten.

Live version: `/start` → screening (answer `Sometimes` to Q1–Q3, `Often` to
Q4 for a 4/6 positive) → `/report` → Continue to interview → give a vague
answer and watch the targeted follow-up arrive.

## Development

```sh
docker compose exec api pytest tests -q   # backend suite (hermetic dummy LLM)
python sim/eval.py                        # F12-min regression: 4 profiles × 2 runs
python sim/export_demo.py                 # re-freeze web/public/demo/*.json
npm run build                             # in web/
```

Stack: Next.js/React + Tailwind, Python/FastAPI + Microsoft Agent Framework
(`agent-framework==1.23.0`, `fastapi==0.141.1`), MongoDB. Pins in
`api/requirements.txt` and `web/package.json`. Details in `docs/setup.md`.

## Limitations, stated once

Research prototype, not clinical: draft topics/taxonomy (`topics-v0.6-draft`)
not clinically validated; every briefing is an `UNREVIEWED — not
clinician-approved` draft until a reviewer annotates it. Synthetic runs prove
the pipeline, not clinical validity or real-user timing. Live-model turns take
~10–17 s each. No real-time monitoring or crisis support (see consent). No
password reset — lose the code/password and the assessment is unrecoverable.
Real-user opening: invite-link + consent-gated 2-day opening only
(`docs/opening.md`); otherwise local/synthetic use.
