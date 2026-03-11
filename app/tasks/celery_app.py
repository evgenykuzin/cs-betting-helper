"""
Celery application.
"""

from celery import Celery
from celery.schedules import crontab
from app.core.config import get_settings

settings = get_settings()

celery = Celery(
    "cs_betting",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_concurrency=4,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    include=["app.tasks.polling"],
)

# ── Beat schedule (periodic tasks) ──
celery.conf.beat_schedule = {
    "poll-odds-every-5min": {
        "task": "app.tasks.polling.poll_all_matches",
        "schedule": settings.poll_interval_seconds,
    },
    "cleanup-old-snapshots-daily": {
        "task": "app.tasks.polling.cleanup_old_data",
        "schedule": crontab(hour=3, minute=0),
    },
    "cleanup-old-logs-daily": {
        "task": "app.tasks.polling.cleanup_old_logs",
        "schedule": crontab(hour=4, minute=0),
    },
}

# Import tasks AFTER celery config to avoid circular imports
from app.tasks import polling  # noqa: E402, F401
