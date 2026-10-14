import os

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "k6-bench-insecure-not-a-secret")
DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = ["benchapp"]
MIDDLEWARE = []
ROOT_URLCONF = "benchsite.urls"
WSGI_APPLICATION = "benchsite.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "NAME": os.environ.get("DB_NAME", "bench"),
        "USER": os.environ.get("DB_USER", "bench"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "bench"),
        "CONN_MAX_AGE": 600,
        # Off: Procrastinate resets the health check per task and Celery doesn't, so it'd add a query to one side.
        "CONN_HEALTH_CHECKS": False,
    }
}

USE_TZ = True
TIME_ZONE = "UTC"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
}

# Set by the backend settings module.
BENCH_BACKEND = None
BENCH_ENQUEUE = None
BENCH_WORKERS_READY = None
