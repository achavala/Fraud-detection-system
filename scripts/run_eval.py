"""
Run evaluation harness — generate synthetic test data and evaluate model performance.
"""
import numpy as np
from src.evaluation.harness import EvaluationHarness


def main():
    harness = EvaluationHarness(threshold_decline=0.85, threshold_review=0.55)

    np.random.seed(42)
    n = 10000
    fraud_rate = 0.03

    y_true = (np.random.random(n) < fraud_rate).astype(int).tolist()
    y_score = []
    for t in y_true:
        if t == 1:
            y_score.append(min(1.0, max(0.0, np.random.beta(5, 2) * 0.6 + 0.3)))
        else:
            y_score.append(min(1.0, max(0.0, np.random.beta(2, 8))))
    amounts = [float(np.random.lognormal(4, 1.5)) for _ in range(n)]

    print("=" * 70)
    print("CHAMPION MODEL EVALUATION: xgb-v4.2.0")
    print("=" * 70)
    champion = harness.evaluate(y_true, y_score, "xgb-v4.2.0", "all", amounts)
    _print_result(champion)

    y_score_challenger = []
    for t in y_true:
        if t == 1:
            y_score_challenger.append(min(1.0, max(0.0, np.random.beta(6, 2) * 0.6 + 0.35)))
        else:
            y_score_challenger.append(min(1.0, max(0.0, np.random.beta(2, 9))))

    print("\n" + "=" * 70)
    print("CHALLENGER MODEL EVALUATION: lgb-v5.0.0-rc1")
    print("=" * 70)
    challenger = harness.evaluate(y_true, y_score_challenger, "lgb-v5.0.0-rc1", "all", amounts)
    _print_result(challenger)

    print("\n" + "=" * 70)
    print("CHAMPION vs CHALLENGER COMPARISON")
    print("=" * 70)
    comparison = harness.compare_models(champion, challenger)
    for metric, data in comparison["comparison"].items():
        arrow = "^" if data["improved"] else "v"
        print(f"  {metric:25s}: {data['champion']:.4f} -> {data['challenger']:.4f} ({data['pct_change']:+.1f}%) {arrow}")
    print(f"\n  Recommendation: {comparison['recommendation'].upper()}")

    print("\n" + "=" * 70)
    print("REGRESSION TEST")
    print("=" * 70)
    reg = harness.regression_test(champion, challenger)
    print(f"  Passed: {reg['passed']}")
    if reg["regressions"]:
        for r in reg["regressions"]:
            print(f"  REGRESSION: {r['metric']} dropped {r['regression_pct']:.1f}%")


def _print_result(r):
    print(f"  Sample size:         {r.sample_size:,}")
    print(f"  Fraud rate:          {r.fraud_rate:.4f}")
    print(f"  AUC-ROC:             {r.auc_roc:.4f}" if r.auc_roc else "  AUC-ROC:             N/A")
    print(f"  AUC-PR:              {r.auc_pr:.4f}" if r.auc_pr else "  AUC-PR:              N/A")
    print(f"  Precision:           {r.precision:.4f}" if r.precision else "  Precision:           N/A")
    print(f"  Recall:              {r.recall:.4f}" if r.recall else "  Recall:              N/A")
    print(f"  F1:                  {r.f1:.4f}" if r.f1 else "  F1:                  N/A")
    print(f"  False Positive Rate: {r.false_positive_rate:.4f}" if r.false_positive_rate else "")
    print(f"  False Negative Rate: {r.false_negative_rate:.4f}" if r.false_negative_rate else "")
    print(f"  Approval Rate:       {r.approval_rate:.4f}" if r.approval_rate else "")
    print(f"  Decline Rate:        {r.decline_rate:.4f}" if r.decline_rate else "")
    print(f"  Review Rate:         {r.review_rate:.4f}" if r.review_rate else "")
    if r.expected_loss:
        print(f"  Expected Loss:       ${r.expected_loss:,.2f}")
    if r.prevented_loss:
        print(f"  Prevented Loss:      ${r.prevented_loss:,.2f}")


if __name__ == "__main__":
    main()
