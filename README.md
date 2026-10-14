# k6-bench

A small, reusable [k6](https://k6.io) harness for measuring how a backend behaves under load, plus the scenarios built on it.

The first scenario answers one question:

> How much background work can a Postgres-backed job queue handle before it hurts the app sharing the same database?

It runs the same Django app twice: once with [Procrastinate](https://procrastinate.readthedocs.io) (queue lives in Postgres) and once with Celery + Redis (queue lives in Redis, as the baseline). Normal app traffic runs at a fixed rate while background jobs step up from 0 to hundreds per second, and the harness records what happens to app latency, queue latency and Postgres.

The harness is built so the answer can come out either way. "It barely matters" is as valid a result as "it degrades at X jobs/s".

## What this is not

- **Not a throughput benchmark.** It doesn't measure how fast workers can empty a queue. [python_queue_benchmark](https://github.com/steventen/python_queue_benchmark) does that: 10 workers, 20,000 print-only jobs, total time. This repo feeds jobs at fixed rates and watches the effect on the app.
- **Not a general verdict.** Results come from one host, a synthetic workload and specific resource limits. Different hardware will give different numbers. Every run records its host, limits and versions so you can judge how far its results carry.

## Requirements

- A Linux host. `run.sh` uses `--network host` for k6, and `meta.py` reads `/proc` for host details.
- Docker with Compose v2
- [uv](https://docs.astral.sh/uv/) (for the host-side Python scripts)
- bash, curl, jq

k6 runs in a container (`grafana/k6`), so it doesn't need to be installed.

## Quick start

```bash
# Short run (~4 min) to check everything works
./scripts/run.sh queue-contention django-procrastinate smoke

# Full run with the default profile
./scripts/run.sh queue-contention django-procrastinate
./scripts/run.sh queue-contention django-celery
```

`run.sh <scenario> <target> [profile]` builds and starts the target, waits for `/healthz`, seeds data, starts the samplers, runs k6, collects job timings, then tears everything down. Results go to `results/<timestamp>-<scenario>-<target>[-<profile>]/`.

Set `KEEP_UP=1` to leave the target running afterwards.

## Layout

```
targets/
  django-common/          shared Django app, Dockerfile, compose.base.yml, hooks
  django-procrastinate/   compose.yml + target.env (Procrastinate backend)
  django-celery/          compose.yml + target.env (Celery + Redis backend)
  static-nginx/           trivial target used to test the harness itself
scenarios/
  lib/                    step schedule, tagging, thresholds, summary helpers
  queue-contention.js
profiles/                 resource limits and scenario settings (env files)
scripts/
  run.sh                  orchestrates one run
  meta.py                 writes meta.json
  sample_pg.py            samples Postgres stats views every 10s
  sample_containers.py    samples docker stats every 10s
  collect_jobs.py         exports job timings, per-step queue latency, backlog
results/                  one folder per run
```

## The queue-contention scenario

Two k6 scenarios run together:

| k6 scenario | Executor | What it does |
|---|---|---|
| `app_traffic` | `constant-arrival-rate` | Fixed rate for the whole run: ~80% `GET /items/<random id>`, ~20% `POST /items` |
| `enqueue` | `ramping-arrival-rate` | Warm-up at 0, then steps through job rates with a short ramp and a hold at each |

Every request is tagged with its `step` (the job rate) and `phase` (`warmup`, `ramp`, `hold`). Only `hold` phases are analysed. Thresholds exist only so the summary carries per-step percentiles; they never fail a run.

Settings (env vars, set in a profile or the shell):

| Variable | Default | Meaning |
|---|---|---|
| `SCENARIO_APP_RATE` | `50` | App requests per second |
| `SCENARIO_WRITE_RATIO` | `0.2` | Share of app requests that are `POST /items` |
| `SCENARIO_STEPS` | `0,10,50,100,200,500` | Job rates (jobs/s), one step each |
| `SCENARIO_WARMUP` | `2m` | Warm-up before the first step, excluded from analysis |
| `SCENARIO_RAMP` | `15s` | Ramp between steps |
| `SCENARIO_HOLD` | `3m` | Hold at each step |
| `SCENARIO_JOBS_PER_REQUEST` | `1` | Jobs enqueued per `POST /enqueue` request |
| `SCENARIO_ITEM_COUNT` | `100000` | Rows seeded into `Item`, and the id range for reads |
| `SCENARIO_MAX_VUS` | `500` | Cap on k6 virtual users per scenario |

`SCENARIO_JOBS_PER_REQUEST` matters. With 1 job per request, a 200 jobs/s step also means 200 extra HTTP requests/s to the web server, which can saturate it before the queue does. Raising it keeps the web load low so the measurement isolates the queue. The per-step table marks a step `UNDER RATE` when k6 delivered less than 95% of the target enqueue rate. Treat those steps as saturation, not as data for that rate.

## The targets

Both Django targets run the same code from `targets/django-common`. The queue backend is the only intended difference.

**App.** Two models: `Item` (seeded with 100k rows) and `JobRun` (one row per job with `enqueued_at`, `started_at`, `finished_at`). Endpoints:

- `GET /items/<id>`: indexed read
- `POST /items`: insert
- `POST /enqueue?n=<k>`: inserts an `Item`, creates `k` `JobRun` rows and enqueues `k` jobs, all in one transaction
- `GET /healthz`: 200 once the database and at least one worker are ready

**Job.** Updates the referenced `Item` and writes its timings to `JobRun`, in one transaction. Same body in both targets, so the job's own database work is identical.

**Procrastinate.** Uses the Django integration (`procrastinate.contrib.django`). Worker: `manage.py procrastinate worker --concurrency=$WORKER_CONCURRENCY`.

**Celery.** Redis broker, no result backend (`task_ignore_result=True`, `result_backend=None`), so Celery's queue bookkeeping never touches Postgres. Jobs are enqueued with `delay_on_commit`. Pool is `prefork` by default; set `CELERY_POOL=threads` to switch.

### What was checked in the library source

Against Procrastinate 3.10.0 and Celery 5.6.3:

- **Procrastinate defers inside the request transaction.** `DjangoConnector.execute_query_one` runs on `django.db.connections[alias].cursor()`, so a sync `defer()` uses the request's connection and commits or rolls back with it.
- **Procrastinate keeps worker DB connections.** Its Django task middleware calls `close_old_connections()` around each task, which respects `CONN_MAX_AGE`.
- **Celery's `delay_on_commit`** is `transaction.on_commit(functools.partial(self.delay, ...))`.
- **Celery closes the DB connection after every task by default.** Its Django fixup calls `conn.close()` after each task, ignoring `CONN_MAX_AGE`, unless `CELERY_DB_REUSE_MAX` is set. In a quick test that meant one new Postgres connection per job and about 4× lower worker throughput. The default profile sets `CELERY_DB_REUSE_MAX=1000000` so both backends handle connections the same way. Set it to `0` for Celery's stock behaviour.

### Fairness

Identical across the two Django targets: app code and image, Gunicorn config (`gthread`, `WEB_WORKERS` × `WEB_THREADS`, `--keep-alive=75`), worker concurrency, resource limits, Postgres image and config, Django `CONN_MAX_AGE`.

Known differences:

- The Celery target runs an extra Redis container with its own limits (`BROKER_CPUS`, `BROKER_MEM`), outside the budget of the other services.
- `CELERY_DB_REUSE_MAX` is set (see above).
- Django's `CONN_HEALTH_CHECKS` is off. Procrastinate's per-task `close_old_connections()` resets the health check, so with it on, every Procrastinate job would send an extra `SELECT 1` that Celery jobs don't.
- Redis runs with its stock config, including RDB snapshots (`save` points) and no `maxmemory`. A backlog larger than the container's memory limit would get Redis killed.
- Procrastinate keeps finished jobs in `procrastinate_jobs` (its default, `delete_jobs=never`) and writes `procrastinate_events` rows. That is part of what's being measured.

### Postgres

The official `postgres` image with no configuration changes. Procrastinate needs none. Each run's `meta.json` lists every setting not at its built-in default. Today that is only what `initdb` writes into `postgresql.conf` plus the image's `listen_addresses`.

## Profiles and resource limits

A profile is an env file in `profiles/`. `default.env` is always loaded; a named profile is layered on top, and shell variables override both.

The default profile approximates a 2 vCPU / 4 GB VPS across the database, web and worker containers:

| Service | CPUs | Memory |
|---|---|---|
| Postgres | 0.8 | 1.5 GB |
| Web (Gunicorn, 2 workers × 4 threads) | 0.7 | 1 GB |
| Worker (concurrency 4) | 0.5 | 1 GB |
| Redis (Celery target only) | 0.25 | 256 MB |

`smoke.env` shortens the run (30s holds, steps up to 200) for checking the setup. Smoke results are gitignored.

## What each run records

| File | Contents |
|---|---|
| `meta.json` | Git commit, timestamp, scenario, target, profile, every config value and which were overridden, container images, digests and limits, versions (k6, Postgres, Python and packages, Redis), Postgres non-default settings, host CPU, cores, RAM, OS |
| `k6.json.gz` | Raw k6 metrics. Not committed; published runs attach it to a GitHub Release |
| `summary.json` | k6 end-of-test summary, including per-step, per-endpoint submetrics |
| `steps.json` | Per step and endpoint: request rate, p50/p95/p99/max latency, failure rate |
| `schedule.json` | Run start time and the step timeline |
| `jobs.csv.gz` | Every job's timings |
| `jobs_summary.json` | Per step: jobs enqueued, queue latency (`started_at - enqueued_at`) p50/p95/p99, run time |
| `backlog.csv` | Jobs enqueued but not yet started, per second |
| `pg.jsonl` | Every 10s: connections by state and wait type, transaction and tuple counters, per-table live/dead tuples and autovacuum counts, lock counts |
| `containers.csv` | Every 10s: CPU and memory per container |
| `compose.log`, `k6.log` | Logs |

### How timing is measured

- Job timestamps come from `time.time()` in the web and worker containers, which share the host clock. `started_at` is taken when the job starts and written together with `finished_at` at the end, so timing costs one write per job.
- That bookkeeping (one `JobRun` insert per job at enqueue, one update when it runs) adds Postgres load. It is the same for both backends.
- Jobs are matched to steps by `enqueued_at` against the run start recorded in k6's `setup()`.
- After k6 finishes, `collect_jobs.py` waits up to `DRAIN_TIMEOUT` (300s) for the backlog to clear. Jobs still unfinished are reported, not dropped.

## Results

No published results yet. Reference runs will be listed here with their host, profile and a link to the run folder.

## Adding targets and scenarios

See [CONTRIBUTING.md](CONTRIBUTING.md). A target is a `compose.yml`, a `target.env` and optional hooks. Nothing in `scripts/` or `scenarios/lib/` knows about Django.

## Not built yet

- Charts (app p95 vs job rate, queue latency vs job rate, dead tuples over time)
- A transactional-enqueue correctness check (rollback and commit-delay cases)
- Optional: k6 Prometheus remote-write output, so runs appear in an existing Grafana

## License

[MIT](LICENSE)
