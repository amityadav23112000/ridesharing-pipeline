# Scale 1 Experiment Results
# Date: 2026-04-07
# Infrastructure: Local Ubuntu laptop (11GB RAM, 8 cores)
# Drivers: 5,000 across 10 Indian cities

SCALE1_RESULTS = {
    "experiment":                "Scale 1 - City Level",
    "date":                      "2026-04-07",
    "infrastructure":            "Local Ubuntu 24.04, 11GB RAM, 8 cores",
    "drivers":                   5000,
    "cities":                    10,
    "drivers_per_city":          500,
    "events_per_minute":         1400,
    "events_per_second":         23,
    "avg_latency_ms":            9500,
    "min_latency_ms":            2552,
    "max_latency_ms":            13083,
    "window_size_sec":           10,
    "flush_time_ms":             100,
    "brokers":                   3,
    "partitions_per_topic":      10,
    "replication_factor":        3,
    "total_surge_records":       4628,
    "max_surge_multiplier":      3.0,
    "window_switched":           "30s -> 10s at 1770 ev/min",
    "infrastructure_cost_usd":   0.0,
    "cost_per_million_events":   0.0,
}

if __name__ == "__main__":
    print("=" * 55)
    print("SCALE 1 EXPERIMENT RESULTS")
    print("=" * 55)
    for k, v in SCALE1_RESULTS.items():
        print(f"  {k:<35} {v}")
    print("=" * 55)
