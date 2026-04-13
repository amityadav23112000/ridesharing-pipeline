"""
Scale 1 EC2 — 2-Second Window Experiment (Minikube on AWS EC2 t3.xlarge)
Date: 2026-04-13
Infrastructure: AWS EC2 t3.xlarge (4 vCPU, 16 GB RAM) + Minikube
Drivers: 50,000  (K8s deployment override: NUM_DRIVERS=50000, SCALE_LEVEL=50K)
Orchestration: Kubernetes (minikube on EC2)
Window: 2 seconds  ← reduced from 5s to target <5s E2E latency
Kafka: 3-broker cluster (10 partitions, replication-factor 2)
Topics: gps-critical, gps-surge, gps-normal
DynamoDB: surge_pricing table (PAY_PER_REQUEST)
Purpose: Evaluate if 2s window reduces surge-detection latency below 5s SLA
Cost: $0.1664/hr (t3.xlarge on-demand ap-south-1)

Bug fixed this run: spark_streaming_job.py had a duplicate .withWatermark("event_timestamp", ...)
  on a STRING column — removed, keeping only .withWatermark("kafka_ts", ...) on TIMESTAMP.

Findings:
  - 2s trigger < batch-processing time (~3–5s) → Spark falls behind continuously
  - Latency degrades batch-over-batch: 13.6s → 19.1s → 23.5s → 28.9s
  - SLA <5s is NOT met at 50K scale with local[4] Spark on t3.xlarge
  - For a fair 5K comparison see scale1_ec2_results.py (5s window, 6.88s latency)
"""

# ── CLOUDWATCH METRICS (last 10 min, 300s period) ──
# Collected: 2026-04-13 ~17:43 UTC, Scale=50K, Namespace=RidesharingPipeline
cloudwatch_metrics = {
    "KafkaEventsPerSecond": {
        "avg": 3614.16,
        "max": 4478.50,
        "min": 477.50,
        "unit": "Count/Second",
        "samples": 1,
    },
    "KafkaEventsPerBatch": {
        "avg": 7228.32,
        "max": 8957.00,
        "min": 955.00,
        "unit": "Count",
        "samples": 1,
    },
    "AvgLatencyMs": {
        "avg": 26236.01,
        "max": 28914.13,
        "min": 13582.22,
        "unit": "Milliseconds",
        "samples": 1,
    },
    "P95LatencyMs": {
        "avg": 28765.94,
        "max": 32893.51,
        "min": 13928.11,
        "unit": "Milliseconds",
        "samples": 1,
    },
    "ActiveSurgeZones": {
        "avg": 55.37,
        "max": 72.00,
        "min": 34.00,
        "unit": "Count",
        "samples": 1,
    },
    "TotalWaitingRiders": {
        "avg": 3723.32,
        "max": 4571.00,
        "min": 451.00,
        "unit": "Count",
        "samples": 1,
    },
    "AvgDemandRatio": {
        "avg": 1.33,
        "max": 1.42,
        "min": 1.12,
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
        "avg": 147.76,
        "max": 148.00,
        "min": 138.00,
        "unit": "Count",
        "samples": 1,
    },
}

# ── SPARK LOG BATCH PROGRESSION ──
# Shows latency degradation as backlog builds at 2s trigger / 50K scale
batch_progression = [
    {"batch": 0,  "zones": 213, "surge_zones": 42, "avg_latency_ms": 13582, "p95_ms": 13928, "kafka_eps": 477.5,  "warn_behind": False},
    {"batch": 1,  "zones": 296, "surge_zones": 34, "avg_latency_ms": 19088, "p95_ms": 19607, "kafka_eps": 4325.5, "warn_behind": True},
    {"batch": 3,  "zones": 402, "surge_zones": 53, "avg_latency_ms": 23535, "p95_ms": 26899, "kafka_eps": 4125.5, "warn_behind": True},
    {"batch": 22, "zones": 385, "surge_zones": 59, "avg_latency_ms": 28914, "p95_ms": 31759, "kafka_eps": 3788.0, "warn_behind": True},
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
    "scale_level":     "50K",
    "drivers":         50000,
    "zones":           148,
    "aws_region":      "ap-south-1",
    "dynamodb_table":  "surge_pricing",
    "cost_per_hour":   "$0.1664",
}

# ── SLA ANALYSIS ──
sla = {
    # EPS target: 1000/s for 5K — at 50K we expect ~10000/s; achieved ~3600 avg
    "target_eps":             1000,
    "achieved_eps_avg":       3614.16,
    "eps_sla_met":            True,      # well above 1K/s threshold

    # Latency SLA: <5000ms target (from task spec)
    "target_latency_ms":      5000,
    "achieved_avg_ms":        26236.01,
    "achieved_p95_ms_avg":    28765.94,
    "achieved_p95_ms_max":    32893.51,
    "latency_sla_met":        False,     # 26s >> 5s SLA — system falling behind

    "falling_behind":         True,      # WARN: batch time (3-5s) > trigger (2s)
    "backlog_growing":        True,

    "availability_pct":       100.0,
    "data_loss_events":       0,
}

# ── COMPARISON: 5s window vs 2s window ──
comparison = {
    "baseline": {
        "experiment":    "scale1_ec2_results.py",
        "date":          "2026-04-12",
        "scale":         "5K (5,000 drivers)",
        "window_s":      5,
        "avg_latency_ms": 6882.35,
        "p95_latency_ms": 7285.18,
        "kafka_eps":      1021.90,
        "sla_5s_met":    False,   # 6.88s > 5s
        "sla_60s_met":   True,    # 6.88s << 60s
    },
    "this_run": {
        "experiment":    "scale1_ec2_2s_window.py",
        "date":          "2026-04-13",
        "scale":         "50K (50,000 drivers)",
        "window_s":      2,
        "avg_latency_ms": 26236.01,
        "p95_latency_ms": 28765.94,
        "kafka_eps":      3614.16,
        "sla_5s_met":    False,   # 26s >> 5s
        "sla_60s_met":   True,    # 26s < 60s
    },
    "verdict": (
        "2s window at 50K drivers DOES NOT meet <5s latency SLA. "
        "Spark local[4] on t3.xlarge cannot process 2s batches fast enough at 50K scale. "
        "Recommendation: reduce to 5K drivers OR use EMR (Scale 3) for 2s window at 50K."
    ),
}


# ── QUICK PRINT ──
if __name__ == "__main__":
    print("=" * 70)
    print("SCALE 1 EC2 — 2s WINDOW EXPERIMENT (2026-04-13)")
    print("=" * 70)
    print(f"\nInfrastructure: {infrastructure['platform']}")
    print(f"Drivers: {infrastructure['drivers']:,}  |  Window: {infrastructure['window_seconds']}s  |  Zones: {infrastructure['zones']}")
    print(f"\n--- CloudWatch Metrics (avg over collection window) ---")
    print(f"  Kafka EPS:          {cloudwatch_metrics['KafkaEventsPerSecond']['avg']:,.2f} events/s")
    print(f"  Events/Batch:       {cloudwatch_metrics['KafkaEventsPerBatch']['avg']:,.0f}")
    print(f"  Avg E2E Latency:    {cloudwatch_metrics['AvgLatencyMs']['avg']/1000:.2f}s")
    print(f"  P95 Latency:        {cloudwatch_metrics['P95LatencyMs']['avg']/1000:.2f}s  (max: {cloudwatch_metrics['P95LatencyMs']['max']/1000:.2f}s)")
    print(f"  Active Surge Zones: {cloudwatch_metrics['ActiveSurgeZones']['avg']:.0f}  (max: {cloudwatch_metrics['ActiveSurgeZones']['max']:.0f})")
    print(f"  Avg Demand Ratio:   {cloudwatch_metrics['AvgDemandRatio']['avg']:.2f}x")

    print(f"\n--- Batch Progression (latency degrades as backlog builds) ---")
    for b in batch_progression:
        warn = " *** FALLING BEHIND ***" if b["warn_behind"] else ""
        print(f"  Batch {b['batch']:>2}: avg={b['avg_latency_ms']/1000:.1f}s  p95={b['p95_ms']/1000:.1f}s  eps={b['kafka_eps']:.0f}{warn}")

    print(f"\n--- SLA ---")
    print(f"  Latency SLA (<5s):  {'PASS' if sla['latency_sla_met'] else 'FAIL'}  (avg {sla['achieved_avg_ms']/1000:.1f}s, p95 {sla['achieved_p95_ms_avg']/1000:.1f}s)")
    print(f"  Falling behind:     {sla['falling_behind']} (batch time ~3-5s > trigger 2s)")
    print(f"  Availability:       {sla['availability_pct']}%")

    print(f"\n--- Comparison: 5s window vs 2s window ---")
    b = comparison['baseline']
    t = comparison['this_run']
    print(f"  Baseline  ({b['scale']:>20s}, {b['window_s']}s window): avg={b['avg_latency_ms']/1000:.2f}s  p95={b['p95_latency_ms']/1000:.2f}s")
    print(f"  This run  ({t['scale']:>20s}, {t['window_s']}s window): avg={t['avg_latency_ms']/1000:.2f}s  p95={t['p95_latency_ms']/1000:.2f}s")
    print(f"\n  Verdict: {comparison['verdict']}")
    print(f"\n  Cost: {infrastructure['cost_per_hour']}/hr")
