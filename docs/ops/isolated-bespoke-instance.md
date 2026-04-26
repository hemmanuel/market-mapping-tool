# Isolated Bespoke Instance

## Purpose

This runbook exists so the bespoke branch can run against a fully separate local data plane without touching the legacy stack.

The isolation boundary is:

- PostgreSQL on `localhost:55432`,
- Neo4j HTTP on `localhost:17474`,
- Neo4j Bolt on `localhost:17687`,
- MinIO API on `localhost:19000`,
- MinIO console on `localhost:19001`,
- pgAdmin on `localhost:15050`,
- bespoke backend on `localhost:8100`,
- and bespoke frontend on `localhost:3300`.

## Active Working Environment

For current bespoke migration work, diagnostics, validation, and operator checks must target this isolated data plane rather than the older default local stack.

The current bespoke database environment is expected to contain exactly one site. If a query returns multiple historical sites, you are almost certainly connected to the wrong Postgres or Neo4j instance.

In practical terms:

- the environment described in this runbook is the active source of truth for bespoke-runtime verification,
- the default local stack is not the environment of record for current bespoke debugging,
- and seeing three legacy sites means you are looking at the older database, not the new bespoke environment.

## What "safe" means here

Running the bespoke pipeline safely means:

1. the bespoke branch writes to its own Postgres database,
2. projects into its own Neo4j instance,
3. preserves artifacts in its own MinIO instance,
4. serves its API from its own backend port,
5. and serves its UI from a frontend that is explicitly pointed at that backend.

If any one of those targets still points at the legacy stack, the environment is not isolated.

## Start The Bespoke Data Plane

From the repo root:

```bash
./scripts/start_bespoke_stack.sh
```

This launches `docker-compose.bespoke.yml`, which provisions a separate Postgres, Neo4j, MinIO, and pgAdmin set with bespoke-only ports, names, and volumes.
The script also uses a dedicated Docker Compose project name, so starting the bespoke stack does not mutate the default local stack.

To stop and remove that stack later:

```bash
./scripts/stop_bespoke_stack.sh
```

## Apply Migrations To The Bespoke Postgres

From the repo root:

```bash
./scripts/migrate_bespoke_db.sh
```

This targets `market_bespoke_db` on `localhost:55432`, not the default Postgres instance.

## Run The Bespoke Backend

From the repo root:

```bash
./scripts/run_bespoke_backend.sh
```

The script pins the backend to the bespoke infrastructure endpoints and exposes the API on `http://localhost:8100`.

The backend still needs the existing non-infrastructure secrets and provider configuration, such as LLM, search, and Clerk-related values. Those should continue to come from the current shell environment or the repository `.env` file.

## Run The Bespoke Frontend

From the `frontend/` directory or repo root:

```bash
./scripts/run_bespoke_frontend.sh
```

The script serves the UI on `http://localhost:3300` and forces `NEXT_PUBLIC_API_BASE_URL=http://localhost:8100`, so the bespoke frontend cannot silently talk to the legacy backend on `localhost:8000`.

The frontend now proxies backend traffic through its own `/api/backend/...` route before forwarding it to the configured API base URL. That keeps the browser pinned to the bespoke frontend origin even when the backend runs on a different port.

The frontend still needs its normal Clerk environment variables through the existing `frontend/.env.local` or the shell environment.

## Verification Checklist

Before creating a new pipeline, verify:

1. `http://localhost:8100/health` returns `{"status": "ok"}`,
2. `http://localhost:3300` loads the bespoke UI,
3. the backend logs show connections to `localhost:55432`, `localhost:17687`, and `localhost:19000`,
4. `http://localhost:17474` opens the bespoke Neo4j browser,
5. `http://localhost:19001` opens the bespoke MinIO console,
6. Postgres `sites` contains exactly one row in the active bespoke environment,
7. and any query that surfaces multiple historical sites is treated as a wrong-environment warning rather than as bespoke-runtime state.

## Safe Operating Rules

- Always start the bespoke frontend with `./scripts/run_bespoke_frontend.sh`.
- Always start the bespoke backend with `./scripts/run_bespoke_backend.sh`.
- Always run migrations with `./scripts/migrate_bespoke_db.sh`.
- Do not point the bespoke frontend at `localhost:8000`.
- Do not run bespoke migrations against `localhost:5432`.
- Do not reuse the legacy MinIO bucket for bespoke runs.

## First Bespoke Run

After the isolated stack, migrations, backend, and frontend are all up:

1. sign in through the bespoke frontend on `localhost:3300`,
2. create a brand new pipeline there,
3. start acquisition from that bespoke command center,
4. wait for acquisition to finish on the bespoke backend,
5. then launch graph generation from that same bespoke pipeline record.

That sequence ensures the new run stays entirely inside the bespoke stack from front-door acquisition through durable graph projection.
