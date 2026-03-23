"""
Generate a realistic fraud simulation dataset, train models on it,
and produce a data quality report.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from src.simulation.fraud_simulator import FraudSimulator


def main():
    print("=" * 70)
    print("FRAUD SIMULATION — GOLD DEMO DATASET GENERATION")
    print("=" * 70)

    sim = FraudSimulator(n_customers=10_000, n_merchants=2_000, n_devices=5_000)

    t0 = time.perf_counter()
    df, edges = sim.generate_with_graph_data(
        n_transactions=100_000,
        fraud_rate=0.025,
        start_date="2025-01-01",
        end_date="2025-12-31",
        seed=42,
    )
    gen_time = time.perf_counter() - t0
    print(f"\nGenerated {len(df):,} transactions in {gen_time:.2f}s")
    print(f"Graph edges: {len(edges):,}")

    print("\n--- Fraud Distribution ---")
    fraud_counts = df.groupby("fraud_type").agg(
        count=("is_fraud", "size"),
        pct=("is_fraud", lambda x: f"{len(x) / len(df) * 100:.2f}%"),
        avg_amount=("billing_amount_usd", "mean"),
    )
    print(fraud_counts.to_string())

    print("\n--- Class Balance ---")
    n_fraud = df["is_fraud"].sum()
    n_legit = len(df) - n_fraud
    print(f"  Legitimate: {n_legit:>8,} ({n_legit / len(df) * 100:.1f}%)")
    print(f"  Fraud:      {n_fraud:>8,} ({n_fraud / len(df) * 100:.1f}%)")

    print("\n--- Chargeback Delay (fraud only) ---")
    delays = df.loc[df["is_fraud"], "chargeback_delay_days"].dropna()
    if len(delays) > 0:
        print(f"  Mean:   {delays.mean():>6.1f} days")
        print(f"  Median: {delays.median():>6.1f} days")
        print(f"  Max:    {delays.max():>6.1f} days")
        print(f"  >30d:   {(delays > 30).sum():>6,} ({(delays > 30).mean() * 100:.1f}%)")

    print("\n--- Feature Statistics (fraud vs legit) ---")
    feature_cols = [c for c in df.columns if c not in [
        "customer_id", "account_id", "card_id", "merchant_id",
        "device_id", "ip_address", "auth_type", "channel", "entry_mode",
        "auth_amount", "currency_code", "merchant_country_code",
        "billing_amount_usd", "event_time", "is_fraud", "fraud_type",
        "chargeback_delay_days", "transaction_id",
    ]]
    for col in feature_cols[:10]:
        fraud_mean = df.loc[df["is_fraud"], col].mean()
        legit_mean = df.loc[~df["is_fraud"], col].mean()
        sep = fraud_mean / (legit_mean + 1e-9)
        print(f"  {col:>35s}: fraud_mean={fraud_mean:>8.2f} legit_mean={legit_mean:>8.2f} separation={sep:.2f}x")

    print("\n--- Graph Edge Types ---")
    print(edges.groupby("edge_type").agg(count=("weight", "size"), avg_weight=("weight", "mean")).to_string())

    t1 = time.perf_counter()
    drifted = FraudSimulator.generate_temporal_drift(df, drift_factor=2.0, drift_start_pct=0.7)
    drift_time = time.perf_counter() - t1
    print(f"\nApplied concept drift in {drift_time:.2f}s")

    late_fraud_mean = drifted.iloc[int(len(drifted) * 0.7):].loc[drifted["is_fraud"], "billing_amount_usd"].mean()
    early_fraud_mean = drifted.iloc[:int(len(drifted) * 0.7)].loc[drifted["is_fraud"], "billing_amount_usd"].mean()
    print(f"  Early fraud avg amount: ${early_fraud_mean:,.2f}")
    print(f"  Late fraud avg amount:  ${late_fraud_mean:,.2f} (drift factor ~{late_fraud_mean / early_fraud_mean:.1f}x)")

    out_dir = Path(__file__).parent.parent / "data"
    out_dir.mkdir(exist_ok=True)
    df.to_parquet(out_dir / "simulation_100k.parquet", index=False)
    edges.to_parquet(out_dir / "simulation_edges.parquet", index=False)
    drifted.to_parquet(out_dir / "simulation_100k_drifted.parquet", index=False)
    print(f"\nDatasets saved to {out_dir}/")
    print("=" * 70)


if __name__ == "__main__":
    main()
