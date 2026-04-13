"""
Scale 1 EC2 — 2-Second Window Results (Minikube on AWS EC2 t3.xlarge)
Date: 2026-04-13
Infrastructure: AWS EC2 t3.xlarge (4 vCPU, 16 GB RAM) + Minikube
Drivers: 5,000  (ConfigMap-driven, hardcoded deployment overrides removed)
Orchestration: Kubernetes (minikube on EC2)
Window: 2 seconds  ← reduced from 5s
Kafka: 3-broker cluster (10 partitions, replication-factor 2)
Topics: gps-critical, gps-surge, gps-normal
DynamoDB: surge_pricing table (PAY_PER_REQUEST)
Purpose: Fair 5K comparison — same scale as scale1_ec2_results.py but with 2s window
Cost: $0.1664/hr (t3.xlarge on-demand ap-south-1)

Changes from previous run:
  1. Removed hardcoded NUM_DRIVERS=50000 from gps-simulator-deployment.yaml
  2. Removed hardcoded SCALE_LEVEL=50K from spark-streaming-deployment.yaml
  3. Both now read from pipeline-config ConfigMap → scale switching via scripts/scale.sh
"""

# ── CLOUDWATCH METRICS (last 10 min, 300s period) ──
# Collected: 2026-04-13 ~17:55 UTC, Scale=5K, Namespace=RidesharingPipeline
cloudwatch_metrics = {
    "KafkaEventsPerSecond": {
        "avg": 1606.59,
        "max": 4903.50,
        "min": 143.00,
        "unit": "Count/Second",
        "samples": 1,
    },
    "AvgLatencyMs": {
        "avg": 5725.32,
        "max": 16965.79,
        "min": 1822.06,
        "unit": "Milliseconds",
        "samples": 1,
    },
    "P95LatencyMs": {
        "avg": 6320.59,
        "max": 20171.98,
        "min": 2132.14,
        "unit": "Milliseconds",
        "samples": 1,
    },
    "ActiveSurgeZones": {
        "avg": 49.74,
        "max": 73.00,
        "min": 17.00,
        "unit": "Count",
        "samples": 1,
    },
    "TotalWaitingRiders": {
        "avg": 1619.60,
        "max": 4947.00,
        "min": 146.00,
        "unit": "Count",
        "samples": 1,
    },
    "AvgDemandRatio": {
        "avg": 1.26,
        "max": 1.40,
        "min": 1.15,
        "unit": "None",
        "samples": 1,
    },
    "WindowSizeSeconds": {
        "avg": 2.0,
        "max": 2.0,
        "min": 2.0,
        "unit": "Seconds",
        "samples": 1,
    },
    "ZonesProcessedPerBatch": {
        "avg": 136.32,
        "max": 148.00,
        "min": 78.00,
        "unit": "Count",
        "samples": 1,
    },
}

# ── SPARK LOG BATCH BREAKDOWN ──
# Oscillating pattern: batches alternate between catching up (low) and
# accumulating (high) because batch time (~3-5s) slightly exceeds trigger (2s).
batch_samples = [
    {"batch": 1, "zones": 144, "surge_zones": 63, "avg_ms": 6527,  "p95_ms": 6873,  "p99_ms": 6921},
    {"batch": 2, "zones": 129, "surge_zones": 44, "avg_ms": 9673,  "p95_ms": 9981,  "p99_ms": 9999},
    {"batch": 3, "zones": 259, "surge_zones": 82, "avg_ms": 3982,  "p95_ms": 4507,  "p99_ms": 4570},
    {"batch": 4, "zones": 127, "surge_zones": 48, "avg_ms": 7354,  "p95_ms": 7662,  "p99_ms": 7713},
    {"batch": 6, "zones": 146, "surge_zones": 60, "avg_ms": 3109,  "p95_ms": 3434,  "p99_ms": 3578},
    {"batch": 7, "zones": 133, "surge_zones": 52, "avg_ms": 6740,  "p95_ms": 7077,  "p99_ms": 7103},
    {"batch": 9, "zones": 137, "surge_zones": 57, "avg_ms": 2313,  "p95_ms": 2649,  "p99_ms": 2726},
]

# ── INFRASTRUCTURE ──
infrastructure = {
    "platform":        "Minikube on AWS EC2 t3.xlarge",
    "driver":          "Docker (rootful)",
    "ec2_instance":    "t3.xlarge",
    "ec2_vcpus":       4,
    "ec2_ram_gb":      16,
    "minikube_cpus":   4,
    "minikube_ram_gb": 12,
    "minikube_disk_gb":20,
    "spark_master":    "local[4]",
    "kafka_brokers":   3,
    "kafka_topics":    ["gps-critical", "gps-surge", "gps-normal"],
    "partitions":      10,
    "replication":     2,
    "window_seconds":  2,
    "scale_level":     "5K",
    "drivers":         5000,
    "zones":           148,
    "aws_region":      "ap-south-1",
    "dynamodb_table":  "surge_pricing",
    "cost_per_hour":   "$0.1664",
}

# ── SLA ANALYSIS ──
sla = {
    "target_eps":             1000,
    "achieved_eps_avg":       1606.59,
    "eps_sla_met":            True,        # 1607 > 1000

    "target_latency_ms":      5000,        # <5s SLA
    "achieved_avg_ms":        5725.32,
    "achieved_p95_ms_avg":    6320.59,
    "achieved_p95_ms_max":    20171.98,
    "latency_sla_met":        False,       # 5.73s avg > 5s — just above threshold

    # Best-case batches hit <5s (batches 3, 6, 9: 3.98s / 3.11s / 2.31s)
    "best_batch_avg_ms":      2313,
    "best_batch_p95_ms":      2649,
    "sla_achievable":         True,        # many individual batches are <5s

    "availability_pct":       100.0,
    "data_loss_events":       0,
}

# ── COMPARISON: 5s window vs 2s window (both at 5K drivers, EC2 t3.xlarge) ──
comparison = {
    "baseline_5s": {
        "experiment":    "scale1_ec2_results.py",
        "date":          "2026-04-12",
        "window_s":      5,
        "avg_latency_ms": 6882.35,
        "p95_latency_ms": 7285.18,
        "kafka_eps":      1021.90,
    },
    "this_run_2s": {
        "experiment":    "scale1_ec2_2s_results.py",
        "date":          "2026-04-13",
        "window_s":      2,
        "avg_latency_ms": 5725.32,
        "p95_latency_ms": 6320.59,
        "kafka_eps":      1606.59,
    },
    "avg_latency_improvement_pct": round(
        (6882.35 - 5725.32) / 6882.35 * 100, 1),   # 16.8%
    "p95_latency_improvement_pct": round(
        (7285.18 - 6320.59) / 7285.18 * 100, 1),   # 13.2%
    "sla_5s_met_baseline": False,   # 6.88s > 5s
    "sla_5s_met_this_run": False,   # 5.73s > 5s (just above)
    "verdict": (
        "2s window reduces avg E2E latency by 16.8% (6.88s → 5.73s) and "
        "p95 by 13.2% (7.29s → 6.32s). Neither fully meets the strict <5s SLA "
        "on average. Individual batches do hit <5s (min observed: 2.31s avg). "
        "To reliably stay <5s: tune Spark parallelism (local[8] or YARN) or "
        "cap maxOffsetsPerTrigger to bound batch size."
    ),
}


# ── QUICK PRINT ──
if __name__ == "__main__":
    print("=" * 70)
    print("SCALE 1 EC2 — 2s WINDOW RESULTS (2026-04-13)")
    print("=" * 70)
    print(f"\nInfrastructure: {infrastructure['platform']}")
    print(f"Drivers: {infrastructure['drivers']:,}  |  Window: {infrastructure['window_seconds']}s  |  Zones: {infrastructure['zones']}")

    print(f"\n--- CloudWatch Metrics ---")
    print(f"  Kafka EPS:          {cloudwatch_metrics['KafkaEventsPerSecond']['avg']:,.2f} events/s")
    print(f"  Avg E2E Latency:    {cloudwatch_metrics['AvgLatencyMs']['avg']/1000:.2f}s  "
          f"(min {cloudwatch_metrics['AvgLatencyMs']['min']/1000:.2f}s, "
          f"max {cloudwatch_metrics['AvgLatencyMs']['max']/1000:.2f}s)")
    print(f"  P95 Latency:        {cloudwatch_metrics['P95LatencyMs']['avg']/1000:.2f}s  "
          f"(max {cloudwatch_metrics['P95LatencyMs']['max']/1000:.2f}s)")
    print(f"  Active Surge Zones: {cloudwatch_metrics['ActiveSurgeZones']['avg']:.0f}  "
          f"(max {cloudwatch_metrics['ActiveSurgeZones']['max']:.0f})")
    print(f"  Avg Demand Ratio:   {cloudwatch_metrics['AvgDemandRatio']['avg']:.2f}x")

    print(f"\n--- Batch Latency Samples ---")
    for b in batch_samples:
        sla_ok = "OK " if b['avg_ms'] < 5000 else "   "
        print(f"  Batch {b['batch']:>2} {sla_ok}  avg={b['avg_ms']/1000:.2f}s  "
              f"p95={b['p95_ms']/1000:.2f}s  zones={b['zones']}")

    print(f"\n--- SLA ---")
    print(f"  Latency SLA (<5s):  {'PASS' if sla['latency_sla_met'] else 'FAIL'}  "
          f"(avg {sla['achieved_avg_ms']/1000:.2f}s — {abs(sla['achieved_avg_ms']-5000)/1000:.2f}s "
          f"{'above' if sla['achieved_avg_ms'] > 5000 else 'below'} target)")
    print(f"  EPS SLA (≥1000):    {'PASS' if sla['eps_sla_met'] else 'FAIL'}  "
          f"({sla['achieved_eps_avg']:.0f} eps)")
    print(f"  Best batch latency: {sla['best_batch_avg_ms']/1000:.2f}s avg / "
          f"{sla['best_batch_p95_ms']/1000:.2f}s p95  ← SLA achievable")
    print(f"  Availability:       {sla['availability_pct']}%")

    print(f"\n--- Comparison: 5s window → 2s window (5K drivers, EC2 t3.xlarge) ---")
    b = comparison['baseline_5s']
    t = comparison['this_run_2s']
    print(f"  {'Window':<8} {'Drivers':<10} {'Avg Latency':<16} {'P95 Latency':<16} {'SLA <5s'}")
    print(f"  {'-'*68}")
    print(f"  {b['window_s']}s       {5000:<10,} {b['avg_latency_ms']/1000:.2f}s           "
          f"{b['p95_latency_ms']/1000:.2f}s           FAIL")
    print(f"  {t['window_s']}s       {5000:<10,} {t['avg_latency_ms']/1000:.2f}s           "
          f"{t['p95_latency_ms']/1000:.2f}s           FAIL")
    print(f"\n  Avg latency improvement: {comparison['avg_latency_improvement_pct']}%")
    print(f"  P95 latency improvement: {comparison['p95_latency_improvement_pct']}%")
    print(f"\n  Verdict: {comparison['verdict']}")
    print(f"\n  Cost: {infrastructure['cost_per_hour']}/hr")
