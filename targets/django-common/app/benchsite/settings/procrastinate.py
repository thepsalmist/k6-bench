from .base import *  # noqa: F403
from .base import INSTALLED_APPS

INSTALLED_APPS = ["procrastinate.contrib.django", *INSTALLED_APPS, "bench_procrastinate"]

BENCH_BACKEND = "procrastinate"
BENCH_ENQUEUE = "bench_procrastinate.backend.enqueue"
BENCH_WORKERS_READY = "bench_procrastinate.backend.workers_ready"
