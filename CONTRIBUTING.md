# Contributing

Contributions are welcome: new targets (FastAPI, Go, other Django setups), new scenarios, fixes, and results from other hardware.

## Development setup

```bash
uv sync                    # host-side script dependencies
uvx pre-commit install     # ruff + basic file checks on commit
./scripts/run.sh queue-contention static-nginx smoke   # check the harness works
```

CI runs ruff, Django system checks, and a short end-to-end run against every target. A PR should pass CI before review.

## Adding a target

A target is a directory under `targets/` that follows this contract:

1. **`compose.yml`**, with explicit CPU and memory limits on every service, read from env vars with defaults. Reuse the role names in `profiles/default.env` (`DB_*`, `WEB_*`, `WORKER_*`, `BROKER_*`) so one profile applies to every target.
2. **`target.env`**:
   - `APP_URL` (required): where the app listens on the host, e.g. `http://127.0.0.1:18080`
   - `PG_DSN` (optional): host-reachable Postgres DSN. Turns on `sample_pg.py`.
   - `JOB_TABLE` (optional): table with job timings. Turns on `collect_jobs.py`. It needs the columns `job_id`, `status`, `enqueued_at`, `started_at`, `finished_at`, with timestamps in epoch seconds.
3. **`GET /healthz`** returns 200 only when the app, database and workers are ready.
4. **The endpoints the scenario calls.** For `queue-contention`: `GET /items/<id>`, `POST /items`, `POST /enqueue?n=<k>` (returns 202).
5. **Optional executable hooks** in `hooks/`. They run from the repo with `COMPOSE_PROJECT_NAME` and `COMPOSE_FILE` exported, so `docker compose ...` inside a hook targets the right stack.
   - `hooks/seed`: load test data after `/healthz` passes.
   - `hooks/versions`: print a JSON object of versions to merge into `meta.json`.
6. **Pinned versions.** Pin image tags and use a lockfile for dependencies.

Use host ports 18080 (app) and 55432 (Postgres) unless the target needs something else. Only one target runs at a time.

To compare implementations fairly, keep everything except the thing being compared identical, and list any unavoidable differences in the README.

## Adding a scenario

A scenario is `scenarios/<name>.js`. Reuse `scenarios/lib/`:

- `env.js`: read settings. Scenario settings use the `SCENARIO_` prefix; `run.sh` forwards those to k6 and records them in `meta.json`.
- `schedule.js`: build a warm-up/ramp/hold timeline, turn it into `ramping-arrival-rate` stages, and tag requests with `step` and `phase`.
- `thresholds.js`: informational thresholds that make the summary carry per-step submetrics. They never fail a run.
- `summary.js`: `handleSummary` that writes `summary.json`, `steps.json` and `schedule.json` and prints a per-step table.

Export `setup()` returning `{ startEpochMs: runStartEpochMs() }` so the timeline is anchored precisely. Keep `scenarios/lib/` and `scripts/` free of anything specific to one target.

## Submitting results

- Run with an unmodified profile, or say exactly what you changed. `meta.json` records it either way.
- Use a quiet host: no other containers or heavy processes running.
- Run each target at least three times, alternating targets between runs.
- Commit the run folders and describe the host in the PR. `k6.json.gz` is gitignored because it gets large; attach it to the PR or a release instead.
- Smoke runs are not accepted as results.

## Pull requests

- Keep each PR to one change.
- Use conventional commit prefixes (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`).
- Never commit secrets. Nothing in this repo needs any.
