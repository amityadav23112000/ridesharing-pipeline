# Scale 1 Experiment Results
# Date: 2026-04-11
# Infrastructure: Local laptop (Ubuntu 24.04, 11GB RAM, 8 cores)
# Simulator: localhost Kafka
# Processor: Spark local[4] on laptop

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
    "kafka_eps_max":             819.0,

    # Demand metrics
    "avg_waiting_riders":        1935.0,
    "avg_demand_ratio":          1.312,
    "avg_surge_zones":           55.0,
    "min_surge_zones":           48.0,
    "max_surge_zones":           60.0,

    # Window
    "window_size_sec":           5,

    # Infrastructure
    "spark_master":              "local[4]",
    "spark_driver_memory":       "2g",
    "kafka_brokers":             3,
    "kafka_partitions":          10,
    "replication_factor":        3,
    "infrastructure_cost":       0.0,
}

if __name__ == "__main__":
    print("=" * 55)
    print("SCALE 1 RESULTS — 5K DRIVERS ON LAPTOP")
    print("=" * 55)
    for k, v in SCALE1_RESULTS.items():
        print(f"  {k:<35} {v}")
    print("=" * 55)
