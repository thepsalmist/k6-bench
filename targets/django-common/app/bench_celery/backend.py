from bench_celery.tasks import run_job_task
from benchsite.celery_app import app


def enqueue(jobs: list[tuple[str, int]]) -> None:
    for job_id, item_id in jobs:
        run_job_task.delay_on_commit(job_id, item_id)


def workers_ready() -> bool:
    return bool(app.control.ping(timeout=1.0))
