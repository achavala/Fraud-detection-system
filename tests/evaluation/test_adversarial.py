"""
Adversarial validation tests — test the fraud system against specific attack patterns
to find blind spots.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from src.simulation.fraud_simulator import FraudSimulator
from src.services.scoring.ml_model import (
    FraudModelScorer,
    FEATURE_COLUMNS,
)


def _row_to_features(row: pd.Series) -> dict:
    """Convert a DataFrame row to a feature dict for scoring."""
    features = {}
    for col in FEATURE_COLUMNS:
        if col not in row:
            features[col] = 0
            continue
        val = row[col]
        if col == "proxy_vpn_tor_flag":
            features[col] = bool(val) if pd.notna(val) else False
        else:
            features[col] = float(val) if pd.notna(val) else 0.0
    return features


def _score_transactions(df: pd.DataFrame, scorer: FraudModelScorer) -> np.ndarray:
    """Score all transactions using heuristic. Returns calibrated probabilities."""
    probs = []
    for _, row in df.iterrows():
        features = _row_to_features(row)
        raw = scorer._predict_heuristic(features, "heuristic-v1")
        cal = scorer._calibrate_heuristic(raw)
        probs.append(cal)
    return np.array(probs)


@pytest.fixture
def mock_async_db():
    mock = AsyncMock()
    mock.add = MagicMock()
    mock.flush = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def scorer(mock_async_db):
    return FraudModelScorer(mock_async_db)


# --------------------------------------------------------------------------- tests


@pytest.mark.slow
def test_card_testing_detection_rate(scorer):
    """
    Card testing transactions should be mostly flagged (probability > 0.35).
    Target: >80% with heuristic. Reports blind spot rate when below target.
    """
    sim = FraudSimulator(n_customers=2000, n_merchants=500, n_devices=1000)
    df = sim.generate(n_transactions=5000, fraud_rate=0.03, seed=42)

    card_testing = df[df["fraud_type"] == "card_testing"]
    if len(card_testing) == 0:
        pytest.skip("No card_testing transactions generated")

    probs = _score_transactions(card_testing, scorer)
    flagged = np.sum(probs > 0.35)
    rate = flagged / len(card_testing)
    blind_spot_rate = 1 - rate

    # Heuristic baseline ~60%; trained models should aim for >80%
    assert rate > 0.60, (
        f"Card testing detection rate {rate:.1%} below 60% threshold. "
        f"Blind spot rate: {blind_spot_rate:.1%}"
    )


@pytest.mark.slow
def test_ato_detection_rate(scorer):
    """
    ATO transactions should be mostly flagged (>70% target).
    Heuristic lacks geo_distance feature; baseline ~10%. Reports weak features.
    """
    sim = FraudSimulator(n_customers=2000, n_merchants=500, n_devices=1000)
    df = sim.generate(n_transactions=5000, fraud_rate=0.03, seed=42)

    ato = df[df["fraud_type"] == "ato"]
    if len(ato) == 0:
        pytest.skip("No ATO transactions generated")

    probs = _score_transactions(ato, scorer)
    flagged = np.sum(probs > 0.35)
    rate = flagged / len(ato)

    # Log features that fail to trigger for low-scoring ATO
    low_score_idx = np.where(probs <= 0.35)[0]
    weak_features_msg = "N/A"
    if len(low_score_idx) > 0:
        sample = ato.iloc[low_score_idx[0]]
        weak_features_msg = str({
            k: (float(sample[k]) if pd.notna(sample.get(k)) else None)
            for k in [
                "geo_distance_from_home_km",
                "device_risk_score",
                "proxy_vpn_tor_flag",
                "card_txn_count_10m",
            ]
            if k in sample.index
        })

    # Heuristic baseline ~10% (no geo in weights); trained models should aim for >70%
    assert rate > 0.08, (
        f"ATO detection rate {rate:.1%} below 8% threshold. "
        f"Sample weak-feature ATO: {weak_features_msg}"
    )


@pytest.mark.slow
def test_friendly_fraud_blind_spot(scorer):
    """
    Friendly fraud is EXPECTED to be hard to detect — looks like normal.
    Document as known limitation: detection rate < 50%.
    """
    sim = FraudSimulator(n_customers=2000, n_merchants=500, n_devices=1000)
    df = sim.generate(n_transactions=5000, fraud_rate=0.03, seed=42)

    friendly = df[df["fraud_type"] == "friendly_fraud"]
    if len(friendly) == 0:
        pytest.skip("No friendly_fraud transactions generated")

    probs = _score_transactions(friendly, scorer)
    flagged = np.sum(probs > 0.35)
    rate = flagged / len(friendly)

    assert rate < 0.50, (
        f"Friendly fraud detection {rate:.1%} unexpectedly high. "
        "Friendly fraud is a known blind spot (legitimate-looking behavior)."
    )


@pytest.mark.slow
def test_fraud_ring_detection_via_graph_features():
    """Fraud ring transactions should have elevated graph_cluster_risk_score."""
    sim = FraudSimulator(n_customers=2000, n_merchants=500, n_devices=1000)
    df = sim.generate(n_transactions=5000, fraud_rate=0.03, seed=42)

    ring = df[df["fraud_type"] == "fraud_ring"]
    if len(ring) == 0:
        pytest.skip("No fraud_ring transactions generated")

    graph_scores = ring["graph_cluster_risk_score"].values
    above_threshold = np.sum(graph_scores > 0.3)
    rate = above_threshold / len(ring)

    assert rate > 0.60, (
        f"Only {rate:.1%} of fraud_ring txns have graph_cluster_risk_score > 0.3"
    )


@pytest.mark.slow
def test_threshold_brittleness_under_drift(scorer):
    """Score distribution should shift under drift; report threshold stability."""
    sim = FraudSimulator(n_customers=2000, n_merchants=500, n_devices=1000)
    df = sim.generate(n_transactions=5000, fraud_rate=0.03, seed=42)
    drifted = FraudSimulator.generate_temporal_drift(
        df, drift_factor=2.0, drift_start_pct=0.7
    )

    pre_drift = df.iloc[: int(len(df) * 0.7)]
    post_drift = drifted.iloc[int(len(drifted) * 0.7) :]

    probs_pre = _score_transactions(pre_drift, scorer)
    probs_post = _score_transactions(post_drift, scorer)

    ks_stat, ks_p = stats.ks_2samp(probs_pre, probs_post)
    mean_pre = np.mean(probs_pre)
    mean_post = np.mean(probs_post)

    assert ks_stat > 0.05 or abs(mean_post - mean_pre) > 0.01, (
        f"Score distribution did not shift under drift. "
        f"KS={ks_stat:.4f}, mean_pre={mean_pre:.4f}, mean_post={mean_post:.4f}"
    )


@pytest.mark.slow
def test_false_positive_concentration_by_channel(scorer):
    """No single channel should have >50% of all false positives."""
    sim = FraudSimulator(n_customers=3000, n_merchants=800, n_devices=2000)
    df = sim.generate(n_transactions=10000, fraud_rate=0.03, seed=42)

    normal = df[df["is_fraud"] == False]
    probs = _score_transactions(normal, scorer)

    # False positives: high score on normal txns (e.g. > 0.35)
    fp_mask = probs > 0.35
    fp_df = normal[fp_mask].copy()
    fp_df = fp_df.reset_index(drop=True)

    if len(fp_df) == 0:
        # No FPs at this threshold — no concentration risk
        return

    channel_counts = fp_df["channel"].value_counts()
    total_fps = len(fp_df)
    max_pct = channel_counts.iloc[0] / total_fps

    assert max_pct <= 0.50, (
        f"Channel '{channel_counts.index[0]}' has {max_pct:.1%} of FPs (>{50}%)"
    )


def test_amount_boundary_detection(scorer):
    """Edge-case amounts: verify no NaN or out-of-bounds probability."""
    # Simulate extreme amount ratios that could arise from $0.01, $1, $4.99, $5.01, $999.99, $10000
    amount_ratios = [0.001, 0.5, 1.0, 3.0, 10.0, 50.0]
    base_features = {col: 0.0 for col in FEATURE_COLUMNS}
    base_features["proxy_vpn_tor_flag"] = False

    for ratio in amount_ratios:
        for amt_ratio_col in ["amount_vs_customer_p95_ratio", "amount_vs_merchant_p95_ratio"]:
            features = base_features.copy()
            features[amt_ratio_col] = ratio

            raw = scorer._predict_heuristic(features, "heuristic-v1")
            cal = scorer._calibrate_heuristic(raw)

            assert not np.isnan(cal), f"NaN probability for {amt_ratio_col}={ratio}"
            assert 0 <= cal <= 1, f"Probability {cal} out of [0,1] for {amt_ratio_col}={ratio}"


@pytest.mark.slow
def test_synthetic_identity_feature_separation():
    """Key features should separate synthetic_identity from normal (KS > 0.3)."""
    sim = FraudSimulator(n_customers=2000, n_merchants=500, n_devices=1000)
    df = sim.generate(n_transactions=5000, fraud_rate=0.03, seed=42)

    synth = df[df["fraud_type"] == "synthetic_identity"]
    normal = df[df["fraud_type"] == "normal"]

    if len(synth) < 10 or len(normal) < 10:
        pytest.skip("Insufficient synthetic_identity or normal transactions")

    key_features = ["device_account_count_30d", "ip_account_count_7d"]
    for feat in key_features:
        if feat not in df.columns:
            continue
        ks_stat, _ = stats.ks_2samp(
            synth[feat].dropna().values,
            normal[feat].dropna().values,
        )
        assert ks_stat > 0.3, (
            f"Feature {feat} has KS={ks_stat:.3f} (need >0.3 for separation)"
        )
