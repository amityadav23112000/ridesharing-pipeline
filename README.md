# Ridesharing Pipeline
## Intelligent, Scalable, Cost-Aware Cloud Data Pipeline
### CSG527 Cloud Computing | BITS Pilani Hyderabad | 2025-26
### Student: H20250060

---

## Project Overview

A production-grade, real-time ridesharing data pipeline that processes GPS telemetry from 500–50,000 simulated drivers. Implements a **Hybrid Lambda Architecture**: Spark Structured Streaming for sub-5s surge pricing decisions, and AWS Glue + Athena for daily batch analytics.

**8 experiments** across 3 infrastructure tiers (local, EC2, EMR) validate performance, cost, and fault-tolerance claims with real measurements.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA PRODUCERS                              │
│        GPS Devices / Driver Mobile Apps (500–50K drivers)       │
│        Each driver sends 1 GPS event/second                     │
└────────────────────────────┬────────────────────────────────────┘
                             │  HTTP POST /ingest
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    INGESTION LAYER                              │
│                                                                 │
│   FastAPI REST Server (:8080)  ←── src/rest_ingestor.py         │
│   Reads zone demand ratio and routes each event to:             │
│                                                                 │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐        │
│   │gps-critical │  │ gps-surge   │  │   gps-normal    │        │
│   │(zone ≥2.0x) │  │(zone ≥1.5x) │  │ (zone < 1.5x)  │        │
│   └──────┬──────┘  └──────┬──────┘  └────────┬────────┘        │
│          │                │                   │                 │
│          └────────────────┴───────────────────┘                 │
│                           │  3 Kafka topics                     │
│                           │  3 partitions each                  │
│                           │  Replicated across 3 brokers        │
│                           │  Messages stored on disk (durable)  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
          ┌─────────────────┴──────────────────┐
          │        SHARED S3 BRIDGE            │
          │  (Speed Layer writes raw events)   │
          │  (Batch Layer reads same S3 files) │
          └────────┬───────────────────────────┘
                   │
     ┌─────────────┴──────────────────────────────────────┐
     │                                                    │
     ▼                                                    ▼
┌──────────────────────────────┐     ┌────────────────────────────────────┐
│        SPEED LAYER           │     │           BATCH LAYER              │
│    (Real-time, < 5s SLA)     │     │       (Hourly, analytics)          │
│                              │     │                                    │
│  Spark Structured Streaming  │     │  Step Functions triggers hourly:   │
│  ← src/spark_streaming_job.py│     │                                    │
│                              │     │  1. CHECK: Is S3 input > 1MB?      │
│  reads all 3 Kafka topics    │     │     NO  → SKIP (saves cost)        │
│  every WINDOW_SECONDS:       │     │     YES → continue                 │
│    500  drivers → 2s window  │     │                                    │
│    5000 drivers → 5s window  │     │  2. AWS Glue ETL Job               │
│    50K  drivers → 10s window │     │     ← src/glue_batch_job.py        │
│                              │     │     reads: S3 raw/trips/           │
│  Stream-stream JOIN:         │     │     city=*/date=YYYY-MM-DD/        │
│    supply stream (drivers)   │     │     writes: S3 processed/          │
│    + demand stream (riders)  │     │     • city_stats.parquet           │
│    watermark = 30s           │     │     • driver_earnings.parquet      │
│                              │     │     • surge_analysis.parquet       │
│  Surge detection per zone:   │     │     • zone_heatmap.parquet         │
│    demand_ratio ≥ 1.5 → SURGE│     │                                    │
│    multiplier: 1.5x → 3.0x  │     │  3. Glue Crawler                   │
│                              │     │     scans S3 processed/            │
│  Writes results to:          │     │     updates Glue Data Catalogue    │
│  ┌───────────┐ ┌──────────┐  │     │                                    │
│  │ DynamoDB  │ │    S3    │  │     │  4. Amazon Athena                  │
│  │surge_price│ │raw/trips/│  │     │     SQL queries on parquet files   │
│  │(hot store)│ │(Parquet) │  │     │     via Glue catalogue             │
│  └─────┬─────┘ └────┬─────┘  │     │     results → S3 athena-results/  │
│        │            │        │     │                                    │
└────────┼────────────┼────────┘     └────────────────────────────────────┘
         │            │
         │            └─────────────────────────────────────────┐
         │                                         (same S3     │
         ▼                                          bucket)      │
┌─────────────────┐                                             │
│ DynamoDB Stream │                                             │
│ triggers Lambda │                                             │
│                 │                                             │
│ surge_multiplier│                                             ▼
│   ≥ 2.0 ?       │                              ┌──────────────────────┐
│   YES → SNS     │                              │  Athena Dashboard    │
│   alert sent    │                              │  docs/athena_        │
└─────────────────┘                              │  dashboard.html      │
                                                 │  6 panels with real  │
                                                 │  Athena query data   │
                                                 └──────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW SPEED LAYER AND BATCH LAYER ARE CONNECTED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Spark (Speed Layer) writes every processed GPS event to:
    s3://ridesharing-pipeline-h20250060/raw/trips/city=X/date=Y/

  Glue ETL (Batch Layer) reads from the SAME S3 path every hour.

  This S3 bucket is the BRIDGE between the two layers.
  Speed Layer produces → S3 → Batch Layer consumes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ORCHESTRATION  : AWS Step Functions (hourly) + Apache Airflow DAG
OBSERVABILITY  : Prometheus (metrics) → Grafana (dashboards)
                 CloudWatch (alarms + RidesharingPipeline dashboard)
FAULT TOLERANCE: Kafka checkpoint replay → zero data loss
IaC            : Terraform (31 AWS resources)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Quick Start (Local)

```bash
git clone https://github.com/amityadav23112000/ridesharing-pipeline.git
cd ridesharing-pipeline
pip install -r requirements.txt

# Start Kafka + Prometheus + Grafana
docker compose -f config/docker-compose.yml up -d

# Run Spark streaming (500 drivers, 2s window)
WINDOW_SECONDS=2 DRIVER_COUNT=500 \
  spark-submit --master local[4] \
    --jars jars/spark-sql-kafka.jar,jars/kafka-clients.jar,\
jars/commons-pool2.jar,jars/spark-token-provider-kafka.jar \
    src/spark_streaming_job.py &

# Start GPS simulator
KAFKA_BROKERS=localhost:9092 python3 src/gps_simulator.py \
  --drivers 500 --duration 120

# Open Grafana: http://localhost:3000  (admin/admin)
```

---

## Repository Structure

```
ridesharing-pipeline/
├── src/
│   ├── spark_streaming_job.py    # Main Spark streaming job (adaptive window, stream-join)
│   ├── gps_simulator.py          # GPS event producer (500–50K drivers)
│   ├── rest_ingestor.py          # FastAPI REST/IoT endpoint → Kafka routing
│   ├── schema_evolution.py       # v1→v2 schema upgrade with zone derivation
│   ├── data_lineage.py           # DynamoDB lineage tracker (audit trail)
│   ├── glue_batch_job.py         # AWS Glue PySpark ETL job
│   ├── batch_uploader.py         # Synthetic trip data → S3
│   └── metrics_collector.py      # CloudWatch metrics publisher
├── dags/
│   └── ridesharing_pipeline_dag.py  # Airflow DAG (hourly batch pipeline)
├── terraform/
│   ├── main.tf / variables.tf / outputs.tf
│   ├── glue.tf                   # Glue catalog, ETL job, crawler
│   ├── athena.tf                 # Athena workgroup + 6 saved queries
│   ├── lambda.tf                 # Lambda surge alert + SNS + DynamoDB stream
│   └── step_functions.tf         # Step Functions orchestration state machine
├── k8s/
│   ├── deployment.yaml           # Spark streaming Kubernetes deployment
│   └── hpa.yaml                  # Horizontal Pod Autoscaler (1→8 pods)
├── config/
│   ├── docker-compose.yml        # Kafka + Prometheus + Grafana stack
│   └── prometheus.yml            # Prometheus scrape config
├── docs/
│   ├── architecture_design.md    # Full architecture document
│   ├── benchmarking_report.md    # Performance & cost analysis
│   ├── research_report.md        # Literature review (Lambda/Spark/Kafka)
│   ├── presentation_outline.md   # 11-slide deck with demo checklist
│   └── athena_dashboard.html     # Athena analytics dashboard (Chart.js)
├── scripts/
│   ├── demo.sh                   # 7-step end-to-end live demo
│   └── download_real_dataset.sh  # NYC Taxi Jan 2024 → ridesharing CSV
├── experiments/
│   ├── results/
│   │   ├── summary_statistics.csv          # All 8 experiment results
│   │   ├── statistical_analysis.txt        # Pearson r, SLA checks
│   │   ├── athena_results/                 # 6 real Athena query CSVs
│   │   └── {local_sub5s,local_1k,...}/     # Per-experiment metrics CSVs
│   └── graphs/                             # 10 benchmark PNGs (gitignored)
├── jars/                         # Kafka-Spark connector JARs
└── data/real/                    # NYC Taxi 100K sample (gitignored)
```

---

## Experiments (8 total)

| Experiment | Infra | Drivers | Window | Avg EPS | p95 Latency | SLA < 5s |
|-----------|-------|---------|--------|---------|-------------|----------|
| `local_sub5s` | Local | 500 | 2s | 60.7 | 4,328ms | **PASS** |
| `local_1k` | Local | 1,000 | 2s | 105.0 | 3,813ms | **PASS** |
| `fault_local` | Local | 1,000 | 5s | 102.6 | 4,312ms | **PASS** |
| `local_5k` | Local | 5,000 | 5s | 464.2 | 6,675ms | NEAR |
| `ec2_5k` | EC2 | 5,000 | 5s | 470.1 | 6,147ms | NEAR |
| `fault_ec2` | EC2 | 5,000 | 5s | 462.3 | 6,125ms | NEAR |
| `ec2_50k` | EC2 | 50,000 | 10s | 1,836.8 | 33,374ms | FAIL |
| `emr_50k` | EMR | 50,000 | 10s | 2,045.7 | 132,500ms | FAIL |

**Key findings:**
- Sub-5s SLA met at ≤ 1K drivers on local hardware
- Adaptive window reduces latency by **49%** at low driver counts
- EC2 matches local performance at 5K (470 vs 464 EPS)
- EMR costs 6× more than EC2 for only 11% throughput gain at 50K
- Fault recovery: < 30s local, < 150s EC2 — **zero data loss**

---

## Innovations

### 1. Adaptive Window Sizing
```python
WINDOW_SECONDS = max(2, driver_count // 1000)
```
ConfigMap-driven — live adjustment without Spark restart. **Result: −49% latency** at 500 drivers.

### 2. Three-Tier Kafka Topic Priority
`gps-critical` / `gps-surge` / `gps-normal` — FastAPI routes each event at ingestion time.

### 3. Schema Evolution with Lineage
`src/schema_evolution.py` upgrades v1→v2 without breaking consumers.
`src/data_lineage.py` writes a DynamoDB audit trail for every upgrade.

### 4. Conditional Batch Skip
Glue job skips if S3 input < 1MB. **Saves ~$3.52/night** in idle Glue charges.

---

## Batch Analytics (AWS Athena)

**Database:** `ridesharing_pipeline` (ap-south-1)
**Tables:** `city_stats`, `driver_earnings`, `surge_analysis`, `zone_heatmap`
**Data:** 3 dates × 10 cities × 100 trips = 3,000 trip records in Parquet

Run these queries in the Athena console (results stored in `s3://.../athena-results/`):

```sql
-- Q1: Top cities by revenue
SELECT city_id, SUM(total_revenue_inr) AS total_revenue,
       ROUND(AVG(avg_fare_inr),2) AS avg_fare
FROM city_stats GROUP BY city_id ORDER BY total_revenue DESC;

-- Q2: Top 10 driver earnings
SELECT driver_id, city_id, total_earnings_inr, total_trips
FROM driver_earnings ORDER BY total_earnings_inr DESC LIMIT 10;

-- Q3: Surge distribution by city
SELECT city_id, surge_bucket, trip_count, ROUND(cancellation_rate_pct,1) AS cancel_rate
FROM surge_analysis ORDER BY city_id, surge_bucket;

-- Q4: Zone peak hours
SELECT city_id, pickup_zone, pickup_hour, trip_count, ROUND(avg_surge,2) AS avg_surge
FROM zone_heatmap WHERE pickup_hour BETWEEN 7 AND 22
ORDER BY trip_count DESC LIMIT 20;

-- Q5: City completion rates
SELECT city_id, ROUND(completion_rate_pct,1) AS completion_pct, ROUND(avg_surge,2) AS avg_surge
FROM city_stats ORDER BY completion_rate_pct DESC;

-- Q6: Surge impact on cancellations
SELECT surge_bucket, SUM(trip_count) AS trips,
       ROUND(AVG(cancellation_rate_pct),1) AS avg_cancel_rate
FROM surge_analysis GROUP BY surge_bucket ORDER BY surge_bucket;
```

**Multi-date trend (all 3 dates):**
```sql
SELECT date, SUM(total_trips) AS trips, ROUND(SUM(total_revenue_inr),2) AS revenue
FROM city_stats GROUP BY date ORDER BY date;
```

Sample output: 2026-04-08 ₹2,00,255 | 2026-04-13 ₹1,99,394 | 2026-04-14 ₹2,02,152

---

## Observability

```bash
# Grafana: http://localhost:3000 (admin/admin)
docker compose -f config/docker-compose.yml up -d

# Prometheus: http://localhost:9090
# CloudWatch dashboard: RidesharingPipeline (ap-south-1)
```

Key Prometheus metrics: `spark_kafka_events_per_second`, `spark_active_surge_zones`, `spark_batch_latency_ms`

---

## AWS Resources

All in `ap-south-1`. Managed via `terraform/`.

| Resource | Name | Status |
|----------|------|--------|
| S3 bucket | `ridesharing-pipeline-h20250060` | Active (11.5 MB) |
| DynamoDB | `driver_status`, `surge_pricing`, `zone_demand` | Active |
| Lambda | `ridesharing-surge-alert` | Active |
| Glue DB | `ridesharing_pipeline` (4 tables) | Active |
| Step Functions | `ridesharing-pipeline-batch-pipeline` | Active |
| EC2 `ridesharing-scale2` | c5.2xlarge | **STOPPED** |
| EMR `ridesharing-emr-scale3` ×2 | 4×m5.xlarge | **TERMINATED** |

> **Ongoing cost: ~$0.003/day** (S3 + DynamoDB storage only)

---

## Cost Summary

| Experiment | Cost/hr |
|-----------|---------|
| Local (laptop) | $0.00 |
| EC2 c5.2xlarge | $0.20 |
| EMR 4×m5.xlarge | $1.25 |
| **Total project spend** | **~$8–10** |

---

## Deliverables Checklist

| Item | File | Status |
|------|------|--------|
| Architecture doc | `docs/architecture_design.md` | ✓ |
| Benchmarking report | `docs/benchmarking_report.md` | ✓ |
| Research report | `docs/research_report.md` | ✓ |
| Demo script | `scripts/demo.sh` | ✓ |
| Athena dashboard | `docs/athena_dashboard.html` | ✓ |
| Presentation outline | `docs/presentation_outline.md` | ✓ |
| 8 experiment CSVs | `experiments/results/` | ✓ |
| 6 Athena query results | `experiments/results/athena_results/` | ✓ |
| Real dataset (100K) | `data/real/` (gitignored — run `scripts/download_real_dataset.sh`) | ✓ |
| 10 benchmark graphs | `experiments/graphs/` (gitignored — run `python3 experiments/generate_graphs.py`) | ✓ |
| Airflow DAG | `dags/ridesharing_pipeline_dag.py` | ✓ |
| Terraform IaC | `terraform/` | ✓ |

---

## Reproduce Results

```bash
# Regenerate all 10 benchmark graphs
python3 experiments/generate_graphs.py

# Download real NYC Taxi dataset (100K rows)
bash scripts/download_real_dataset.sh

# Run end-to-end live demo
bash scripts/demo.sh
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError` | `pip install -r requirements.txt` |
| Kafka topics missing | `docker compose -f config/docker-compose.yml up -d` and wait 20s |
| `unrecognized arguments: --kafka-broker` | Use env var: `KAFKA_BROKERS=localhost:9092 python3 src/gps_simulator.py` |
| Athena: no query result location | Already set to `s3://ridesharing-pipeline-h20250060/athena-results/` |
| Glue table shows no rows | Run `MSCK REPAIR TABLE <table>` in Athena |
| Spark JAR not found | Ensure all 4 JARs are in `jars/` directory |

---

## GitHub

[https://github.com/amityadav23112000/ridesharing-pipeline](https://github.com/amityadav23112000/ridesharing-pipeline)
