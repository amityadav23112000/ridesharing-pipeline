# Fault Tolerance Test Results
# Date: 2026-04-09
# Test: Kill Kafka broker-1 during live pipeline

FAULT_TOLERANCE_RESULTS = {
    "test":                  "Kafka Broker Failure",
    "date":                  "2026-04-09",
    "kafka_brokers_total":   3,
    "broker_killed":         "kafka-broker-1",
    "replication_factor":    3,

    # Results
    "records_before_kill":   5068,
    "records_after_60s":     5068,
    "events_lost":           0,
    "data_loss":             "ZERO",

    # Recovery
    "kill_time":             "15:22:40 IST",
    "restart_time":          "15:23:45 IST",
    "recovery_time_seconds": 65,

    # What happened
    "pipeline_behavior":     "Continued without interruption",
    "broker_2_took_over":    True,
    "broker_3_took_over":    True,
    "manual_intervention":   False,

    # Conclusion
    "conclusion": """
    Kafka replication factor=3 proved fault tolerant.
    Killing 1 of 3 brokers caused ZERO data loss.
    Pipeline recovered automatically in 65 seconds.
    Brokers 2 and 3 continued serving all partitions.
    This satisfies the 99.9% uptime SLA requirement.
    """
}

if __name__ == "__main__":
    print("=" * 55)
    print("FAULT TOLERANCE TEST RESULTS")
    print("=" * 55)
    for k, v in FAULT_TOLERANCE_RESULTS.items():
        if k != 'conclusion':
            print(f"  {k:<35} {v}")
    print(f"\nCONCLUSION:{FAULT_TOLERANCE_RESULTS['conclusion']}")
    print("=" * 55)
