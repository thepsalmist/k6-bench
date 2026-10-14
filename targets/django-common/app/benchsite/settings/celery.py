import os

from .base import *  # noqa: F403
from .base import INSTALLED_APPS

INSTALLED_APPS = [*INSTALLED_APPS, "bench_celery"]

BENCH_BACKEND = "celery"
BENCH_ENQUEUE = "bench_celery.backend.enqueue"
BENCH_WORKERS_READY = "bench_celery.backend.workers_ready"

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# No result backend: Celery must not touch Postgres for queue bookkeeping.
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
# Celery's Django fixup closes the DB connection after every task unless this is set,
# ignoring CONN_MAX_AGE. Procrastinate keeps it, so default to reuse; 0 restores Celery's default.
CELERY_DB_REUSE_MAX = int(os.environ.get("CELERY_DB_REUSE_MAX", "1000000")) or None
