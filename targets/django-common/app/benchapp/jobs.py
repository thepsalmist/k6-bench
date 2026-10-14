import time

from django.db import transaction
from django.db.models import F
from django.db.models.functions import Now

from benchapp.models import Item, JobRun


def run_job(job_id: str, item_id: int) -> None:
    """The job body shared by every backend: one small write to the referenced item."""
    started_at = time.time()
    with transaction.atomic():
        Item.objects.filter(pk=item_id).update(counter=F("counter") + 1, updated_at=Now())
        # started_at is taken above but written here, so timing costs one write per job, not two.
        JobRun.objects.filter(job_id=job_id).update(started_at=started_at, finished_at=time.time(), status="done")
