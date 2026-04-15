#!/usr/bin/env python3
"""
metrics_collector.py — Scrapes Prometheus endpoints during an experiment run.

Polls GPS simulator (port 8000) and Spark streaming (port 8001) every
--interval-seconds for --duration-seconds total, writing all samples to:
    {output_dir}/{experiment_name}/metrics_{timestamp}.csv

CSV columns: timestamp, experiment_name, source, metric_name, value, labels

Usage:
    python3 src/metrics_collector.py \
        --experiment-name local_sub5s \
        --duration-seconds 180 \
        --output-dir experiments/results/
"""

import argparse
import csv
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

# ── SCRAPE TARGETS ──
SCRAPE_TARGETS = [
    ("http://localhost:8001/metrics", "spark"),       # Spark streaming job
    ("http://localhost:8000/metrics", "simulator"),   # GPS simulator
]

# Only write these metrics to keep CSV compact
METRICS_OF_INTEREST = {
    "spark_batch_latency_ms",
    "spark_kafka_events_per_second",
    "spark_active_surge_zones",
    "spark_events_processed_total",
    "gps_events_sent_total",
    "active_drivers_count",
    "events_per_minute",
}

CSV_FIELDS = ["timestamp", "experiment_name", "source", "metric_name", "value", "labels"]


def _parse_prometheus_text(text):
    """Parse Prometheus text exposition format into list of dicts."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            if "{" in line:
                name_part, rest = line.split("{", 1)
                labels_str, rest = rest.split("}", 1)
                value_str = rest.strip().split()[0]
            else:
                parts = line.split()
                name_part = parts[0]
                value_str = parts[1] if len(parts) > 1 else "0"
                labels_str = ""
            rows.append({
                "metric_name": name_part.strip(),
                "value": float(value_str),
                "labels": labels_str.strip(),
            })
        except (ValueError, IndexError):
            continue
    return rows


def _scrape(url):
    """Scrape one Prometheus endpoint. Returns [] on any error."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "ridesharing-metrics-collector/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return _parse_prometheus_text(resp.read().decode("utf-8"))
    except Exception:
        return []


def collect_sample(experiment_name):
    """Collect one round of samples from all targets. Returns list of row dicts."""
    now = datetime.utcnow().isoformat() + "Z"
    rows = []
    for url, source in SCRAPE_TARGETS:
        for metric in _scrape(url):
            if metric["metric_name"] in METRICS_OF_INTEREST:
                rows.append({
                    "timestamp":       now,
                    "experiment_name": experiment_name,
                    "source":          source,
                    "metric_name":     metric["metric_name"],
                    "value":           metric["value"],
                    "labels":          metric["labels"],
                })
    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Collect real-time metrics during a pipeline experiment"
    )
    parser.add_argument("--experiment-name",   required=True,
                        help="Experiment label (e.g. local_sub5s)")
    parser.add_argument("--duration-seconds",  type=int, required=True,
                        help="Total collection time in seconds")
    parser.add_argument("--output-dir",        default="experiments/results",
                        help="Root directory for result files")
    parser.add_argument("--interval-seconds",  type=int, default=10,
                        help="Scrape interval in seconds (default: 10)")
    args = parser.parse_args()

    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)

    ts_tag   = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"metrics_{ts_tag}.csv")

    print(f"[metrics_collector] experiment   = {args.experiment_name}")
    print(f"[metrics_collector] duration     = {args.duration_seconds}s")
    print(f"[metrics_collector] interval     = {args.interval_seconds}s")
    print(f"[metrics_collector] output       = {out_path}")
    print(f"[metrics_collector] targets      = {[t[0] for t in SCRAPE_TARGETS]}")
    print()

    start      = time.time()
    total_rows = 0
    no_data_streak = 0

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()

        while time.time() - start < args.duration_seconds:
            rows = collect_sample(args.experiment_name)

            if rows:
                writer.writerows(rows)
                f.flush()
                total_rows    += len(rows)
                no_data_streak = 0

                lat_val = next(
                    (r["value"] for r in rows if r["metric_name"] == "spark_batch_latency_ms"),
                    0.0,
                )
                eps_val = next(
                    (r["value"] for r in rows if r["metric_name"] == "spark_kafka_events_per_second"),
                    0.0,
                )
                surge_val = next(
                    (r["value"] for r in rows if r["metric_name"] == "spark_active_surge_zones"),
                    0.0,
                )
                elapsed = int(time.time() - start)
                sla = "PASS" if lat_val < 5000 else "FAIL"
                print(
                    f"  t={elapsed:>4}s | "
                    f"latency={lat_val:>8.0f}ms [{sla}] | "
                    f"eps={eps_val:>7.1f} | "
                    f"surge_zones={surge_val:>4.0f} | "
                    f"rows_written={total_rows}"
                )
            else:
                no_data_streak += 1
                elapsed = int(time.time() - start)
                print(
                    f"  t={elapsed:>4}s | "
                    f"(no data — check Prometheus endpoints are up) "
                    f"[streak={no_data_streak}]"
                )
                if no_data_streak == 3:
                    print("  WARNING: 3 consecutive empty scrapes — "
                          "is the pipeline running?")

            time.sleep(args.interval_seconds)

    elapsed_total = int(time.time() - start)
    print()
    print(f"[metrics_collector] finished — {total_rows} rows in {elapsed_total}s")
    print(f"[metrics_collector] saved to  {out_path}")

    if total_rows == 0:
        print("[metrics_collector] WARNING: zero rows collected — "
              "no graphs will be generated for this experiment")
        sys.exit(1)


if __name__ == "__main__":
    main()
