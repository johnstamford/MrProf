# Release notes (pre-submission stub)

## Done (Features 1–16, F10a, F11-min, F12-min, F13-min, 15–16)

- Assessment sessions (code + password), ASRS v1.1 6Q deterministic scoring
  (`original-0-6`), screening + interview briefings with exact-quote citations.
- Full adaptive interview (14 objectives, taster 6), batch evidence extraction,
  tensions/contradictions retained, reviewer annotate (accept/amend/reject),
  3-section clinician report, frozen synthetic demo set (`/demo`, 4 personas),
  Tailwind UI overhaul, consent/invite/delete/rate-limit hardening.

## Known limitations

- Live-turn latency ~10–17 s (model path); hermetic dummy path ~200 ms.
- Topics/taxonomy are `draft — not clinically validated` (interim
  psychology-student view only); synthetic success ≠ clinical validity.
- No PDF beyond print CSS; no clinician dashboard; no password recovery.
- Risk workflow is a static non-monitored signpost (F10b deferred).

## Real-user opening

Disabled by default. Bounded 2-day invite-link + consent opening only, via
`docker-compose.opening.yml` (see `docs/opening.md`). Otherwise local and
synthetic use.
