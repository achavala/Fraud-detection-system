from __future__ import annotations

from datetime import date, timedelta

from celery.schedules import crontab

from src.workers.celery_app import app
from src.core.config import get_settings

settings = get_settings()

_YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
_TODAY = date.today().isoformat()

app.conf.beat_schedule = {
    "daily-offline-feature-backfill": {
        "task": "src.workers.tasks.backfill_offline_features",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "features"},
        "kwargs": {
            "auth_event_ids": [],
            "feature_version": settings.feature_version,
            "label_snapshot_date": _YESTERDAY,
        },
    },
    "daily-label-snapshot-generation": {
        "task": "src.workers.tasks.generate_label_snapshots",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "labels"},
        "kwargs": {
            "snapshot_date": _YESTERDAY,
            "maturity_days": 30,
        },
    },
    "daily-drift-monitoring": {
        "task": "src.workers.tasks.compute_drift_metrics",
        "schedule": crontab(hour=4, minute=0),
        "options": {"queue": "governance"},
        "kwargs": {
            "model_version": settings.champion_model_version,
            "metric_date": _TODAY,
        },
    },
    "hourly-shadow-experiment-check": {
        "task": "src.workers.tasks.run_shadow_experiment",
        "schedule": crontab(minute=0),
        "options": {"queue": "experiments"},
        "kwargs": {
            "challenger_version": (
                settings.shadow_model_versions.split(",")[0].strip()
                or "lgb-v5.0.0-rc1"
            ),
            "champion_version": settings.champion_model_version,
            "auth_event_ids": [],
        },
    },
}
