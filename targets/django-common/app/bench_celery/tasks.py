from benchapp.jobs import run_job
from benchsite.celery_app import app


@app.task(name="bench.run_job")
def run_job_task(job_id: str, item_id: int) -> None:
    run_job(job_id, item_id)
