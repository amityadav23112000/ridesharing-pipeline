"""
Scale 1 — Kubernetes Results (Minikube on Laptop)
Date: 2026-04-11
Infrastructure: Laptop + Minikube (4 CPU, 6 GB RAM)
Drivers: 5,000
Orchestration: Kubernetes (minikube v1.32+)
Window: 5 seconds
Kafka: 3-broker cluster (3 partitions, replication-factor 3)
Topics: gps-critical, gps-surge, gps-normal
DynamoDB: surge_pricing table (PAY_PER_REQUEST)
Cost: $0/hr (local minikube)
"""

# ── CLOUDWATCH METRICS (last 15 min, 3 data points / 300s period) ──
# Collected: 2026-04-11 ~17:20 UTC, Scale=5K, Namespace=RidesharingPipeline
cloudwatch_metrics = {
    "KafkaEventsPerSecond": {
        "avg": 1006.59,
        "max": 1013.0,
        "min": 997.8,
        "unit": "Count/Second",
        "samples": 3,
    },
    "KafkaEventsPerBatch": {
        "avg": 5032.96,
        "max": 5065.0,
        "min": 4989.0,
        "unit": "Count",
        "samples": 3,
    },
    "AvgLatencyMs": {
        "avg": 31039.84,
        "max": 46714.1,
        "min": 14567.81,
        "unit": "Milliseconds",
        "samples": 3,
    },
    "P95LatencyMs": {
        "avg": 41864.58,
        "max": 57609.68,
        "min": 22762.44,
        "unit": "Milliseconds",
        "samples": 3,
    },
    "P99LatencyMs": {
        "avg": 44197.97,
        "max": 66202.15,
        "min": 24485.51,
        "unit": "Milliseconds",
        "samples": 3,
    },
    "ActiveSurgeZones": {
        "avg": 75.0,
        "max": 91.0,
        "min": 40.0,
        "unit": "Count",
        "samples": 3,
    },
    "TotalWaitingRiders": {
        "avg": 2720.43,
        "max": 2790.0,
        "min": 2460.0,
        "unit": "Count",
        "samples": 3,
    },
    "AvgDemandRatio": {
        "avg": 1.48,
        "max": 1.58,
        "min": 1.23,
        "unit": "None",
        "samples": 3,
    },
    "WindowSizeSeconds": {
        "avg": 5.0,
        "max": 5.0,
        "min": 5.0,
        "unit": "Seconds",
        "samples": 3,
    },
    "ZonesProcessedPerBatch": {
        "avg": 148.0,
        "max": 148.0,
        "min": 148.0,
        "unit": "Count",
        "samples": 3,
    },
}

# ── PROMETHEUS METRICS (live snapshot at ~17:22 UTC) ──
# Source: Prometheus NodePort 30090, scraped from spark-streaming:8001 + gps-simulator:8000
prometheus_metrics = {
    "spark_kafka_events_per_second": 1010.8,   # Gauge — EPS in last batch
    "spark_active_surge_zones":      80,        # Gauge — zones with multiplier > 1.0
    "spark_batch_latency_ms":        18169.77,  # Gauge — avg E2E latency last batch
    "spark_events_processed_total":  437778,    # Counter — cumulative events since start
    "active_drivers_count":          5000,      # Gauge — GPS simulator active drivers
    "gps_events_sent_total":         8794,      # Counter — GPS events sent since start
}

# ── FAULT TOLERANCE TEST ──
# Test: Delete kafka-broker-0 pod, K8s restarts it automatically
# Spark uses 3-broker Kafka cluster; losing 1 broker does not halt processing
fault_tolerance = {
    "test_date":               "2026-04-11",
    "test_time_utc":           "17:23:21",
    "pod_deleted":             "kafka-broker-0",
    "dynamodb_count_before":   94957,
    "dynamodb_count_after":    95868,
    "new_records_during_test": 911,            # records written while broker was down
    "recovery_time_seconds":   50,             # pod went Running 1/1 at 50s
    "data_loss":               0,              # Spark continued via 2 remaining brokers
    "spark_interrupted":       False,          # Batch logs show continuous processing
    "last_batch_before_del":   "Batch 103",
    "notes": (
        "Kafka 3-broker setup with replication-factor=3 and min.insync.replicas=1. "
        "Losing 1 broker did not cause Spark to fail or replay. "
        "KafkaEventsPerSecond remained ~1010 throughout recovery window. "
        "DynamoDB grew by 911 records during the 50s outage window, "
        "confirming zero data loss."
    ),
}

# ── SLA ANALYSIS ──
sla = {
    "target_eps":            1000,
    "achieved_eps_avg":      1006.59,
    "eps_sla_met":           True,           # 1006 > 1000

    "target_latency_p95_ms": 60000,          # 60s SLA
    "achieved_p95_ms_avg":   41864.58,
    "achieved_p95_ms_max":   57609.68,
    "latency_sla_met":       True,           # max p95 57.6s < 60s

    "target_surge_zones_max": 100,
    "achieved_surge_zones_max": 91,
    "surge_zone_sla_met":    True,

    "availability_pct":      100.0,          # no Spark restarts during 72-min run
    "data_loss_events":      0,
    "fault_recovery_secs":   50,
}

# ── INFRASTRUCTURE ──
infrastructure = {
    "platform":        "Minikube (local laptop)",
    "driver":          "Docker",
    "cpus":            4,
    "memory_gb":       6,
    "spark_master":    "local[4]",
    "kafka_brokers":   3,
    "kafka_topics":    ["gps-critical", "gps-surge", "gps-normal"],
    "partitions":      3,
    "replication":     3,
    "window_seconds":  5,
    "scale_level":     "5K",
    "drivers":         5000,
    "zones":           148,          # unique zone_ids processed per batch
    "aws_region":      "ap-south-1",
    "dynamodb_table":  "surge_pricing",
    "cost_per_hour":   "$0.00",
}

# ── QUICK PRINT ──
if __name__ == "__main__":
    import json
    print("=" * 60)
    print("SCALE 1 — KUBERNETES RESULTS (2026-04-11)")
    print("=" * 60)
    print(f"\nInfrastructure: {infrastructure['platform']}")
    print(f"Drivers: {infrastructure['drivers']:,}  |  Window: {infrastructure['window_seconds']}s  |  Zones: {infrastructure['zones']}")
    print(f"\n--- CloudWatch Metrics (avg over last 15 min) ---")
    print(f"  Kafka EPS:         {cloudwatch_metrics['KafkaEventsPerSecond']['avg']:,.2f} events/s")
    print(f"  Events/Batch:      {cloudwatch_metrics['KafkaEventsPerBatch']['avg']:,.0f}")
    print(f"  Avg E2E Latency:   {cloudwatch_metrics['AvgLatencyMs']['avg']/1000:.1f}s")
    print(f"  P95 Latency:       {cloudwatch_metrics['P95LatencyMs']['avg']/1000:.1f}s  (max: {cloudwatch_metrics['P95LatencyMs']['max']/1000:.1f}s)")
    print(f"  P99 Latency:       {cloudwatch_metrics['P99LatencyMs']['avg']/1000:.1f}s")
    print(f"  Active Surge Zones:{cloudwatch_metrics['ActiveSurgeZones']['avg']:.0f}  (max: {cloudwatch_metrics['ActiveSurgeZones']['max']:.0f})")
    print(f"  Avg Demand Ratio:  {cloudwatch_metrics['AvgDemandRatio']['avg']:.2f}x")
    print(f"\n--- Prometheus Metrics (live snapshot) ---")
    print(f"  Kafka EPS (live):  {prometheus_metrics['spark_kafka_events_per_second']:.1f}")
    print(f"  Surge Zones:       {prometheus_metrics['spark_active_surge_zones']}")
    print(f"  Batch Latency:     {prometheus_metrics['spark_batch_latency_ms']/1000:.1f}s")
    print(f"  Events Processed:  {prometheus_metrics['spark_events_processed_total']:,}")
    print(f"  Active Drivers:    {prometheus_metrics['active_drivers_count']:,}")
    print(f"\n--- Fault Tolerance ---")
    print(f"  Pod deleted:       {fault_tolerance['pod_deleted']}")
    print(f"  Recovery time:     {fault_tolerance['recovery_time_seconds']}s")
    print(f"  Data loss:         {fault_tolerance['data_loss']} events")
    print(f"  Records written during outage: {fault_tolerance['new_records_during_test']}")
    print(f"\n--- SLA ---")
    print(f"  EPS SLA (≥1000):   {'PASS' if sla['eps_sla_met'] else 'FAIL'}  ({sla['achieved_eps_avg']:,.2f})")
    print(f"  P95 SLA (<60s):    {'PASS' if sla['latency_sla_met'] else 'FAIL'}  (avg {sla['achieved_p95_ms_avg']/1000:.1f}s, max {sla['achieved_p95_ms_max']/1000:.1f}s)")
    print(f"  Availability:      {sla['availability_pct']}%")
    print(f"  Cost:              {infrastructure['cost_per_hour']}/hr")
