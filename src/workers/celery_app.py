from __future__ import annotations

import os

from celery import Celery

from src.core.config import get_settings

settings = get_settings()
broker_url = os.environ.get("CELERY_BROKER_URL", settings.redis_url)

app = Celery("fraud_workers")
app.conf.update(
    broker_url=broker_url,
    result_backend=broker_url,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

app.conf.task_routes = {
    "src.workers.tasks.backfill_offline_features": {"queue": "features"},
    "src.workers.tasks.generate_label_snapshots": {"queue": "labels"},
    "src.workers.tasks.compute_drift_metrics": {"queue": "governance"},
    "src.workers.tasks.run_shadow_experiment": {"queue": "experiments"},
}

app.autodiscover_tasks(["src.workers"])

# Load beat schedule (must happen after app is configured)
import src.workers.scheduler  # noqa: F401, E402
