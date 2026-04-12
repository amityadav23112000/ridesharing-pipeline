"""
Scale 1 — Kubernetes Results (Minikube on AWS EC2 t3.xlarge)
Date: 2026-04-12
Infrastructure: AWS EC2 t3.xlarge (4 vCPU, 16 GB RAM) + Minikube
Drivers: 5,000  (same workload as Scale1-Laptop, but on EC2 hardware)
Orchestration: Kubernetes (minikube on EC2)
Window: 5 seconds
Kafka: 3-broker cluster (3 partitions, replication-factor 3)
Topics: gps-critical, gps-surge, gps-normal
DynamoDB: surge_pricing table (PAY_PER_REQUEST)
Purpose: Fair hardware comparison — Scale 1 workload on same EC2 hardware as Scale 2
Cost: $0.1664/hr (t3.xlarge on-demand ap-south-1)

Procedure: Switched NUM_DRIVERS from 50000→5000 on running EC2 cluster,
           waited 8 minutes for metrics to stabilize, then collected data.
"""

# ── CLOUDWATCH METRICS (last 10 min, 300s period) ──
# Collected: 2026-04-12 ~05:25 UTC, Scale=5K, Namespace=RidesharingPipeline
cloudwatch_metrics = {
    "KafkaEventsPerSecond": {
        "avg": 1021.90,
        "max": 1983.60,
        "min": 975.60,
        "unit": "Count/Second",
        "samples": 2,
    },
    "KafkaEventsPerBatch": {
        "avg": 5109.50,
        "max": 9918.00,
        "min": 4878.00,
        "unit": "Count",
        "samples": 2,
    },
    "AvgLatencyMs": {
        "avg": 6882.35,
        "max": 11348.16,
        "min": 5180.59,
        "unit": "Milliseconds",
        "samples": 2,
    },
    "P95LatencyMs": {
        "avg": 7285.18,
        "max": 11646.51,
        "min": 5496.09,
        "unit": "Milliseconds",
        "samples": 2,
    },
    "ActiveSurgeZones": {
        "avg": 49.09,
        "max": 61.00,
        "min": 34.00,
        "unit": "Count",
        "samples": 2,
    },
    "TotalWaitingRiders": {
        "avg": 2557.35,
        "max": 4927.00,
        "min": 2413.00,
        "unit": "Count",
        "samples": 2,
    },
    "AvgDemandRatio": {
        "avg": 1.25,
        "max": 1.33,
        "min": 1.16,
        "unit": "None",
        "samples": 2,
    },
    "WindowSizeSeconds": {
        "avg": 5.0,
        "max": 5.0,
        "min": 5.0,
        "unit": "Seconds",
        "samples": 2,
    },
    "ZonesProcessedPerBatch": {
        "avg": 148.0,
        "max": 148.0,
        "min": 148.0,
        "unit": "Count",
        "samples": 2,
    },
}

# ── PROMETHEUS METRICS (live snapshot at ~05:25 UTC) ──
# Source: Prometheus NodePort 30090, scraped from spark-streaming:8001 + gps-simulator:8000
prometheus_metrics = {
    "spark_kafka_events_per_second": 1000.0,   # Gauge — EPS in last batch
    "spark_active_surge_zones":      52.0,     # Gauge — zones with multiplier > 1.0
    "spark_batch_latency_ms":        6502.46,  # Gauge — avg E2E latency last batch
    "active_drivers_count":          5000.0,   # Gauge — GPS simulator active drivers
}

# ── SLA ANALYSIS ──
sla = {
    "target_eps":            1000,
    "achieved_eps_avg":      1021.90,
    "eps_sla_met":           True,           # 1022 > 1000

    "target_latency_p95_ms": 60000,          # 60s SLA
    "achieved_p95_ms_avg":   7285.18,
    "achieved_p95_ms_max":   11646.51,
    "latency_sla_met":       True,           # max p95 11.6s << 60s

    "target_surge_zones_max": 100,
    "achieved_surge_zones_max": 61,
    "surge_zone_sla_met":    True,

    "availability_pct":      100.0,
    "data_loss_events":      0,
}

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
    "partitions":      3,
    "replication":     3,
    "window_seconds":  5,
    "scale_level":     "5K",
    "drivers":         5000,
    "zones":           148,
    "aws_region":      "ap-south-1",
    "dynamodb_table":  "surge_pricing",
    "cost_per_hour":   "$0.1664",            # t3.xlarge on-demand ap-south-1
}

# ── QUICK PRINT ──
if __name__ == "__main__":
    print("=" * 65)
    print("SCALE 1 — EC2 RESULTS (2026-04-12)")
    print("=" * 65)
    print(f"\nInfrastructure: {infrastructure['platform']}")
    print(f"Drivers: {infrastructure['drivers']:,}  |  Window: {infrastructure['window_seconds']}s  |  Zones: {infrastructure['zones']}")
    print(f"\n--- CloudWatch Metrics (avg over last 10 min) ---")
    print(f"  Kafka EPS:         {cloudwatch_metrics['KafkaEventsPerSecond']['avg']:,.2f} events/s")
    print(f"  Events/Batch:      {cloudwatch_metrics['KafkaEventsPerBatch']['avg']:,.0f}")
    print(f"  Avg E2E Latency:   {cloudwatch_metrics['AvgLatencyMs']['avg']/1000:.2f}s")
    print(f"  P95 Latency:       {cloudwatch_metrics['P95LatencyMs']['avg']/1000:.2f}s  (max: {cloudwatch_metrics['P95LatencyMs']['max']/1000:.2f}s)")
    print(f"  Active Surge Zones:{cloudwatch_metrics['ActiveSurgeZones']['avg']:.0f}  (max: {cloudwatch_metrics['ActiveSurgeZones']['max']:.0f})")
    print(f"  Avg Demand Ratio:  {cloudwatch_metrics['AvgDemandRatio']['avg']:.2f}x")
    print(f"\n--- Prometheus Metrics (live snapshot) ---")
    print(f"  Kafka EPS (live):  {prometheus_metrics['spark_kafka_events_per_second']:.1f}")
    print(f"  Surge Zones:       {prometheus_metrics['spark_active_surge_zones']:.0f}")
    print(f"  Batch Latency:     {prometheus_metrics['spark_batch_latency_ms']/1000:.2f}s")
    print(f"  Active Drivers:    {prometheus_metrics['active_drivers_count']:.0f}")
    print(f"\n--- SLA ---")
    print(f"  EPS SLA (≥1000):   {'PASS' if sla['eps_sla_met'] else 'FAIL'}  ({sla['achieved_eps_avg']:,.2f})")
    print(f"  P95 SLA (<60s):    {'PASS' if sla['latency_sla_met'] else 'FAIL'}  (avg {sla['achieved_p95_ms_avg']/1000:.2f}s, max {sla['achieved_p95_ms_max']/1000:.2f}s)")
    print(f"  Availability:      {sla['availability_pct']}%")
    print(f"  Cost:              {infrastructure['cost_per_hour']}/hr")
