"""Tests for the fraud simulation engine."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.simulation.fraud_simulator import FraudSimulator


@pytest.fixture
def simulator():
    return FraudSimulator(n_customers=500, n_merchants=100, n_devices=300)


def test_generate_correct_count(simulator):
    df = simulator.generate(n_transactions=1000, fraud_rate=0.03, seed=1)
    assert len(df) == 1000


def test_generate_fraud_rate_approximate(simulator):
    df = simulator.generate(n_transactions=10000, fraud_rate=0.025, seed=42)
    actual_rate = df["is_fraud"].mean()
    assert 0.015 < actual_rate < 0.04


def test_all_fraud_types_present(simulator):
    df = simulator.generate(n_transactions=10000, fraud_rate=0.03, seed=42)
    expected_types = {"normal", "card_testing", "ato", "friendly_fraud",
                      "merchant_compromise", "fraud_ring", "synthetic_identity"}
    actual_types = set(df["fraud_type"].unique())
    assert expected_types == actual_types


def test_feature_columns_present(simulator):
    df = simulator.generate(n_transactions=500, seed=10)
    expected = [
        "customer_txn_count_1h", "customer_txn_count_24h", "customer_spend_24h",
        "card_txn_count_10m", "merchant_txn_count_10m", "merchant_chargeback_rate_30d",
        "device_txn_count_1d", "device_account_count_30d", "ip_account_count_7d",
        "ip_card_count_7d", "geo_distance_from_home_km", "geo_distance_from_last_txn_km",
        "seconds_since_last_txn", "amount_vs_customer_p95_ratio",
        "amount_vs_merchant_p95_ratio", "proxy_vpn_tor_flag",
        "device_risk_score", "behavioral_risk_score", "graph_cluster_risk_score",
    ]
    for col in expected:
        assert col in df.columns, f"Missing feature: {col}"


def test_feature_bounds(simulator):
    df = simulator.generate(n_transactions=5000, seed=7)
    assert (df["device_risk_score"] >= 0).all()
    assert (df["device_risk_score"] <= 1).all()
    assert (df["behavioral_risk_score"] >= 0).all()
    assert (df["behavioral_risk_score"] <= 1).all()
    assert (df["graph_cluster_risk_score"] >= 0).all()
    assert (df["graph_cluster_risk_score"] <= 1).all()
    assert (df["billing_amount_usd"] > 0).all()


def test_chargeback_delays_only_for_fraud(simulator):
    df = simulator.generate(n_transactions=5000, fraud_rate=0.03, seed=5)
    legit = df[~df["is_fraud"]]
    fraud = df[df["is_fraud"]]
    assert legit["chargeback_delay_days"].isna().all()
    assert fraud["chargeback_delay_days"].notna().all()


def test_card_testing_features(simulator):
    df = simulator.generate(n_transactions=10000, fraud_rate=0.03, seed=42)
    ct = df[df["fraud_type"] == "card_testing"]
    normal = df[df["fraud_type"] == "normal"]
    assert ct["card_txn_count_10m"].mean() > normal["card_txn_count_10m"].mean() * 3


def test_ato_geo_distance(simulator):
    df = simulator.generate(n_transactions=10000, fraud_rate=0.03, seed=42)
    ato = df[df["fraud_type"] == "ato"]
    normal = df[df["fraud_type"] == "normal"]
    assert ato["geo_distance_from_home_km"].mean() > normal["geo_distance_from_home_km"].mean() * 10


def test_generate_with_graph_data(simulator):
    df, edges = simulator.generate_with_graph_data(n_transactions=2000, seed=42)
    assert len(df) == 2000
    assert len(edges) > 0
    assert set(edges.columns) == {"src_node_id", "dst_node_id", "edge_type", "weight"}
    assert set(edges["edge_type"].unique()) <= {"account_device", "account_ip", "device_ip"}


def test_temporal_drift(simulator):
    df = simulator.generate(n_transactions=5000, fraud_rate=0.03, seed=42)
    drifted = FraudSimulator.generate_temporal_drift(df, drift_factor=3.0, drift_start_pct=0.7)
    assert len(drifted) == len(df)
    late_fraud = drifted.iloc[int(len(drifted) * 0.7):]
    late_fraud = late_fraud[late_fraud["is_fraud"]]
    early_fraud = drifted.iloc[:int(len(drifted) * 0.7)]
    early_fraud = early_fraud[early_fraud["is_fraud"]]
    if len(late_fraud) > 0 and len(early_fraud) > 0:
        assert late_fraud["billing_amount_usd"].mean() > early_fraud["billing_amount_usd"].mean()


def test_generation_performance(simulator):
    import time
    t0 = time.perf_counter()
    sim = FraudSimulator(n_customers=10000, n_merchants=2000, n_devices=5000)
    df = sim.generate(n_transactions=50000, seed=99)
    elapsed = time.perf_counter() - t0
    assert elapsed < 10.0, f"Generation took {elapsed:.1f}s, should be < 10s"
    assert abs(len(df) - 50000) < 50, f"Expected ~50000 rows, got {len(df)}"
