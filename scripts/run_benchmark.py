"""
Run the latency/load benchmark suite and print a production-readiness report.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.evaluation.benchmark import BenchmarkSuite


def main():
    print("=" * 70)
    print("FRAUD PLATFORM — LATENCY & LOAD BENCHMARK REPORT")
    print("=" * 70)

    suite = BenchmarkSuite(db=None)  # type: ignore
    report = suite.generate_report()

    for section, data in report["benchmarks"].items():
        print(f"\n--- {section.replace('_', ' ').title()} ---")
        for k, v in data.items():
            if isinstance(v, float):
                print(f"  {k:>20s}: {v:>10.3f} ms")
            else:
                print(f"  {k:>20s}: {v}")

    print("\n" + "=" * 70)
    print("SLO RESULTS")
    print("=" * 70)
    for slo, result in report["slo"].items():
        status = "PASS" if result == "PASS" else "FAIL"
        marker = "[OK]" if status == "PASS" else "[!!]"
        print(f"  {marker} {slo}: {result}")

    all_pass = all(v == "PASS" for v in report["slo"].values())
    print(f"\nOverall: {'ALL SLOs MET' if all_pass else 'SLO VIOLATIONS DETECTED'}")
    print("=" * 70)

    out_path = Path(__file__).parent.parent / "reports" / "benchmark_report.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report written to: {out_path}")


if __name__ == "__main__":
    main()
