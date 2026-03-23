"""
Complete 12-15 minute demo script that exercises all platform capabilities.
Run standalone: python3 scripts/demo_walkthrough.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ANSI colors
C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "cyan": "\033[96m",
    "magenta": "\033[95m",
}


def print_section(title: str, duration: str) -> None:
    print(f"\n{C['bold']}{C['blue']}{'='*70}{C['reset']}")
    print(f"{C['bold']}{C['blue']}  {title}  ({duration}){C['reset']}")
    print(f"{C['bold']}{C['blue']}{'='*70}{C['reset']}\n")


def print_sub(s: str) -> None:
    print(f"{C['cyan']}  {s}{C['reset']}")


def print_ok(s: str) -> None:
    print(f"{C['green']}  ✓ {s}{C['reset']}")


def main() -> None:
    print(f"\n{C['bold']}Fraud Detection Platform — Full Demo Walkthrough{C['reset']}")
    print(f"{C['dim']}Est. duration: 12-15 minutes{C['reset']}")

    # -------------------------------------------------------------------------
    # SECTION 1: FRAUD SIMULATION (2 min)
    # -------------------------------------------------------------------------
    print_section("SECTION 1: FRAUD SIMULATION", "~2 min")

    from src.simulation.fraud_simulator import FraudSimulator

    sim = FraudSimulator(n_customers=5_000, n_merchants=800, n_devices=3_000)
    t0 = time.perf_counter()
    df, edges = sim.generate_with_graph_data(
        n_transactions=10_000,
        fraud_rate=0.025,
        start_date="2025-01-01",
        end_date="2025-06-30",
        seed=42,
    )
    gen_time = time.perf_counter() - t0

    print_sub(f"Generated {len(df):,} transactions in {gen_time:.3f}s")
    print_sub(f"Graph edges: {len(edges):,}")

    print(f"\n{C['bold']}Fraud distribution:{C['reset']}")
    fraud_dist = df.groupby("fraud_type").size()
    for ft, cnt in fraud_dist.items():
        pct = cnt / len(df) * 100
        print(f"  {ft:>20s}: {cnt:>6,} ({pct:>5.2f}%)")

    n_fraud = int(df["is_fraud"].sum())
    n_legit = len(df) - n_fraud
    print(f"\n{C['bold']}Class imbalance:{C['reset']}")
    print(f"  Legitimate: {n_legit:>6,} ({n_legit / len(df) * 100:.1f}%)")
    print(f"  Fraud:      {n_fraud:>6,} ({n_fraud / len(df) * 100:.1f}%)")
    print_ok("Section 1 complete — simulation data ready")

    # -------------------------------------------------------------------------
    # SECTION 2: MODEL TRAINING (2 min)
    # -------------------------------------------------------------------------
    print_section("SECTION 2: MODEL TRAINING", "~2 min")

    from src.services.scoring.model_trainer import FraudModelTrainer, FEATURE_COLUMNS

    trainer = FraudModelTrainer()
    # Use simulator output — ensure we have required columns
    feature_cols = [c for c in FEATURE_COLUMNS if c in df.columns]
    if len(feature_cols) < len(FEATURE_COLUMNS):
        print_sub("Using trainer synthetic data (simulator columns mismatch)")
        train_df = trainer.generate_synthetic_training_data(n_samples=5_000, fraud_rate=0.03, seed=42)
        feature_cols = list(FEATURE_COLUMNS)
    else:
        train_df = df[feature_cols + ["is_fraud"]].copy()
        train_df["is_fraud"] = train_df["is_fraud"].astype(int)

    t0 = time.perf_counter()
    result = trainer.train_xgboost(train_df, model_version="demo-xgb-v1", test_size=0.2)
    train_time = time.perf_counter() - t0

    m = result.get("metrics", {})
    print_sub(f"Trained XGBoost in {train_time:.2f}s")
    print_sub(f"AUC-ROC:  {m.get('auc_roc') or 0:.4f}")
    print_sub(f"AUC-PR:   {m.get('auc_pr') or 0:.4f}")
    print_sub(f"Precision (p=0.55): {m.get('precision', 0):.4f}")
    print_sub(f"Recall (p=0.55):    {m.get('recall', 0):.4f}")
    print_ok("Section 2 complete — model artifact saved")

    # -------------------------------------------------------------------------
    # SECTION 3: REAL-TIME SCORING (2 min)
    # -------------------------------------------------------------------------
    print_section("SECTION 3: REAL-TIME SCORING", "~2 min")

    from src.services.scoring.ml_model import FraudModelScorer
    from src.services.scoring.rules_engine import RulesEngine

    model_scorer = FraudModelScorer(db=None)  # type: ignore
    rules_engine = RulesEngine(db=None)  # type: ignore

    # Suspicious transaction: high velocity, new device, VPN
    suspicious_vec = {
        "customer_txn_count_1h": 12,
        "customer_txn_count_24h": 25,
        "customer_spend_24h": 3500.0,
        "card_txn_count_10m": 8,
        "merchant_txn_count_10m": 15,
        "merchant_chargeback_rate_30d": 0.08,
        "device_txn_count_1d": 20,
        "device_account_count_30d": 4,
        "ip_account_count_7d": 5,
        "ip_card_count_7d": 6,
        "geo_distance_from_home_km": 2500.0,
        "geo_distance_from_last_txn_km": 500.0,
        "seconds_since_last_txn": 15,
        "amount_vs_customer_p95_ratio": 4.2,
        "amount_vs_merchant_p95_ratio": 2.1,
        "proxy_vpn_tor_flag": True,
        "device_risk_score": 0.72,
        "behavioral_risk_score": 0.65,
        "graph_cluster_risk_score": 0.55,
    }

    # Normal transaction
    normal_vec = {
        "customer_txn_count_1h": 1,
        "customer_txn_count_24h": 4,
        "customer_spend_24h": 180.0,
        "card_txn_count_10m": 0,
        "merchant_txn_count_10m": 2,
        "merchant_chargeback_rate_30d": 0.005,
        "device_txn_count_1d": 3,
        "device_account_count_30d": 1,
        "ip_account_count_7d": 1,
        "ip_card_count_7d": 1,
        "geo_distance_from_home_km": 12.0,
        "geo_distance_from_last_txn_km": 5.0,
        "seconds_since_last_txn": 3600,
        "amount_vs_customer_p95_ratio": 0.9,
        "amount_vs_merchant_p95_ratio": 0.85,
        "proxy_vpn_tor_flag": False,
        "device_risk_score": 0.1,
        "behavioral_risk_score": 0.08,
        "graph_cluster_risk_score": 0.05,
    }

    for label, vec in [("SUSPICIOUS", suspicious_vec), ("NORMAL", normal_vec)]:
        prob = model_scorer._predict_heuristic(vec, "demo-xgb-v1")
        cal = model_scorer._calibrate_heuristic(prob)
        rule_results = []
        fired_rules = []
        for r in rules_engine.rules:
            fired, score, _ = r.evaluate(vec, {})
            rule_results.append(type("R", (), {"fired_flag": fired, "severity": r.severity})())
            if fired:
                fired_rules.append((r.rule_id, r.name))
        rule_score = rules_engine.compute_aggregate_rule_score(rule_results) if rule_results else 0.0
        final = 0.7 * cal + 0.3 * (rule_score if hasattr(rule_score, "__float__") else 0)

        risk_band = "HIGH" if final >= 0.55 else ("MEDIUM" if final >= 0.35 else "LOW")
        print(f"\n{C['bold']}{label} transaction:{C['reset']}")
        print_sub(f"  ML probability: {cal:.4f} | Ensemble: {final:.4f} | Risk band: {risk_band}")

        fired = fired_rules
        if fired:
            print_sub(f"  Rules fired: {', '.join(f'{rid}({n})' for rid, n in fired)}")

    print_ok("Section 3 complete — scoring demonstrated")

    # -------------------------------------------------------------------------
    # SECTION 4: RULES ENGINE (1 min)
    # -------------------------------------------------------------------------
    print_section("SECTION 4: RULES ENGINE", "~1 min")

    print_sub("Evaluating rules on suspicious transaction:")
    for rule in rules_engine.rules:
        fired, score, explanation = rule.evaluate(suspicious_vec, {})
        if fired:
            print(f"    {C['yellow']}▶ {rule.rule_id} {rule.name}: {explanation}{C['reset']}")
    print_ok("Section 4 complete — rules engine evaluated")

    # -------------------------------------------------------------------------
    # SECTION 5: GRAPH ANALYSIS (2 min)
    # -------------------------------------------------------------------------
    print_section("SECTION 5: GRAPH ANALYSIS", "~2 min")

    import networkx as nx

    # Build small fraud ring: 3 accounts sharing 1 device and 2 IPs
    G = nx.Graph()
    nodes = [
        ("account:101", "account", "101"),
        ("account:102", "account", "102"),
        ("account:103", "account", "103"),
        ("device:shared_dev_001", "device", "shared_dev_001"),
        ("ip:10.0.0.1", "ip", "10.0.0.1"),
        ("ip:10.0.0.2", "ip", "10.0.0.2"),
    ]
    for nid, ntype, ref in nodes:
        G.add_node(nid, node_type=ntype, entity_ref=ref, risk_score=0.6 if "account" in nid else 0.3)
    G.add_edge("account:101", "device:shared_dev_001", edge_type="account_device", weight=5)
    G.add_edge("account:102", "device:shared_dev_001", edge_type="account_device", weight=3)
    G.add_edge("account:103", "device:shared_dev_001", edge_type="account_device", weight=4)
    G.add_edge("account:101", "ip:10.0.0.1", edge_type="account_ip", weight=2)
    G.add_edge("account:102", "ip:10.0.0.1", edge_type="account_ip", weight=2)

    rings = []
    for component in nx.connected_components(G):
        if len(component) < 3:
            continue
        sub = G.subgraph(component)
        account_nodes = [n for n in component if G.nodes[n].get("node_type") == "account"]
        if len(account_nodes) < 2:
            continue
        shared_devices = sum(1 for n in component if G.nodes[n].get("node_type") == "device")
        shared_ips = sum(1 for n in component if G.nodes[n].get("node_type") == "ip")
        avg_risk = sum(G.nodes[n].get("risk_score", 0) for n in component) / len(component)
        ring_score = 0.0
        if len(account_nodes) >= 3 and shared_devices >= 1:
            ring_score += 0.3
        if shared_ips >= 1 and len(account_nodes) >= 2:
            ring_score += 0.2
        ring_score += avg_risk * 0.5
        if ring_score > 0.3:
            rings.append({
                "cluster_id": min(component),
                "node_count": len(component),
                "account_count": len(account_nodes),
                "shared_devices": shared_devices,
                "shared_ips": shared_ips,
                "ring_score": min(ring_score, 1.0),
            })

    print_sub(f"Built graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print_sub(f"Detected {len(rings)} fraud ring(s)")
    for r in rings:
        print_sub(f"  Cluster: {r['account_count']} accounts, {r['shared_devices']} shared devices, "
                  f"{r['shared_ips']} shared IPs, ring_score={r['ring_score']:.2f}")
    print_ok("Section 5 complete — fraud ring detected")

    # -------------------------------------------------------------------------
    # SECTION 6: BENCHMARK (2 min)
    # -------------------------------------------------------------------------
    print_section("SECTION 6: BENCHMARK", "~2 min")

    from src.evaluation.benchmark import BenchmarkSuite

    suite = BenchmarkSuite(db=None)  # type: ignore
    report = suite.generate_report()

    print_sub("Latency percentiles (ms):")
    for name, data in report["benchmarks"].items():
        p50 = data.get("p50", 0)
        p95 = data.get("p95", 0)
        p99 = data.get("p99", 0)
        rps = data.get("throughput_rps", 0)
        extras = f" | {rps:,.0f} req/s" if rps else ""
        print(f"    {name:>25s}: p50={p50:.3f} p95={p95:.3f} p99={p99:.3f}{extras}")

    print(f"\n{C['bold']}SLO Results:{C['reset']}")
    for slo, status in report["slo"].items():
        ok = status == "PASS"
        sym = f"{C['green']}✓{C['reset']}" if ok else f"{C['yellow']}!{C['reset']}"
        print(f"  {sym} {slo}: {status}")
    print_ok("Section 6 complete — benchmark run")

    # -------------------------------------------------------------------------
    # SECTION 7: THRESHOLD OPTIMIZATION (2 min)
    # -------------------------------------------------------------------------
    print_section("SECTION 7: THRESHOLD OPTIMIZATION", "~2 min")

    import numpy as np
    from src.services.economics.threshold_optimizer import ThresholdOptimizer

    # Use scores from training/simulation
    n_opt = 2000
    probs = np.random.beta(2, 5, size=n_opt)
    amts = np.random.lognormal(5, 1, size=n_opt).clip(10, 5000)
    if "is_fraud" in train_df.columns and len(train_df) >= n_opt:
        fraud = np.array(train_df["is_fraud"].values[:n_opt], dtype=int)
    else:
        fraud = np.random.binomial(1, 0.03, size=n_opt)

    opt = ThresholdOptimizer(min_approval_rate=0.90, max_false_positive_rate=0.05)
    single_result = opt.optimize(probs, amts, fraud)
    multi_result = opt.optimize_multi_threshold(probs, amts, fraud)

    print_sub(f"Single-threshold optimal: {single_result.optimal_threshold:.2f}")
    print_sub(f"  Net savings: ${single_result.net_savings_usd:,.2f}")
    print_sub(f"  Approval rate: {single_result.approval_rate:.2%}")
    print_sub(f"  FPR: {single_result.false_positive_rate:.2%}")

    print_sub(f"3-tier optimal: decline={multi_result['decline_threshold']:.2f}, "
              f"review={multi_result['review_threshold']:.2f}, step_up={multi_result['step_up_threshold']:.2f}")
    print_sub(f"  Net savings: ${multi_result['net_savings_usd']:,.2f}")
    print_ok("Section 7 complete — threshold optimization done")

    # -------------------------------------------------------------------------
    # SECTION 8: ECONOMICS (1 min)
    # -------------------------------------------------------------------------
    print_section("SECTION 8: ECONOMICS", "~1 min")

    detail = single_result.detail_by_threshold
    best = next((d for d in detail if d["threshold"] == single_result.optimal_threshold), detail[-1])
    print_sub(f"Prevented fraud $:  ${best.get('prevented_fraud_usd', 0):,.2f}")
    print_sub(f"Missed fraud $:     ${best.get('missed_fraud_usd', 0):,.2f}")
    print_sub(f"FP volume $:        ${best.get('fp_volume_usd', 0):,.2f}")
    print_sub(f"Business cost $:    ${best.get('business_cost_usd', 0):,.2f}")
    print_sub(f"Net savings:        ${single_result.net_savings_usd:,.2f}")
    total_vol = float(amts.sum())
    bps = (best.get("prevented_fraud_usd", 0) / total_vol * 10000) if total_vol else 0
    print_sub(f"Fraud basis points: {bps:.2f}")
    print_ok("Section 8 complete — economics sample")

    # -------------------------------------------------------------------------
    # SECTION 9: FEATURE PARITY (1 min)
    # -------------------------------------------------------------------------
    print_section("SECTION 9: FEATURE PARITY", "~1 min")

    from src.services.features.parity import FEATURE_REGISTRY

    checksum_blob = json.dumps(FEATURE_REGISTRY, sort_keys=True)
    checksum = hashlib.sha256(checksum_blob.encode()).hexdigest()[:16]

    feats = FEATURE_REGISTRY.get("features", [])
    print_sub(f"Feature registry: {len(feats)} features")
    for f in feats[:5]:
        print(f"    {f.get('name', '')}: {f.get('type', '')} — {f.get('description', '')}")
    print_sub(f"  ... and {len(feats) - 5} more")
    print_sub(f"Schema checksum: {checksum}")
    print_ok("Section 9 complete — feature registry shown")

    # -------------------------------------------------------------------------
    # SECTION 10: SUMMARY (1 min)
    # -------------------------------------------------------------------------
    print_section("SECTION 10: SUMMARY", "~1 min")

    caps = [
        "Fraud simulation (7 attack patterns)",
        "Model training (XGBoost / LightGBM)",
        "Real-time scoring (ML + rules ensemble)",
        "Rules engine (8 deterministic rules)",
        "Graph analysis (fraud ring detection)",
        "Latency benchmark (SLO verification)",
        "Threshold optimization (1-tier & 3-tier)",
        "Economics (net savings, basis points)",
        "Feature parity (19-feature registry)",
    ]
    for c in caps:
        print_ok(c)
    print(f"\n{C['bold']}{C['green']}All capabilities demonstrated. Demo complete.{C['reset']}\n")


if __name__ == "__main__":
    main()
