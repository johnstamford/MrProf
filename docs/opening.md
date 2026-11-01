# 2-day real-user opening — runbook (F13-min)

This is the bounded public opening: invite-link only, synthetic demo first,
manual deletion, then a database wipe when it ends. Full retention/backup
policy and the clinician risk workflow stay post-hackathon.

## 1. Prerequisites

- A machine with Docker Compose and a public hostname via Cloudflare Tunnel.
- A Cloudflare Tunnel token (`TUNNEL_TOKEN`) routing to the web service.
- A real model behind the OpenAI-compatible endpoint (`LLM_PROVIDER`,
  `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`) — check it with a synthetic
  run before admitting anyone.
- An invite code you distribute yourself (`PUBLIC_INVITE_CODE`).

## 2. Pre-opening check (synthetic data only)

1. Copy `.env.example` to `.env` and set real values, including:
   `REQUIRE_CONSENT=1`, `PUBLIC_INVITE_CODE=<code>`, `RATE_LIMIT_PER_MIN=60`.
2. `docker compose -f docker-compose.yml -f docker-compose.opening.yml up --build`
3. `docker compose exec api pytest tests -q` — full suite green.
4. Run one synthetic journey end to end and open its reports + frozen
   `/demo` example in a browser (proves the tunnel route works).
5. `GET /api/config` shows `invite_required: true, consent_required: true`.
6. `GET /api/consent` names the configured model — confirm it matches the
   model you intend to use.

## 3. During the opening

- Share the tunnel URL **with the invite code**, e.g.
  `https://<your-host>/start` + code. No report-sharing feature exists:
  reports open only with the visitor's own code + password.
- What visitors see: consent page (`/consent`), invite + consent gates on
  `/start`, static non-monitored support note on `/start` and `/interview`,
  `UNREVIEWED — not clinician-approved` banner on every briefing.
- Abuse caps: POST rate limit (`RATE_LIMIT_PER_MIN`), 2000-char answer cap,
  bounded model retries/budgets. Watch api logs for `rate_limited` and
  `validation_fallback` warnings.
- Deletion requests: with the visitor's assessment code + password,
  `DELETE /api/assessments/<code>` removes the assessment, transcript,
  all evidence docs, and all reports (verified by `test_delete_cascades`
  in `api/tests/test_opening.py`). Without both, it cannot be retrieved —
  by design there is no reset.

## 4. Closing

1. Stop the tunnel (`docker compose down`) so the opening URL goes dark.
2. Wipe the database volume: `docker volume rm mrprof_mongo_data`
   (destroys all assessments, transcripts, evidence, and reports).
3. Confirm `docker compose up` starts clean with no prior records.

## 5. Known limitations (interim wording)

- Topics v0.4 / taxonomy v0.2 drafts: not clinically validated; interim
  psychology-student review only.
- Rate limiting is per-process memory, not a production WAF.
- No accounts, no password recovery, no clinician dashboard, no PDF export
  (print stylesheet instead). Full risk workflow deferred to F10b.
