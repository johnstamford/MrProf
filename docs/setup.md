# Setup (Feature 1)

Prerequisite: Docker Desktop (or Docker Engine + Compose v2). Nothing else required.

## Start

```sh
cp .env.example .env   # once; never commit .env
docker compose up --build
```

Open http://localhost:3000 — the page reports API and MongoDB reachability,
and `/api/health` reaches FastAPI through the intended Next.js rewrite route.

## Verify

```sh
docker compose config                       # compose file is valid
curl -s http://localhost:3000/api/health    # {"ok":true,"service":"api"}
curl -s http://127.0.0.1:8000/ready         # {"ok":true,"mongo":"ok"}
curl -s http://127.0.0.1:8000/spike/agent-framework
docker compose ps                           # all three services healthy
```

Persistence: `docker compose down && docker compose up -d`, then re-check
`/ready` and any seeded data — the `mrprof_mongo_data` named volume survives
ordinary restarts. MongoDB publishes no ports; it is reachable only inside
the compose network.

## Dev database UI (optional)

```sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
# open http://localhost:8081 (Mongo Express, localhost only)
```

`docker-compose.dev.yml` is never loaded by plain `up`, so the default stack
keeps MongoDB portless. Stop the UI with
`docker compose -f docker-compose.yml -f docker-compose.dev.yml stop mongo-express`.

## Reset

```sh
docker compose down            # keep data
docker compose down -v         # also delete the mongo volume (data loss)
```

## Notes

- Dependency pins: `api/requirements.txt`, `web/package.json`.
- Agent Framework approach (spike): per-assessment session blob persisted in
  MongoDB alongside assessment state, restored per request. Proven by
  `GET /spike/agent-framework` (import + insert/read/delete round-trip).
  Full interview wiring lands in Feature 5.
