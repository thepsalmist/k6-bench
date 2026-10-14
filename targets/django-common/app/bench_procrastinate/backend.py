from datetime import timedelta

from django.utils import timezone
from procrastinate.contrib.django.models import ProcrastinateWorker

from bench_procrastinate.tasks import run_job_task


def enqueue(jobs: list[tuple[str, int]]) -> None:
    # Sync defer goes through Django's connection, so it is part of the caller's transaction.
    for job_id, item_id in jobs:
        run_job_task.defer(job_id=job_id, item_id=item_id)


def workers_ready() -> bool:
    cutoff = timezone.now() - timedelta(seconds=30)
    return ProcrastinateWorker.objects.filter(last_heartbeat__gte=cutoff).exists()
