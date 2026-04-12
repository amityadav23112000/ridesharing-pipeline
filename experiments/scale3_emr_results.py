"""
Scale 3 — EMR Distributed Spark Results (AWS EMR on m5.xlarge × 3)
Date: 2026-04-12
Infrastructure: AWS EMR 6.15.0 (Spark 3.4.1-amzn-2 on YARN)
Cluster: 1 × master m5.xlarge + 2 × core m5.xlarge = 3 nodes total
Total: 12 vCPU, 48 GB RAM
Drivers: 50,000  (10 cities × 5,000 drivers each)
Spark config: --num-executors 4 --executor-cores 2 --executor-memory 3g
              --packages spark-sql-kafka-0-10_2.12:3.4.0
              --conf spark.sql.shuffle.partitions=20
Deploy mode: YARN client (driver on master node)
Kafka: 3-broker cluster on EC2 t3.xlarge (3.110.170.240:9092-9094 via socat proxy)
Topics: gps-critical, gps-surge, gps-normal
DynamoDB: surge_pricing table (PAY_PER_REQUEST)
Run duration: ~11 minutes (08:35 – 08:46 UTC), 136 batches processed
Cluster ID: j-B38XSUW8NW4V

Cost breakdown:
  3 × m5.xlarge EC2 on-demand (ap-south-1): ~$0.226/hr × 3 = $0.678/hr
  EMR surcharge (Spark): ~$0.048/vCPU-hr × 12 vCPU = $0.576/hr
  Total: ~$1.25/hr  (cluster ran ~30 min including provisioning = ~$0.63)

Key finding vs Scale2-EC2:
  EMR starts fast (Batch 0: 24s latency) but consumer lag accumulates.
  Kafka consumer throughput is higher (4125 vs 3077 EPS) yet latency
  grows faster because GPS simulator outruns even the YARN cluster.
  Root cause: GPS rate (~4000 EPS) ≈ EMR processing rate — no headroom.
  In a real EKS cluster with more partitions, EMR would scale further.
"""

# ── CLOUDWATCH METRICS (last 15 min, 2 data points / 300s period) ──
# Collected: 2026-04-12 ~08:47 UTC, Scale=50K, Namespace=RidesharingPipeline
# Window: 08:34–08:47 UTC (EMR step active)
cloudwatch_metrics = {
    "KafkaEventsPerSecond": {
        "avg": 4125.27,
        "max": 6300.00,
        "min": 2365.80,
        "unit": "Count/Second",
        "samples": 2,
    },
    "KafkaEventsPerBatch": {
        "avg": 20626.35,
        "max": 31500.00,
        "min": 11829.00,
        "unit": "Count",
        "samples": 2,
    },
    "AvgLatencyMs": {
        "avg": 201198.79,
        "max": 348755.32,
        "min": 37401.51,
        "unit": "Milliseconds",
        "samples": 2,
    },
    "P95LatencyMs": {
        "avg": 205431.40,
        "max": 356889.73,
        "min": 39964.20,
        "unit": "Milliseconds",
        "samples": 2,
    },
    "P99LatencyMs": {
        "avg": 205780.01,
        "max": 357107.08,
        "min": 40025.65,
        "unit": "Milliseconds",
        "samples": 2,
    },
    "ActiveSurgeZones": {
        "avg": 29.43,
        "max": 45.00,
        "min": 17.00,
        "unit": "Count",
        "samples": 2,
    },
    "TotalWaitingRiders": {
        "avg": 10356.55,
        "max": 15680.00,
        "min": 5849.00,
        "unit": "Count",
        "samples": 2,
    },
    "AvgDemandRatio": {
        "avg": 1.26,
        "max": 1.31,
        "min": 1.20,
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
        "avg": 147.77,
        "max": 148.00,
        "min": 138.00,
        "unit": "Count",
        "samples": 2,
    },
}

# ── SPARK BATCH LOG SUMMARY (from /mnt/var/log/hadoop/steps/s-01812713EHHFC5MU6JKH/stdout) ──
batch_log_summary = {
    "total_batches":        136,
    "run_duration_min":     11,
    "batch_0_latency_ms":   24094,    # Fast start: GPS ran 4 min before EMR started
    "batch_40_latency_ms":  128605,   # At 5 min mark
    "batch_134_latency_ms": 371700,   # At 10 min mark
    "batch_0_surge_zones":  62,
    "batch_0_kafka_eps":    305.6,    # Warm-up: consuming accumulated backlog
    "peak_kafka_eps":       5678.6,   # At batch ~5 (burst to clear backlog)
    "steady_kafka_eps":     4000,     # Steady state ~4000 EPS
    "latency_trend":        "linear_growth",
    "latency_start_ms":     24094,
    "latency_end_ms":       368389,
    "notes": (
        "EMR Spark on YARN started with low latency (24s) since GPS simulator "
        "had been running 4 minutes pre-EMR. Burst of ~5678 EPS to clear backlog. "
        "Latency grew linearly from 24s→368s over 11 min because GPS produces "
        "~3500-4000 EPS ≈ EMR processing rate — no sustained headroom. "
        "Scale2-EC2 started at 125s avg (already behind when measured), while "
        "Scale3-EMR started at 24s showing distributed Spark's initial advantage."
    ),
}

# ── SLA ANALYSIS ──
sla = {
    "target_eps":            1000,
    "achieved_eps_avg":      4125.27,
    "eps_sla_met":           True,             # 4125 >> 1000 (4× more than SLA)

    "target_latency_p95_ms": 60000,            # 60s SLA
    "achieved_p95_ms_avg":   205431.40,
    "achieved_p95_ms_max":   356889.73,
    "achieved_p95_ms_min":   39964.20,         # Early batches well under SLA
    "latency_sla_met":       False,            # avg exceeds 60s SLA (consumer lag)
    "latency_notes": (
        "P95 latency averaged 205s (> 60s SLA) over the 11-minute run. "
        "However, the first ~2 minutes (batches 0–20) met the SLA with latency < 60s. "
        "Latency exceeds SLA because GPS event rate (~3500-4000 EPS) approaches "
        "EMR's processing capacity, causing progressive consumer lag. "
        "With more Kafka partitions and more EMR executors this would not occur."
    ),

    "target_surge_zones_max": 100,
    "achieved_surge_zones_max": 45,
    "surge_zone_sla_met":    True,

    "availability_pct":      100.0,
    "data_loss_events":      0,
}

# ── INFRASTRUCTURE ──
infrastructure = {
    "platform":          "AWS EMR 6.15.0 (Spark on YARN)",
    "emr_release":       "emr-6.15.0",
    "spark_version":     "3.4.1-amzn-2",
    "master_instance":   "m5.xlarge",
    "core_instances":    2,
    "core_instance":     "m5.xlarge",
    "total_nodes":       3,
    "total_vcpus":       12,          # 4 vCPU × 3 nodes
    "total_ram_gb":      48,          # 16 GB × 3 nodes
    "spark_master":      "yarn",
    "deploy_mode":       "client",
    "num_executors":     4,
    "executor_cores":    2,
    "executor_memory":   "3g",
    "driver_memory":     "2g",
    "kafka_brokers":     3,
    "kafka_topics":      ["gps-critical", "gps-surge", "gps-normal"],
    "partitions":        10,
    "replication":       3,
    "window_seconds":    5,
    "scale_level":       "50K",
    "drivers":           50000,
    "cities":            10,
    "drivers_per_city":  5000,
    "zones":             148,
    "aws_region":        "ap-south-1",
    "dynamodb_table":    "surge_pricing",
    "cluster_id":        "j-B38XSUW8NW4V",
    "cost_per_hour_ec2": "$0.678",    # 3 × m5.xlarge on-demand
    "cost_per_hour_emr": "$0.576",    # EMR surcharge (12 vCPU × $0.048)
    "cost_per_hour":     "~$1.25",
    "kafka_access":      "socat TCP proxy on EC2 host (9092-9094 → minikube NodePorts)",
}

# ── QUICK PRINT ──
if __name__ == "__main__":
    print("=" * 70)
    print("SCALE 3 — EMR DISTRIBUTED SPARK RESULTS (2026-04-12)")
    print("=" * 70)
    print(f"\nPlatform: {infrastructure['platform']}")
    print(f"Cluster:  1 master + {infrastructure['core_instances']} core × {infrastructure['master_instance']}")
    print(f"Total:    {infrastructure['total_vcpus']} vCPU, {infrastructure['total_ram_gb']} GB RAM")
    print(f"Drivers:  {infrastructure['drivers']:,}  |  Cities: {infrastructure['cities']}")
    print(f"Window:   {infrastructure['window_seconds']}s  |  Executors: {infrastructure['num_executors']} × {infrastructure['executor_cores']} cores")
    print(f"\n--- CloudWatch Metrics (avg over last 15 min) ---")
    print(f"  Kafka EPS:         {cloudwatch_metrics['KafkaEventsPerSecond']['avg']:,.2f} events/s  (max: {cloudwatch_metrics['KafkaEventsPerSecond']['max']:,.0f})")
    print(f"  Events/Batch:      {cloudwatch_metrics['KafkaEventsPerBatch']['avg']:,.0f}")
    print(f"  Avg E2E Latency:   {cloudwatch_metrics['AvgLatencyMs']['avg']/1000:.1f}s  (min: {cloudwatch_metrics['AvgLatencyMs']['min']/1000:.1f}s)")
    print(f"  P95 Latency:       {cloudwatch_metrics['P95LatencyMs']['avg']/1000:.1f}s  (max: {cloudwatch_metrics['P95LatencyMs']['max']/1000:.1f}s)")
    print(f"  Active Surge Zones:{cloudwatch_metrics['ActiveSurgeZones']['avg']:.0f}  (max: {cloudwatch_metrics['ActiveSurgeZones']['max']:.0f})")
    print(f"  Avg Demand Ratio:  {cloudwatch_metrics['AvgDemandRatio']['avg']:.2f}x")
    print(f"\n--- Batch Log Summary (from YARN step logs) ---")
    print(f"  Total batches:     {batch_log_summary['total_batches']}")
    print(f"  Latency at start:  {batch_log_summary['latency_start_ms']/1000:.1f}s  (Batch 0 — fast initial consumption)")
    print(f"  Latency at 5 min:  {batch_log_summary['batch_40_latency_ms']/1000:.1f}s  (Batch ~40)")
    print(f"  Latency at 10 min: {batch_log_summary['batch_134_latency_ms']/1000:.1f}s  (Batch ~134)")
    print(f"  Peak EPS:          {batch_log_summary['peak_kafka_eps']:,.1f}  (burst clearing initial backlog)")
    print(f"\n--- SLA ---")
    print(f"  EPS SLA (≥1000):   {'PASS' if sla['eps_sla_met'] else 'FAIL'}  ({sla['achieved_eps_avg']:,.2f})")
    print(f"  P95 SLA (<60s):    {'PASS' if sla['latency_sla_met'] else 'FAIL'}  (avg {sla['achieved_p95_ms_avg']/1000:.1f}s, min {sla['achieved_p95_ms_min']/1000:.1f}s)")
    print(f"  Availability:      {sla['availability_pct']}%")
    print(f"  Cost:              {infrastructure['cost_per_hour']}/hr")
    print(f"\n  EMR advantage: Initial latency 24s vs Scale2-EC2's 125s avg")
    print(f"  EMR advantage: Peak EPS 5678 vs Scale2-EC2's peak 4504")
    print(f"  EMR limitation: Latency grows as GPS rate ≈ processing capacity")
