from django.conf import settings
from django.utils.module_loading import import_string

enqueue = import_string(settings.BENCH_ENQUEUE)
workers_ready = import_string(settings.BENCH_WORKERS_READY)
