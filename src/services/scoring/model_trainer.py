"""
Phase 1 + Phase 3: Model training pipeline.
Trains XGBoost and LightGBM fraud classifiers from offline features + label snapshots.
Produces serialized model artifacts for FraudModelScorer to load.
"""
from __future__ import annotations

import os
import json
import pickle
import math
from datetime import datetime, timezone
from typing import Optional, Any
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import roc_auc_score, average_precision_score, classification_report

from src.core.logging import get_logger

logger = get_logger(__name__)

MODEL_DIR = Path(__file__).parent.parent.parent.parent / "models_artifact"

FEATURE_COLUMNS = [
    "customer_txn_count_1h",
    "customer_txn_count_24h",
    "customer_spend_24h",
    "card_txn_count_10m",
    "merchant_txn_count_10m",
    "merchant_chargeback_rate_30d",
    "device_txn_count_1d",
    "device_account_count_30d",
    "ip_account_count_7d",
    "ip_card_count_7d",
    "geo_distance_from_home_km",
    "geo_distance_from_last_txn_km",
    "seconds_since_last_txn",
    "amount_vs_customer_p95_ratio",
    "amount_vs_merchant_p95_ratio",
    "proxy_vpn_tor_flag",
    "device_risk_score",
    "behavioral_risk_score",
    "graph_cluster_risk_score",
]


class FraudModelTrainer:
    """
    Trains fraud detection models from the offline feature store.
    Reads fact_transaction_features_offline joined with fact_label_snapshot
    to produce leakage-free training datasets.
    """

    def __init__(self, model_dir: Optional[Path] = None):
        self.model_dir = model_dir or MODEL_DIR
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def generate_synthetic_training_data(
        self, n_samples: int = 50000, fraud_rate: float = 0.03, seed: int = 42
    ) -> pd.DataFrame:
        """Generate realistic synthetic fraud data for training when DB is unavailable."""
        np.random.seed(seed)
        n_fraud = int(n_samples * fraud_rate)
        n_legit = n_samples - n_fraud

        def _gen(n, is_fraud):
            return pd.DataFrame({
                "customer_txn_count_1h": np.random.poisson(8 if is_fraud else 2, n),
                "customer_txn_count_24h": np.random.poisson(15 if is_fraud else 5, n),
                "customer_spend_24h": np.random.lognormal(7 if is_fraud else 5, 1, n),
                "card_txn_count_10m": np.random.poisson(4 if is_fraud else 1, n),
                "merchant_txn_count_10m": np.random.poisson(6 if is_fraud else 2, n),
                "merchant_chargeback_rate_30d": np.random.beta(3 if is_fraud else 1, 20, n),
                "device_txn_count_1d": np.random.poisson(10 if is_fraud else 3, n),
                "device_account_count_30d": np.random.poisson(3 if is_fraud else 1, n),
                "ip_account_count_7d": np.random.poisson(4 if is_fraud else 1, n),
                "ip_card_count_7d": np.random.poisson(5 if is_fraud else 1, n),
                "geo_distance_from_home_km": np.random.exponential(2000 if is_fraud else 50, n),
                "geo_distance_from_last_txn_km": np.random.exponential(1000 if is_fraud else 20, n),
                "seconds_since_last_txn": np.random.exponential(30 if is_fraud else 3600, n).astype(int),
                "amount_vs_customer_p95_ratio": np.random.lognormal(1.5 if is_fraud else 0, 0.5, n),
                "amount_vs_merchant_p95_ratio": np.random.lognormal(1.0 if is_fraud else 0, 0.5, n),
                "proxy_vpn_tor_flag": np.random.binomial(1, 0.4 if is_fraud else 0.02, n),
                "device_risk_score": np.random.beta(5 if is_fraud else 1, 2 if is_fraud else 10, n),
                "behavioral_risk_score": np.random.beta(4 if is_fraud else 1, 2 if is_fraud else 10, n),
                "graph_cluster_risk_score": np.random.beta(3 if is_fraud else 1, 3 if is_fraud else 15, n),
                "is_fraud": np.ones(n, dtype=int) if is_fraud else np.zeros(n, dtype=int),
            })

        fraud_df = _gen(n_fraud, True)
        legit_df = _gen(n_legit, False)
        df = pd.concat([fraud_df, legit_df], ignore_index=True).sample(frac=1, random_state=seed)
        return df

    def train_xgboost(
        self,
        df: pd.DataFrame,
        model_version: str = "xgb-v4.2.0",
        test_size: float = 0.2,
    ) -> dict:
        import xgboost as xgb

        X = df[FEATURE_COLUMNS].fillna(0)
        y = df["is_fraud"]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, stratify=y, random_state=42
        )

        scale_pos_weight = len(y_train[y_train == 0]) / max(len(y_train[y_train == 1]), 1)

        model = xgb.XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=scale_pos_weight,
            eval_metric="aucpr",
            use_label_encoder=False,
            random_state=42,
        )
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

        calibrated = CalibratedClassifierCV(model, cv=3, method="isotonic")
        calibrated.fit(X_train, y_train)

        y_prob = calibrated.predict_proba(X_test)[:, 1]
        metrics = self._compute_metrics(y_test, y_prob)

        artifact_path = self.model_dir / f"{model_version}.pkl"
        with open(artifact_path, "wb") as f:
            pickle.dump({
                "model": calibrated,
                "raw_model": model,
                "feature_columns": FEATURE_COLUMNS,
                "model_version": model_version,
                "training_metrics": metrics,
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "feature_importances": dict(zip(FEATURE_COLUMNS, model.feature_importances_.tolist())),
            }, f)

        logger.info(
            "xgboost_trained",
            model_version=model_version,
            auc_roc=metrics["auc_roc"],
            auc_pr=metrics["auc_pr"],
            path=str(artifact_path),
        )
        return {"model_version": model_version, "path": str(artifact_path), "metrics": metrics}

    def train_lightgbm(
        self,
        df: pd.DataFrame,
        model_version: str = "lgb-v5.0.0-rc1",
        test_size: float = 0.2,
    ) -> dict:
        import lightgbm as lgb

        X = df[FEATURE_COLUMNS].fillna(0)
        y = df["is_fraud"]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, stratify=y, random_state=42
        )

        model = lgb.LGBMClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            is_unbalance=True,
            random_state=42,
            verbose=-1,
        )
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)])

        calibrated = CalibratedClassifierCV(model, cv=3, method="isotonic")
        calibrated.fit(X_train, y_train)

        y_prob = calibrated.predict_proba(X_test)[:, 1]
        metrics = self._compute_metrics(y_test, y_prob)

        artifact_path = self.model_dir / f"{model_version}.pkl"
        with open(artifact_path, "wb") as f:
            pickle.dump({
                "model": calibrated,
                "raw_model": model,
                "feature_columns": FEATURE_COLUMNS,
                "model_version": model_version,
                "training_metrics": metrics,
                "trained_at": datetime.now(timezone.utc).isoformat(),
                "feature_importances": dict(zip(FEATURE_COLUMNS, model.feature_importances_.tolist())),
            }, f)

        logger.info(
            "lightgbm_trained",
            model_version=model_version,
            auc_roc=metrics["auc_roc"],
            auc_pr=metrics["auc_pr"],
            path=str(artifact_path),
        )
        return {"model_version": model_version, "path": str(artifact_path), "metrics": metrics}

    def _compute_metrics(self, y_true, y_prob, threshold: float = 0.55) -> dict:
        y_pred = (np.array(y_prob) >= threshold).astype(int)
        y_true_arr = np.array(y_true)
        tp = int(np.sum((y_pred == 1) & (y_true_arr == 1)))
        fp = int(np.sum((y_pred == 1) & (y_true_arr == 0)))
        fn = int(np.sum((y_pred == 0) & (y_true_arr == 1)))
        tn = int(np.sum((y_pred == 0) & (y_true_arr == 0)))

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return {
            "auc_roc": float(roc_auc_score(y_true, y_prob)) if len(set(y_true)) > 1 else None,
            "auc_pr": float(average_precision_score(y_true, y_prob)) if len(set(y_true)) > 1 else None,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "threshold": threshold,
        }
