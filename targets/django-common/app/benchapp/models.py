from django.db import models


class Item(models.Model):
    name = models.CharField(max_length=100)
    payload = models.TextField()
    counter = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bench_item"


class JobRun(models.Model):
    """Timings are epoch seconds from time.time() in the web and worker containers (same host clock)."""

    job_id = models.UUIDField(primary_key=True)
    backend = models.CharField(max_length=32)
    item_id = models.BigIntegerField()
    status = models.CharField(max_length=16, default="queued")
    enqueued_at = models.FloatField()
    started_at = models.FloatField(null=True)
    finished_at = models.FloatField(null=True)

    class Meta:
        db_table = "bench_jobrun"
