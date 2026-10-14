import json
import time
import uuid

from django.conf import settings
from django.db import connection, transaction
from django.http import HttpResponseNotAllowed, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from benchapp import backend
from benchapp.models import Item, JobRun

PAYLOAD = "x" * 200
MAX_JOBS_PER_REQUEST = 1000


def healthz(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    if not backend.workers_ready():
        return JsonResponse({"ok": False, "reason": "no workers"}, status=503)
    return JsonResponse({"ok": True, "backend": settings.BENCH_BACKEND})


def get_item(request, item_id):
    item = Item.objects.filter(pk=item_id).values("id", "name", "counter", "updated_at").first()
    if item is None:
        return JsonResponse({"error": "not found"}, status=404)
    return JsonResponse(item)


@csrf_exempt
def create_item(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    data = json.loads(request.body or b"{}")
    item = Item.objects.create(name=str(data.get("name", "item"))[:100], payload=PAYLOAD)
    return JsonResponse({"id": item.pk}, status=201)


@csrf_exempt
def enqueue(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    n = int(request.GET.get("n", 1))
    if not 1 <= n <= MAX_JOBS_PER_REQUEST:
        return JsonResponse({"error": f"n must be 1..{MAX_JOBS_PER_REQUEST}"}, status=400)
    with transaction.atomic():
        item = Item.objects.create(name="enqueue", payload=PAYLOAD)
        enqueued_at = time.time()
        runs = JobRun.objects.bulk_create(
            JobRun(
                job_id=uuid.uuid4(),
                backend=settings.BENCH_BACKEND,
                item_id=item.pk,
                enqueued_at=enqueued_at,
            )
            for _ in range(n)
        )
        backend.enqueue([(str(run.job_id), item.pk) for run in runs])
    return JsonResponse({"item_id": item.pk, "jobs": n}, status=202)
