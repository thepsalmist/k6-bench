from procrastinate.contrib.django import app

from benchapp.jobs import run_job


@app.task(name="bench.run_job")
def run_job_task(job_id: str, item_id: int) -> None:
    run_job(job_id, item_id)
