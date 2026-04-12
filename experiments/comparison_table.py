"""
Ridesharing Pipeline — Scale Comparison Table
Experiments: Scale1-Laptop vs Scale1-EC2 vs Scale2-EC2
Generated: 2026-04-12

Purpose: Fair hardware comparison
  - Scale1-Laptop: 5K drivers on local Minikube (4 CPU, 6 GB RAM)
  - Scale1-EC2:    5K drivers on EC2 t3.xlarge (4 vCPU, 16 GB RAM)  ← same hardware as Scale2
  - Scale2-EC2:   50K drivers on EC2 t3.xlarge (4 vCPU, 16 GB RAM)
"""

# ── DATA ──────────────────────────────────────────────────────────────────────

experiments = {
    "Scale1-Laptop": {
        "label":           "Scale 1 — Laptop",
        "date":            "2026-04-11",
        "platform":        "Minikube (local laptop)",
        "instance":        "Laptop",
        "vcpus":           4,
        "ram_gb":          6,
        "drivers":         5_000,
        "kafka_eps_avg":   1006.59,
        "events_per_batch":5032.96,
        "latency_avg_ms":  31039.84,
        "latency_p95_ms":  41864.58,
        "latency_p95_max": 57609.68,
        "surge_zones_avg": 75.0,
        "surge_zones_max": 91.0,
        "demand_ratio":    1.48,
        "waiting_riders":  2720.43,
        "zones_per_batch": 148.0,
        "window_sec":      5,
        "cost_per_hr":     0.00,
        "eps_sla_pass":    True,
        "p95_sla_pass":    True,   # max p95 57.6s < 60s SLA
    },
    "Scale1-EC2": {
        "label":           "Scale 1 — EC2",
        "date":            "2026-04-12",
        "platform":        "Minikube on AWS EC2 t3.xlarge",
        "instance":        "t3.xlarge",
        "vcpus":           4,
        "ram_gb":          16,
        "drivers":         5_000,
        "kafka_eps_avg":   1021.90,
        "events_per_batch":5109.50,
        "latency_avg_ms":  6882.35,
        "latency_p95_ms":  7285.18,
        "latency_p95_max": 11646.51,
        "surge_zones_avg": 49.09,
        "surge_zones_max": 61.0,
        "demand_ratio":    1.25,
        "waiting_riders":  2557.35,
        "zones_per_batch": 148.0,
        "window_sec":      5,
        "cost_per_hr":     0.1664,
        "eps_sla_pass":    True,
        "p95_sla_pass":    True,   # max p95 11.6s << 60s SLA
    },
    "Scale2-EC2": {
        "label":           "Scale 2 — EC2",
        "date":            "2026-04-12",
        "platform":        "Minikube on AWS EC2 t3.xlarge",
        "instance":        "t3.xlarge",
        "vcpus":           4,
        "ram_gb":          16,
        "drivers":         50_000,
        "kafka_eps_avg":   3077.76,
        "events_per_batch":15388.78,
        "latency_avg_ms":  125469.40,
        "latency_p95_ms":  126880.67,
        "latency_p95_max": 312243.30,
        "surge_zones_avg": 32.77,
        "surge_zones_max": 67.0,
        "demand_ratio":    1.25,
        "waiting_riders":  7694.32,
        "zones_per_batch": 144.11,
        "window_sec":      5,
        "cost_per_hr":     0.1664,
        "eps_sla_pass":    True,
        "p95_sla_pass":    False,  # 125s avg >> 60s SLA (single-node backpressure)
    },
}

# ── DERIVED RATIOS ─────────────────────────────────────────────────────────────

s1l  = experiments["Scale1-Laptop"]
s1ec = experiments["Scale1-EC2"]
s2ec = experiments["Scale2-EC2"]

latency_improvement_ec2_vs_laptop = round(s1l["latency_avg_ms"] / s1ec["latency_avg_ms"], 1)
latency_improvement_p95_ec2_vs_laptop = round(s1l["latency_p95_ms"] / s1ec["latency_p95_ms"], 1)
eps_scale_factor = round(s2ec["kafka_eps_avg"] / s1ec["kafka_eps_avg"], 1)
driver_scale_factor = s2ec["drivers"] // s1ec["drivers"]
latency_penalty_scale2_vs_scale1ec2 = round(s2ec["latency_avg_ms"] / s1ec["latency_avg_ms"], 1)


# ── PRINT ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    W = 72

    def hr(char="─"):
        print(char * W)

    def row(label, s1l_val, s1ec_val, s2ec_val, fmt="{}", width=18):
        c1 = fmt.format(s1l_val).rjust(width)
        c2 = fmt.format(s1ec_val).rjust(width)
        c3 = fmt.format(s2ec_val).rjust(width)
        print(f"  {label:<22}{c1}{c2}{c3}")

    print()
    hr("═")
    print("  RIDESHARING PIPELINE — SCALE COMPARISON")
    hr("═")
    print(f"  {'Metric':<22}{'Scale1-Laptop':>18}{'Scale1-EC2':>18}{'Scale2-EC2':>18}")
    hr()

    print("  INFRASTRUCTURE")
    row("Platform",      "Minikube/Local", "EC2 t3.xlarge", "EC2 t3.xlarge")
    row("vCPUs",         s1l["vcpus"],     s1ec["vcpus"],   s2ec["vcpus"],   fmt="{}")
    row("RAM (GB)",      s1l["ram_gb"],    s1ec["ram_gb"],  s2ec["ram_gb"],  fmt="{}")
    row("Drivers",       f"{s1l['drivers']:,}", f"{s1ec['drivers']:,}", f"{s2ec['drivers']:,}")
    row("Cost ($/hr)",   f"${s1l['cost_per_hr']:.4f}",
                         f"${s1ec['cost_per_hr']:.4f}",
                         f"${s2ec['cost_per_hr']:.4f}")

    hr()
    print("  THROUGHPUT")
    row("Kafka EPS (avg)", f"{s1l['kafka_eps_avg']:.1f}",
                           f"{s1ec['kafka_eps_avg']:.1f}",
                           f"{s2ec['kafka_eps_avg']:.1f}")
    row("Events/Batch",  f"{s1l['events_per_batch']:,.0f}",
                         f"{s1ec['events_per_batch']:,.0f}",
                         f"{s2ec['events_per_batch']:,.0f}")
    row("EPS SLA (≥1000)", "PASS" if s1l["eps_sla_pass"] else "FAIL",
                            "PASS" if s1ec["eps_sla_pass"] else "FAIL",
                            "PASS" if s2ec["eps_sla_pass"] else "FAIL")

    hr()
    print("  LATENCY")
    row("Avg E2E (s)",   f"{s1l['latency_avg_ms']/1000:.2f}",
                         f"{s1ec['latency_avg_ms']/1000:.2f}",
                         f"{s2ec['latency_avg_ms']/1000:.2f}")
    row("P95 avg (s)",   f"{s1l['latency_p95_ms']/1000:.2f}",
                         f"{s1ec['latency_p95_ms']/1000:.2f}",
                         f"{s2ec['latency_p95_ms']/1000:.2f}")
    row("P95 max (s)",   f"{s1l['latency_p95_max']/1000:.2f}",
                         f"{s1ec['latency_p95_max']/1000:.2f}",
                         f"{s2ec['latency_p95_max']/1000:.2f}")
    row("P95 SLA (<60s)","PASS" if s1l["p95_sla_pass"] else "FAIL",
                         "PASS" if s1ec["p95_sla_pass"] else "FAIL",
                         "PASS" if s2ec["p95_sla_pass"] else "FAIL")

    hr()
    print("  SURGE DETECTION")
    row("Surge Zones avg",f"{s1l['surge_zones_avg']:.0f}",
                          f"{s1ec['surge_zones_avg']:.0f}",
                          f"{s2ec['surge_zones_avg']:.0f}")
    row("Surge Zones max",f"{s1l['surge_zones_max']:.0f}",
                          f"{s1ec['surge_zones_max']:.0f}",
                          f"{s2ec['surge_zones_max']:.0f}")
    row("Demand Ratio",   f"{s1l['demand_ratio']:.2f}x",
                          f"{s1ec['demand_ratio']:.2f}x",
                          f"{s2ec['demand_ratio']:.2f}x")
    row("Waiting Riders", f"{s1l['waiting_riders']:,.0f}",
                          f"{s1ec['waiting_riders']:,.0f}",
                          f"{s2ec['waiting_riders']:,.0f}")
    row("Zones/Batch",    f"{s1l['zones_per_batch']:.0f}",
                          f"{s1ec['zones_per_batch']:.0f}",
                          f"{s2ec['zones_per_batch']:.1f}")

    hr("═")
    print("  KEY INSIGHTS")
    hr("═")
    print(f"""
  1. EC2 vs Laptop (same 5K workload):
       Avg latency  : {s1l['latency_avg_ms']/1000:.1f}s → {s1ec['latency_avg_ms']/1000:.2f}s  ({latency_improvement_ec2_vs_laptop}× faster)
       P95 latency  : {s1l['latency_p95_ms']/1000:.1f}s → {s1ec['latency_p95_ms']/1000:.2f}s  ({latency_improvement_p95_ec2_vs_laptop}× faster)
       Reason       : EC2 t3.xlarge has 16 GB RAM vs laptop's 6 GB; Minikube
                      avoids memory pressure / swapping, keeping Spark batches tight.

  2. Scale 2 vs Scale 1 (both EC2):
       Drivers      : {s1ec['drivers']:,} → {s2ec['drivers']:,}  ({driver_scale_factor}× more drivers)
       EPS           : {s1ec['kafka_eps_avg']:.0f} → {s2ec['kafka_eps_avg']:.0f}  ({eps_scale_factor}× more events/s)
       Avg latency  : {s1ec['latency_avg_ms']/1000:.2f}s → {s2ec['latency_avg_ms']/1000:.1f}s  ({latency_penalty_scale2_vs_scale1ec2}× higher)
       Reason       : 10× more drivers produce {eps_scale_factor}× EPS; Spark local[4] saturates
                      at 50K — batches lag behind the 5s window, queue builds up.
                      Fix: distributed EKS cluster with multiple Spark executors.

  3. EPS SLA (≥1000 events/s): ALL PASS
     P95 Latency SLA (<60s):   Scale1-Laptop PASS | Scale1-EC2 PASS | Scale2-EC2 FAIL
""")
    hr("═")
    print(f"  Collected: 2026-04-12 | Region: ap-south-1 | Kafka: 3-broker | Window: 5s")
    hr("═")
    print()
