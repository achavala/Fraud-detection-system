from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import numpy as np
from src.workers.celery_app import app
from sqlalchemy import create_engine, select, and_
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings
from src.core.logging import get_logger
from src.models.features import FactTransactionFeaturesOnline, FactTransactionFeaturesOffline
from src.models.labels import FactFraudLabel, FactLabelSnapshot
from src.models.governance import FactFeatureDriftMetric, FactThresholdExperiment
from src.models.transactions import FactAuthorizationEvent
from src.services.scoring.ml_model import FEATURE_COLUMNS, _load_model_artifact

logger = get_logger(__name__)

# Synchronous engine for Celery workers (psycopg2)
_engine = None
_SessionLocal = None


def _get_sync_session() -> Session:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url_sync,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _SessionLocal()


def _to_scoring_vector_from_json(feature_json: dict | None) -> dict[str, Any]:
    """Build scoring vector from feature_json (online) or feature dict."""
    if not feature_json:
        return {k: 0 for k in FEATURE_COLUMNS}

    def coerce(v: Any) -> float:
        if v is None:
            return 0.0
        if isinstance(v, bool):
            return 1.0 if v else 0.0
        if isinstance(v, (int, float, Decimal)):
            return float(v)
        return 0.0

    return {k: coerce(feature_json.get(k, 0)) for k in FEATURE_COLUMNS}


def _score_with_model(features: dict[str, Any], model_version: str) -> float:
    """Score features with a model version; returns calibrated probability."""
    artifact = _load_model_artifact(model_version)
    settings = get_settings()

    def coerce_numeric(v: Any) -> float:
        if v is None:
            return 0.0
        if isinstance(v, bool):
            return 1.0 if v else 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    if artifact:
        cols = artifact.get("feature_columns", FEATURE_COLUMNS)
        x = np.array([[coerce_numeric(features.get(c, 0)) for c in cols]])
        model = artifact["model"]
        proba = model.predict_proba(x)[0]
        return float(proba[1])

    # Heuristic fallback
    import hashlib
    score = 0.0
    weights = {
        "card_txn_count_10m": (0.12, 5),
        "device_account_count_30d": (0.15, 3),
        "ip_card_count_7d": (0.10, 5),
        "customer_txn_count_1h": (0.08, 10),
        "proxy_vpn_tor_flag": (0.12, 1),
        "device_risk_score": (0.10, 1),
        "amount_vs_customer_p95_ratio": (0.08, 3),
        "seconds_since_last_txn": (-0.05, 60),
        "graph_cluster_risk_score": (0.10, 1),
        "merchant_chargeback_rate_30d": (0.10, 0.05),
    }
    for feat, (weight, threshold) in weights.items():
        val = features.get(feat, 0)
        if val is None:
            continue
        val = 1 if val is True else (0 if val is False else float(val))
        if weight < 0:
            contribution = weight * max(0, 1 - val / threshold) if threshold else 0
        else:
            contribution = weight * min(val / threshold, 1.0) if threshold else 0
        score += contribution
    noise = int(hashlib.md5(model_version.encode()).hexdigest()[:4], 16) / 65535 * 0.02
    raw = max(0.01, min(0.99, score + noise))
    return 1.0 / (1.0 + math.exp(-5 * (raw - 0.5)))


def _compute_psi(prod_vals: list[float], train_vals: list[float], n_bins: int = 10) -> float:
    """Population Stability Index between production and training distributions."""
    all_vals = train_vals + prod_vals
    if not all_vals:
        return 0.0
    lo, hi = min(all_vals), max(all_vals)
    if hi <= lo:
        return 0.0
    bin_edges = np.linspace(lo, hi, n_bins + 1)
    train_hist, _ = np.histogram(train_vals, bins=bin_edges)
    prod_hist, _ = np.histogram(prod_vals, bins=bin_edges)
    train_pct = (train_hist + 1e-10) / (train_hist.sum() + 1e-10)
    prod_pct = (prod_hist + 1e-10) / (prod_hist.sum() + 1e-10)
    psi = np.sum((prod_pct - train_pct) * np.log(prod_pct / train_pct))
    return float(max(0.0, psi))


@app.task(bind=True, name="src.workers.tasks.backfill_offline_features")
def backfill_offline_features(
    self,
    auth_event_ids: list[int],
    feature_version: str,
    label_snapshot_date: date | None,
) -> dict[str, Any]:
    """
    Copy online features to offline feature store for each auth_event_id.
    Uses synchronous SQLAlchemy (psycopg2) since Celery workers are sync.
    """
    if isinstance(label_snapshot_date, str):
        label_snapshot_date = date.fromisoformat(label_snapshot_date) if label_snapshot_date else None
    session = _get_sync_session()
    try:
        if not auth_event_ids and label_snapshot_date:
            # Auto-discover: auth events with online features but no offline for this snapshot
            cutoff = datetime.combine(
                label_snapshot_date - timedelta(days=1),
                datetime.min.time(),
                tzinfo=timezone.utc,
            )
            subq = (
                select(FactTransactionFeaturesOnline.auth_event_id)
                .where(FactTransactionFeaturesOnline.feature_timestamp < cutoff)
            )
            candidates = [r[0] for r in session.execute(subq).fetchall()][:5000]
            auth_event_ids = []
            for aid in candidates:
                ex = session.execute(
                    select(FactTransactionFeaturesOffline.offline_feature_row_id).where(
                        and_(
                            FactTransactionFeaturesOffline.auth_event_id == aid,
                            FactTransactionFeaturesOffline.label_snapshot_date == label_snapshot_date,
                        )
                    )
                ).scalar_one_or_none()
                if ex is None:
                    auth_event_ids.append(aid)
                if len(auth_event_ids) >= 1000:
                    break

        created = 0
        for auth_event_id in auth_event_ids:
            result = session.execute(
                select(FactTransactionFeaturesOnline).where(
                    FactTransactionFeaturesOnline.auth_event_id == auth_event_id
                )
            )
            online = result.scalar_one_or_none()
            if not online:
                logger.warning("no_online_features", auth_event_id=auth_event_id)
                continue

            feature_json = online.feature_json or {}
            offline = FactTransactionFeaturesOffline(
                auth_event_id=auth_event_id,
                as_of_time=online.feature_timestamp,
                feature_version=feature_version,
                label_snapshot_date=label_snapshot_date,
                feature_json=feature_json,
            )
            session.add(offline)
            created += 1

        session.commit()
        logger.info(
            "backfill_offline_features_done",
            auth_event_count=len(auth_event_ids),
            created=created,
        )
        return {"created": created, "total": len(auth_event_ids)}
    except Exception as e:
        session.rollback()
        logger.exception("backfill_offline_features_failed", error=str(e))
        raise
    finally:
        session.close()


@app.task(bind=True, name="src.workers.tasks.generate_label_snapshots")
def generate_label_snapshots(
    self,
    snapshot_date: date,
    maturity_days: int,
) -> dict[str, Any]:
    """
    For auth_events older than maturity_days, look up latest fraud_label
    and create fact_label_snapshot records.
    """
    if isinstance(snapshot_date, str):
        snapshot_date = date.fromisoformat(snapshot_date)

    session = _get_sync_session()
    try:
        cutoff = snapshot_date - timedelta(days=maturity_days)
        # Auth events with event_time before cutoff
        subq = (
            select(FactAuthorizationEvent.auth_event_id)
            .where(FactAuthorizationEvent.event_time < datetime.combine(cutoff, datetime.min.time(), tzinfo=timezone.utc))
        )
        auth_ids = [r[0] for r in session.execute(subq).fetchall()]

        # Get latest fraud_label per auth_event_id (by label_received_at desc)
        created = 0
        for auth_event_id in auth_ids:
            result = session.execute(
                select(FactFraudLabel)
                .where(FactFraudLabel.auth_event_id == auth_event_id)
                .order_by(FactFraudLabel.label_received_at.desc())
                .limit(1)
            )
            label = result.scalar_one_or_none()
            if not label:
                continue

            # Check if snapshot already exists for this auth_event + snapshot_date
            existing = session.execute(
                select(FactLabelSnapshot).where(
                    and_(
                        FactLabelSnapshot.auth_event_id == auth_event_id,
                        FactLabelSnapshot.snapshot_date == snapshot_date,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue

            snap = FactLabelSnapshot(
                auth_event_id=auth_event_id,
                snapshot_date=snapshot_date,
                label_status=label.label_source,
                is_fraud_snapshot=label.is_fraud,
                maturity_days=maturity_days,
            )
            session.add(snap)
            created += 1

        session.commit()
        logger.info(
            "generate_label_snapshots_done",
            snapshot_date=snapshot_date.isoformat(),
            maturity_days=maturity_days,
            created=created,
        )
        return {"created": created, "auth_events_scanned": len(auth_ids)}
    except Exception as e:
        session.rollback()
        logger.exception("generate_label_snapshots_failed", error=str(e))
        raise
    finally:
        session.close()


@app.task(bind=True, name="src.workers.tasks.compute_drift_metrics")
def compute_drift_metrics(
    self,
    model_version: str,
    metric_date: date,
) -> dict[str, Any]:
    """
    For each feature in FEATURE_COLUMNS, compute PSI of recent production
    vs training distribution; write to fact_feature_drift_metric.
    """
    if isinstance(metric_date, str):
        metric_date = date.fromisoformat(metric_date)

    session = _get_sync_session()
    try:
        settings = get_settings()

        # Training distribution: offline features (historical)
        train_start = metric_date - timedelta(days=120)
        train_end = metric_date - timedelta(days=30)
        train_start_dt = datetime.combine(train_start, datetime.min.time(), tzinfo=timezone.utc)
        train_end_dt = datetime.combine(train_end, datetime.min.time(), tzinfo=timezone.utc)

        # Production: recent online features (last 7 days before metric_date)
        prod_start = metric_date - timedelta(days=7)
        prod_end = metric_date
        prod_start_dt = datetime.combine(prod_start, datetime.min.time(), tzinfo=timezone.utc)
        prod_end_dt = datetime.combine(prod_end, datetime.min.time(), tzinfo=timezone.utc)

        train_q = session.execute(
            select(FactTransactionFeaturesOffline.feature_json).where(
                and_(
                    FactTransactionFeaturesOffline.as_of_time >= train_start_dt,
                    FactTransactionFeaturesOffline.as_of_time < train_end_dt,
                )
            )
        )
        train_rows = train_q.fetchall()

        prod_q = session.execute(
            select(FactTransactionFeaturesOnline.feature_json).where(
                and_(
                    FactTransactionFeaturesOnline.feature_timestamp >= prod_start_dt,
                    FactTransactionFeaturesOnline.feature_timestamp < prod_end_dt,
                )
            )
        )
        prod_rows = prod_q.fetchall()

        def extract_vals(rows: list, col: str) -> list[float]:
            vals = []
            for (fj,) in rows:
                if not fj:
                    continue
                v = fj.get(col)
                if v is None:
                    continue
                if isinstance(v, bool):
                    vals.append(1.0 if v else 0.0)
                elif isinstance(v, (int, float, Decimal)):
                    vals.append(float(v))
                else:
                    vals.append(0.0)
            return vals

        psi_threshold = 0.25  # Common drift alert threshold
        created = 0
        for col in FEATURE_COLUMNS:
            train_vals = extract_vals(train_rows, col)
            prod_vals = extract_vals(prod_rows, col)
            psi = _compute_psi(prod_vals, train_vals) if train_vals and prod_vals else 0.0

            train_mean = float(np.mean(train_vals)) if train_vals else 0.0
            prod_mean = float(np.mean(prod_vals)) if prod_vals else 0.0
            null_rate = 1.0 - (len(prod_vals) / max(1, len(prod_rows))) if prod_rows else 0.0

            rec = FactFeatureDriftMetric(
                model_version=model_version,
                feature_name=col,
                metric_date=metric_date,
                psi=psi,
                js_divergence=None,
                null_rate=null_rate,
                train_mean=train_mean,
                prod_mean=prod_mean,
                alert_flag=psi >= psi_threshold,
            )
            session.add(rec)
            created += 1

        session.commit()
        logger.info(
            "compute_drift_metrics_done",
            model_version=model_version,
            metric_date=metric_date.isoformat(),
            features=created,
        )
        return {"created": created}
    except Exception as e:
        session.rollback()
        logger.exception("compute_drift_metrics_failed", error=str(e))
        raise
    finally:
        session.close()


@app.task(bind=True, name="src.workers.tasks.run_shadow_experiment")
def run_shadow_experiment(
    self,
    challenger_version: str,
    champion_version: str,
    auth_event_ids: list[int],
) -> dict[str, Any]:
    """
    Score each auth_event with both champion and challenger; compare metrics.
    Writes result to fact_threshold_experiment.
    """
    session = _get_sync_session()
    try:
        if not auth_event_ids:
            # Auto-discover: recent auth events with online features (last 24h)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            rows = session.execute(
                select(FactTransactionFeaturesOnline.auth_event_id)
                .where(FactTransactionFeaturesOnline.feature_timestamp >= cutoff)
                .limit(500)
            ).fetchall()
            auth_event_ids = [r[0] for r in rows]

        now = datetime.now(timezone.utc)
        champion_scores: list[float] = []
        challenger_scores: list[float] = []
        agreements = 0
        threshold = get_settings().score_threshold_review

        for auth_event_id in auth_event_ids:
            result = session.execute(
                select(FactTransactionFeaturesOnline.feature_json)
                .where(FactTransactionFeaturesOnline.auth_event_id == auth_event_id)
            )
            row = result.fetchone()
            if not row:
                continue
            features = _to_scoring_vector_from_json(row[0])

            champ_score = _score_with_model(features, champion_version)
            chall_score = _score_with_model(features, challenger_version)
            champion_scores.append(champ_score)
            challenger_scores.append(chall_score)

            champ_above = champ_score >= threshold
            chall_above = chall_score >= threshold
            if champ_above == chall_above:
                agreements += 1

        n = len(champion_scores)
        outcome = {
            "champion_avg_score": float(np.mean(champion_scores)) if champion_scores else 0.0,
            "challenger_avg_score": float(np.mean(challenger_scores)) if challenger_scores else 0.0,
            "champion_decline_pct": (
                sum(1 for s in champion_scores if s >= threshold) / n * 100 if n else 0
            ),
            "challenger_decline_pct": (
                sum(1 for s in challenger_scores if s >= threshold) / n * 100 if n else 0
            ),
            "agreement_pct": agreements / n * 100 if n else 100.0,
            "n_events": n,
        }

        exp = FactThresholdExperiment(
            challenger_model_version=challenger_version,
            champion_model_version=champion_version,
            threshold_set_version=None,
            mode="shadow",
            start_time=now,
            end_time=now,
            traffic_pct=100.0,
            outcome_summary_json=outcome,
        )
        session.add(exp)
        session.commit()

        logger.info(
            "run_shadow_experiment_done",
            champion=champion_version,
            challenger=challenger_version,
            n_events=n,
        )
        return {"experiment_id": exp.experiment_id, "outcome": outcome}
    except Exception as e:
        session.rollback()
        logger.exception("run_shadow_experiment_failed", error=str(e))
        raise
    finally:
        session.close()
