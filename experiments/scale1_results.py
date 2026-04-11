# Scale 1 Experiment Results
# Date: 2026-04-11
# Infrastructure: Local laptop (Ubuntu 24.04, 11GB RAM, 8 cores)

SCALE1_RESULTS = {
    "experiment":                "Scale 1 - City Level",
    "date":                      "2026-04-11",
    "infrastructure":            "Local laptop Ubuntu 24.04",
    "drivers":                   5000,
    "cities":                    10,
    "drivers_per_city":          500,

    # Kafka ingestion
    "kafka_eps_avg":             757.0,
    "kafka_eps_min":             598.0,
    "kafka_eps_max":             1000.0,

    # REAL end-to-end latency (event created → DynamoDB written)
    "avg_latency_ms":            11085.0,
    "p95_latency_ms":            14109.0,
    "min_latency_ms":            9255.0,
    "max_latency_ms":            16814.0,
    "latency_note":              "Real E2E: GPS event creation to DynamoDB write",
    "sla_target_ms":             10000,
    "sla_met":                   False,
    "sla_note":                  "Avg 11s exceeds 10s SLA — window processing overhead",

    # Demand metrics
    "avg_waiting_riders":        1935.0,
    "avg_demand_ratio":          1.312,
    "avg_surge_zones":           55.0,

    # Window
    "window_size_sec":           5,

    # Infrastructure
    "spark_master":              "local[4]",
    "spark_driver_memory":       "2g",
    "kafka_brokers":             3,
    "replication_factor":        3,
    "infrastructure_cost":       0.0,
}

if __name__ == "__main__":
    print("=" * 60)
    print("SCALE 1 RESULTS — 5K DRIVERS ON LAPTOP")
    print("=" * 60)
    for k, v in SCALE1_RESULTS.items():
        print(f"  {k:<38} {v}")
    print("=" * 60)
    print(f"\nSLA STATUS: {'PASS ✓' if SCALE1_RESULTS['sla_met'] else 'FAIL ✗'}")
    print(f"Avg latency {SCALE1_RESULTS['avg_latency_ms']}ms vs target {SCALE1_RESULTS['sla_target_ms']}ms")
    print("Research finding: Optimize window processing to meet SLA")
    print("=" * 60)
