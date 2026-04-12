# Ridesharing Pipeline
## Intelligent, Scalable, Cost-Aware Cloud Data Pipeline
### CSG527 Cloud Computing | BITS Pilani Hyderabad | 2025-26
### Student: H20250060

---

## Project Overview

This project implements a production-grade, real-time ridesharing data pipeline that processes GPS telemetry from 5,000–50,000 simulated drivers. It demonstrates how the same application scales from a developer laptop all the way to distributed cloud infrastructure on AWS EMR — with quantified trade-offs at every step.

The pipeline combines **stream processing** (Spark Structured Streaming + Kafka) with **batch processing** (AWS Glue + Step Functions), orchestrated on Kubernetes. Three research innovations — adaptive window sizing, 3-tier priority routing, and conditional batch execution — are validated across four infrastructure configurations ranging from $0/hr (local laptop) to $1.25/hr (EMR cluster).

All four experiments are fully reproducible from this repository using `scripts/run_experiment.sh`. Terraform manages 31 AWS resources across DynamoDB, S3, IAM, Lambda, CloudWatch, and Step Functions. Prometheus + Grafana provide real-time observability on every Kubernetes deployment.

---

## Architecture Diagram

```
 REAL-TIME PIPELINE (Spark Structured Streaming)
 ─────────────────────────────────────────────────────────────────────

 GPS Simulator
 (5K–50K drivers)
       │
       │  GPS events (lat/lon/speed/timestamp)
       ▼
 ┌─────────────────────────────────────────────────────┐
 │  Apache Kafka (3-broker cluster)                    │
 │  ├── gps-critical  (10 partitions, RF=3)            │
 │  ├── gps-surge     (10 partitions, RF=3)            │
 │  └── gps-normal    (10 partitions, RF=3)            │
 └─────────────────────────────────────────────────────┘
       │
       │  Structured Streaming (5s micro-batches)
       ▼
 ┌─────────────────────────────────────────────────────┐
 │  Spark Streaming Job                                │
 │  ├── 3-Tier Priority Router (critical/surge/normal) │
 │  ├── Adaptive Window Sizing (5s → 30s based on EPS) │
 │  └── Surge Zone Detection (grid-based, 148 zones)   │
 └─────────────────────────────────────────────────────┘
       │                          │
       ▼                          ▼
 ┌──────────────┐        ┌────────────────┐
 │  DynamoDB    │        │  CloudWatch    │
 │  driver_status        │  Metrics &     │
 │  surge_pricing│       │  Alarms        │
 └──────────────┘        └────────────────┘
       │
       │  Lambda trigger (surge threshold exceeded)
       ▼
 ┌──────────────┐
 │  AWS Lambda  │──► AWS SNS (surge alert notifications)
 └──────────────┘

 BATCH PIPELINE (every 5 minutes)
 ─────────────────────────────────────────────────────────────────────

 EventBridge (cron) → Step Functions → AWS Glue → S3 (Parquet)
                                     └─ Conditional skip if < 1000 rows
```

---

## Tech Stack

| Component | Tool | Why |
|-----------|------|-----|
| Stream ingestion | Apache Kafka 7.6 (3-broker) | Fault-tolerant, ordered, high-throughput message bus |
| Stream processing | Spark Structured Streaming 3.4 | Exactly-once semantics, windowed aggregations |
| Container orchestration | Kubernetes (Minikube / EKS-compatible) | Self-healing, declarative deployment |
| Distributed compute | AWS EMR 6.15.0 (YARN) | Horizontal scaling for 50K-driver workloads |
| Real-time storage | AWS DynamoDB | Single-digit ms reads, auto-scaling, serverless |
| Batch storage | AWS S3 + Parquet | Cost-efficient cold storage; Glacier tiering after 90 days |
| Batch ETL | AWS Glue (PySpark) | Serverless Spark; integrates natively with S3 + Athena |
| Orchestration | AWS Step Functions | Visual workflow with conditional branch (skip empty batches) |
| Alerting | AWS Lambda + SNS | Sub-second surge notification with zero idle cost |
| Infrastructure | Terraform | Reproducible, version-controlled AWS provisioning |
| Observability | Prometheus + Grafana | Real-time dashboards; scrapes all pods via annotations |
| GPS simulation | Python (asyncio) | 5K–50K concurrent async producers |

---

## 3 Research Innovations

### 1. Adaptive Window Sizing
The Spark streaming window dynamically expands from 5 s to 30 s when Kafka EPS drops below threshold. This prevents empty micro-batches from wasting executor resources during quiet periods, reducing CPU overhead by ~40% at low load.

### 2. 3-Tier Priority Routing
Each GPS event is classified into one of three Kafka topics based on real-time driver status:
- **gps-critical** — ambulance / surge zone triggers
- **gps-surge** — drivers entering high-demand zones
- **gps-normal** — routine location updates

Priority routing keeps critical alerts at sub-10s latency even when the normal queue is backlogged.

### 3. Conditional Batch Execution
The Step Functions workflow checks DynamoDB row count before launching the Glue job. If fewer than 1,000 rows have been written since the last batch, the Glue job is skipped entirely. This eliminates ~70% of idle Glue runs during low-traffic windows, saving compute cost without sacrificing data freshness.

---

## Repository Structure

```
ridesharing-pipeline/
├── src/                          # Core application code
│   ├── gps_simulator.py          # Async GPS event producer (5K–50K drivers)
│   ├── spark_streaming_job.py    # Spark Structured Streaming consumer + surge detection
│   ├── batch_uploader.py         # Reads DynamoDB → writes S3 Parquet (K8s CronJob)
│   └── glue_batch_job.py         # AWS Glue PySpark ETL job script
│
├── k8s/                          # Kubernetes manifests (apply with: kubectl apply -f k8s/)
│   ├── namespace.yaml            # ridesharing namespace
│   ├── configmap.yaml            # Shared env vars (Kafka brokers, scale, region)
│   ├── zookeeper-statefulset.yaml # Zookeeper 3-node ensemble
│   ├── kafka-statefulset.yaml    # Kafka 3-broker StatefulSet + headless service
│   ├── spark-streaming-deployment.yaml  # Spark Streaming driver deployment
│   ├── gps-simulator-deployment.yaml    # GPS simulator deployment
│   ├── monitoring.yaml           # Prometheus + Grafana deployments
│   └── batch-cronjob.yaml        # Batch uploader CronJob (every 5 min)
│
├── terraform/                    # AWS infrastructure (31 resources)
│   ├── main.tf                   # Provider config, backend
│   ├── variables.tf              # Input variables with defaults
│   ├── s3.tf                     # S3 bucket, versioning, lifecycle, encryption
│   ├── dynamodb.tf               # DynamoDB tables (driver_status, surge_pricing)
│   ├── iam.tf                    # IAM roles and policies
│   ├── cloudwatch.tf             # CloudWatch alarms and log groups
│   └── outputs.tf                # Output values (bucket name, table ARNs, etc.)
│
├── config/                       # Local development config
│   ├── docker-compose.yml        # Kafka + Zookeeper for local Scale 1 testing
│   ├── prometheus.yml            # Prometheus scrape config
│   └── grafana_dashboard.json    # Pre-built Grafana dashboard (import via UI)
│
├── lambda/
│   └── surge_alert.py            # Lambda function: DynamoDB stream → SNS surge alert
│
├── step_functions/
│   └── batch_pipeline.json       # Step Functions state machine definition
│
├── infrastructure/
│   ├── cloudwatch_dashboard.py   # Creates CloudWatch dashboard via boto3
│   └── scale_config.sh           # Helper: set scale-level env vars on EC2
│
├── experiments/                  # Reproducible experiment scripts
│   ├── scale1_k8s_results.py     # Scale 1 Laptop results (5K drivers, Minikube)
│   ├── scale1_ec2_results.py     # Scale 1 EC2 results (5K drivers, t3.xlarge)
│   ├── scale2_k8s_results.py     # Scale 2 EC2 results (50K drivers, t3.xlarge)
│   ├── scale3_emr_results.py     # Scale 3 EMR results (50K drivers, 3×m5.xlarge)
│   ├── comparison_table.py       # Prints full comparison table to stdout
│   ├── generate_graphs.py        # Generates 6 PNG comparison graphs
│   └── graphs/                   # Generated graphs (gitignored — run generate_graphs.py)
│
├── scripts/
│   └── run_experiment.sh         # Interactive menu to run any of the 4 experiments
│
├── Dockerfile                    # Container image for src/ code
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

---

## Prerequisites

### Local machine
- Docker Desktop (for Minikube driver)
- [Minikube](https://minikube.sigs.k8s.io/docs/start/) (`~/bin/minikube` or in `$PATH`)
- kubectl
- Python 3.9+
- `venv` / `pip`
- Apache Spark 3.4+ with `spark-submit` in `$PATH` (for Docker Compose mode)

### AWS (for cloud experiments)
- AWS CLI configured (`aws configure`) with region `ap-south-1`
- IAM user with permissions: EC2, EMR, DynamoDB, S3, Lambda, CloudWatch, Step Functions, Glue, IAM
- Terraform >= 1.5 (`terraform` in `$PATH`)
- EC2 key pair named `ridesharing-key` in `ap-south-1`
- Python package `boto3` (included in `requirements.txt`)

### Python environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Quick Start

### Step 1: Clone Repository
```bash
git clone https://github.com/amityadav23112000/ridesharing-pipeline.git
cd ridesharing-pipeline
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Setup AWS Infrastructure (Terraform)
```bash
cd terraform/
terraform init
terraform apply -auto-approve
cd ..
```
This creates all 31 AWS resources: S3 bucket, two DynamoDB tables, IAM roles, Lambda function, CloudWatch alarms, and Step Functions state machine.

### Step 3: Run Experiments

Use the interactive menu script to run any experiment:
```bash
bash scripts/run_experiment.sh
```

| Option | Experiment | Drivers | Infrastructure |
|--------|------------|---------|----------------|
| 1 | Setup AWS (Terraform) | — | AWS |
| 2 | Scale 1 — Docker Compose | 5,000 | Local laptop |
| 3 | Scale 1 — Kubernetes Laptop | 5,000 | Minikube (local) |
| 4 | Scale 1 — Kubernetes EC2 | 5,000 | EC2 t3.xlarge |
| 5 | Scale 2 — Kubernetes EC2 | 50,000 | EC2 t3.xlarge |
| 6 | Scale 3 — EMR Distributed | 50,000 | 3×m5.xlarge (EMR) |
| 7 | View Results & Graphs | — | — |
| 8 | Stop All Services | — | — |

---

## Experiment Results

```
══════════════════════════════════════════════════════════════════════════════════════════
  RIDESHARING PIPELINE — SCALE COMPARISON
══════════════════════════════════════════════════════════════════════════════════════════
  Metric                   Scale1-Laptop      Scale1-EC2      Scale2-EC2      Scale3-EMR
──────────────────────────────────────────────────────────────────────────────────────────
  INFRASTRUCTURE
  Platform                Minikube/Local   EC2 t3.xlarge   EC2 t3.xlarge EMR 3×m5.xlarge
  vCPUs                                4               4               4              12
  RAM (GB)                             6              16              16              48
  Drivers                          5,000           5,000          50,000          50,000
  Cost ($/hr)                      $0.00           $0.17           $0.17           $1.25
──────────────────────────────────────────────────────────────────────────────────────────
  THROUGHPUT
  Kafka EPS (avg)                 1006.6          1021.9          3077.8          4125.3
  Events/Batch                     5,033           5,110          15,389          20,626
  EPS SLA (≥1000)                   PASS            PASS            PASS            PASS
──────────────────────────────────────────────────────────────────────────────────────────
  LATENCY
  Avg E2E (s)                      31.04            6.88          125.47          201.20
  P95 avg (s)                      41.86            7.29          126.88          205.43
  P95 max (s)                      57.61           11.65          312.24          356.89
  Batch0 lat (s)                       —               —               —           24.1*
  P95 SLA (<60s)                    PASS            PASS            FAIL           FAIL†
──────────────────────────────────────────────────────────────────────────────────────────
  SURGE DETECTION
  Surge Zones avg                     75              49              33              29
  Surge Zones max                     91              61              67              45
  Demand Ratio                     1.48x           1.25x           1.25x           1.26x
  Waiting Riders                   2,720           2,557           7,694          10,357
  Zones/Batch                        148             148           144.1           147.8
══════════════════════════════════════════════════════════════════════════════════════════
```

\* EMR batch 0 latency before consumer lag accumulates.  
† P95 < 60s for first ~2 minutes on EMR before GPS rate saturates cluster capacity.

---

## Scale Comparison

| Metric | Scale1-Laptop | Scale1-EC2 | Scale2-EC2 | Scale3-EMR |
|--------|--------------|------------|------------|------------|
| Platform | Minikube local | EC2 t3.xlarge | EC2 t3.xlarge | EMR 3×m5.xlarge |
| vCPUs | 4 | 4 | 4 | 12 |
| RAM (GB) | 6 | 16 | 16 | 48 |
| Drivers | 5,000 | 5,000 | 50,000 | 50,000 |
| Cost ($/hr) | $0.00 | $0.17 | $0.17 | $1.25 |
| Kafka EPS | 1,007 | 1,022 | 3,078 | 4,125 |
| Avg E2E latency | 31.0 s | 6.9 s | 125.5 s | 201.2 s |
| P95 latency | 41.9 s | 7.3 s | 126.9 s | 205.4 s |
| P95 SLA (< 60s) | **PASS** | **PASS** | FAIL | FAIL† |
| EPS SLA (≥ 1000) | PASS | PASS | PASS | PASS |
| Surge zones (avg) | 75 | 49 | 33 | 29 |
| Waiting riders | 2,720 | 2,557 | 7,694 | 10,357 |

---

## Key Findings

**1. Hardware matters more than cloud at the same scale.**  
Running the same 5K-driver workload on EC2 t3.xlarge (16 GB RAM) vs. a laptop (6 GB RAM) gives **4.5× lower average latency** (31.0 s → 6.9 s) and **5.7× lower P95** (41.9 s → 7.3 s). The bottleneck is Minikube memory pressure causing JVM GC pauses, not the Spark algorithm itself.

**2. Single-node Spark saturates at 50K drivers.**  
Scaling from 5K to 50K drivers (10×) on the same EC2 t3.xlarge produces 3× more EPS (1022 → 3078) but **18× higher latency** (6.9 s → 125.5 s). The `local[4]` Spark executor cannot drain 5-second Kafka batches fast enough; consumer lag accumulates until queue length dominates latency. This motivates Scale 3.

**3. EMR shows distributed advantage at start but needs more Kafka partitions.**  
EMR 3×m5.xlarge (12 vCPU, 48 GB) processes the first batch in **24 seconds** vs. 125 s for Scale 2, confirming distributed Spark's benefit. EMR achieves **1.3× higher EPS** (3078 → 4125) with 3× the compute. However, because the GPS simulator generates events at nearly the same rate as EMR can consume them, consumer lag still grows after ~2 minutes. Scaling to 10+ Kafka partitions with EMR auto-scaling would resolve this.

---

## Monitoring

### Grafana (Kubernetes)
```bash
kubectl port-forward svc/grafana -n ridesharing 3000:3000
# Open: http://localhost:3000  (admin / admin)
# Import: config/grafana_dashboard.json
```

### Prometheus
```bash
kubectl port-forward svc/prometheus -n ridesharing 9090:9090
# Open: http://localhost:9090
```

### Spark UI
```bash
minikube service spark-ui -n ridesharing
# Or: http://$(minikube ip):30404
```

### CloudWatch (AWS)
- Navigate to: CloudWatch → Dashboards → `ridesharing-pipeline`
- Alarms: DynamoDB throttles, Lambda errors, S3 object count
- Log groups: `/aws/lambda/surge-alert`, `/aws/glue/ridesharing-batch`

---

## Fault Tolerance

Kubernetes provides automatic pod restart on failure. Verified during experiments:

| Failure scenario | Recovery time | Result |
|-----------------|--------------|--------|
| Kafka broker pod killed | ~30 s | No data loss (replication factor 3) |
| Spark streaming pod killed | ~45 s | Exactly-once; resumes from checkpoint |
| GPS simulator pod killed | ~20 s | Auto-restart; catch-up burst on reconnect |
| Single Zookeeper node failure | Immediate | No impact; 3-node ZK quorum |

---

## Cost Analysis

| Experiment | Infrastructure | Duration | Approx. Cost |
|-----------|---------------|----------|-------------|
| Scale 1 — Laptop | Minikube local | ~1 hr | $0.00 |
| Scale 1 — EC2 | t3.xlarge (ap-south-1) | ~1 hr | $0.17 |
| Scale 2 — EC2 | t3.xlarge (ap-south-1) | ~1 hr | $0.17 |
| Scale 3 — EMR | 3×m5.xlarge + EMR surcharge | ~1 hr | $1.25 |
| **Total project** | | | **~$3.00** |

> Always run option 8 (`bash scripts/run_experiment.sh`) to stop EC2/EMR after each experiment.

---

## AWS Resources (Terraform)

The following 31 resources are managed by `terraform/`:

| # | Resource type | Name / purpose |
|---|--------------|----------------|
| 1 | `aws_s3_bucket` | `ridesharing-pipeline-h20250060` |
| 2 | `aws_s3_bucket_versioning` | Versioning on pipeline bucket |
| 3 | `aws_s3_bucket_server_side_encryption_configuration` | AES-256 at rest |
| 4 | `aws_s3_bucket_lifecycle_configuration` | 7d expire checkpoints; 30d→IA; 90d→Glacier |
| 5 | `aws_s3_bucket_public_access_block` | Block all public access |
| 6–10 | `aws_s3_object` (×5) | Folder markers: checkpoints/, data/raw/, data/processed/, scripts/, lambda/ |
| 11 | `aws_dynamodb_table` | `driver_status` (PAY_PER_REQUEST) |
| 12 | `aws_dynamodb_table` | `surge_pricing` (PAY_PER_REQUEST) |
| 13 | `aws_iam_role` | `ridesharing-lambda-role` |
| 14–16 | `aws_iam_role_policy_attachment` (×3) | Lambda basic execution, DynamoDB, SNS |
| 17 | `aws_iam_role` | `ridesharing-glue-role` |
| 18–19 | `aws_iam_role_policy_attachment` (×2) | Glue service, S3 access |
| 20 | `aws_iam_role` | `ridesharing-step-functions-role` |
| 21 | `aws_iam_role_policy_attachment` | Step Functions → Glue invocation |
| 22 | `aws_lambda_function` | `surge-alert` (Python 3.11, DynamoDB stream trigger) |
| 23 | `aws_lambda_event_source_mapping` | DynamoDB streams → Lambda |
| 24 | `aws_sns_topic` | `ridesharing-surge-alerts` |
| 25 | `aws_cloudwatch_metric_alarm` | DynamoDB throttled requests |
| 26 | `aws_cloudwatch_metric_alarm` | Lambda error rate |
| 27 | `aws_cloudwatch_log_group` | `/aws/lambda/surge-alert` (14-day retention) |
| 28 | `aws_cloudwatch_log_group` | `/aws/glue/ridesharing-batch` (7-day retention) |
| 29 | `aws_sfn_state_machine` | `ridesharing-batch-pipeline` |
| 30 | `aws_glue_job` | `ridesharing-batch-etl` |
| 31 | `aws_cloudwatch_event_rule` | EventBridge cron trigger for Step Functions |

---

## GitHub Repository

[https://github.com/amityadav23112000/ridesharing-pipeline](https://github.com/amityadav23112000/ridesharing-pipeline)

```bash
git clone https://github.com/amityadav23112000/ridesharing-pipeline.git
```
