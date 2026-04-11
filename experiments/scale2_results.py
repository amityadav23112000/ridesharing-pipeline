# Scale 2 Experiment Results
# Date: 2026-04-11
# Infrastructure: AWS EC2 t3.large (8GB RAM, 2 vCPU)

SCALE2_RESULTS = {
    "experiment":                "Scale 2 - Metro Level",
    "date":                      "2026-04-11",
    "infrastructure":            "AWS EC2 t3.large",
    "drivers":                   50000,
    "cities":                    10,
    "drivers_per_city":          5000,
    "kafka_eps_avg":             2754.0,
    "kafka_eps_min":             2461.0,
    "kafka_eps_max":             3342.0,
    "avg_waiting_riders":        7048.0,
    "avg_demand_ratio":          1.263,
    "avg_surge_zones":           38.1,
    "window_size_sec":           5,
    "spark_master":              "local[8]",
    "kafka_brokers":             2,
    "ec2_instance":              "t3.large",
    "ec2_cost_per_hour":         0.0832,
    "scale1_kafka_eps":          500,
    "scale2_kafka_eps":          2754,
    "kafka_throughput_increase": "5.5x",
}

if __name__ == "__main__":
    print("=" * 55)
    print("SCALE 2 RESULTS — 50K DRIVERS ON EC2")
    print("=" * 55)
    for k, v in SCALE2_RESULTS.items():
        print(f"  {k:<35} {v}")
    print("=" * 55)
    print(f"\nKafka throughput increase: {SCALE2_RESULTS['kafka_throughput_increase']}")
    print(f"Avg surge zones: {SCALE2_RESULTS['avg_surge_zones']}")
