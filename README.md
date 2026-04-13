# Ridesharing Pipeline
## Intelligent, Scalable, Cost-Aware Cloud Data Pipeline
### CSG527 Cloud Computing | BITS Pilani Hyderabad | 2025-26
### Student: H20250060

---

## Project Overview

This project implements a production-grade, real-time ridesharing data pipeline that processes GPS telemetry from 5,000–50,000 simulated drivers. It demonstrates how the same application scales from a developer laptop all the way to distributed cloud infrastructure on AWS EMR — with quantified trade-offs at every step.

The pipeline combines **stream processing** (Spark Structured Streaming + Kafka) with **batch processing** (AWS Glue + Step Functions), orchestrated on Kubernetes. Three research innovations — adaptive window sizing, 3-tier priority routing, and conditional batch execution — are validated across four infrastructure configurations ranging from $0/hr (local laptop) to $1.25/hr (EMR cluster).

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
| GPS simulation | Python (threading) | 5K–50K concurrent threaded producers |

---

## 3 Research Innovations

### 1. Adaptive Window Sizing
The Spark streaming window is controlled entirely by the `WINDOW_SECONDS` environment variable — no code change required. Set `WINDOW_SECONDS=5` at peak load (fast surge detection) or `WINDOW_SECONDS=120` during off-peak (reduces CPU by ~40%). The ConfigMap drives this change at runtime via `kubectl patch`.

### 2. 3-Tier Priority Routing
Each GPS event is classified into one of three Kafka topics based on real-time driver status:
- **gps-critical** — ambulance / surge zone triggers (speed > 100 km/h or battery < 10%)
- **gps-surge** — drivers entering high-demand zones (demand ratio > 1.5)
- **gps-normal** — routine location updates

Priority routing keeps critical alerts at sub-10s latency even when the normal queue is backlogged.

### 3. Conditional Batch Execution
The Step Functions workflow checks whether the S3 input file exists before launching the Glue job. If no data is found for the day, the Glue job is skipped entirely. This eliminates idle Glue runs during low-traffic windows, saving compute cost without sacrificing data freshness.

---

## Repository Structure

```
ridesharing-pipeline/
├── src/                          # Core application code
│   ├── gps_simulator.py          # Threaded GPS event producer (5K–50K drivers)
│   ├── spark_streaming_job.py    # Spark Structured Streaming consumer + surge detection
│   ├── batch_uploader.py         # Generates synthetic trip CSV → uploads to S3
│   └── glue_batch_job.py         # AWS Glue PySpark ETL job script
│
├── k8s/                          # Kubernetes manifests
│   ├── namespace.yaml            # ridesharing namespace
│   ├── configmap.yaml            # Shared env vars (Kafka brokers, scale, region)
│   ├── zookeeper-statefulset.yaml
│   ├── kafka-statefulset.yaml    # Kafka 3-broker StatefulSet + headless service
│   ├── spark-streaming-deployment.yaml
│   ├── gps-simulator-deployment.yaml
│   ├── hpa.yaml                  # HorizontalPodAutoscaler for Spark + GPS simulator
│   ├── monitoring.yaml           # Prometheus + Grafana deployments
│   └── batch-cronjob.yaml        # Batch uploader CronJob (every 5 min)
│
├── terraform/                    # AWS infrastructure (31 resources)
│   ├── main.tf                   # Provider config, backend
│   ├── variables.tf              # Input variables with defaults
│   ├── s3.tf                     # S3 bucket, versioning, lifecycle, encryption
│   ├── dynamodb.tf               # DynamoDB tables (driver_status, surge_pricing, zone_demand)
│   ├── iam.tf                    # IAM roles and policies
│   ├── cloudwatch.tf             # CloudWatch alarms and dashboard
│   └── outputs.tf                # Output values (bucket name, table ARNs, etc.)
│
├── config/                       # Local development config
│   ├── docker-compose.yml        # Kafka + Zookeeper for local Scale 1 testing
│   ├── prometheus.yml            # Prometheus scrape config
│   └── grafana_dashboard.json    # Pre-built Grafana dashboard (import via UI)
│
├── lambda/
│   └── surge_alert.py            # Lambda: DynamoDB stream → SNS surge alert
│
├── step_functions/
│   └── batch_pipeline.json       # Step Functions state machine definition
│
├── infrastructure/
│   ├── cloudwatch_dashboard.py   # Creates CloudWatch dashboard via boto3
│   └── scale_config.sh           # Source this to set scale-level env vars
│
├── experiments/                  # Reproducible experiment result scripts
│   ├── scale1_k8s_results.py
│   ├── scale1_ec2_results.py
│   ├── scale1_ec2_2s_window.py
│   ├── scale2_k8s_results.py
│   ├── scale3_emr_results.py
│   ├── comparison_table.py       # Prints full comparison table to stdout
│   └── generate_graphs.py        # Generates 6 PNG comparison graphs
│
├── scripts/
│   ├── run_experiment.sh         # Interactive menu — run any experiment
│   └── scale.sh                  # Patch ConfigMap + rollout restart for scale switch
│
├── jars/                         # Kafka/Spark connector JARs (required for local run)
│   ├── spark-sql-kafka.jar
│   ├── kafka-clients.jar
│   ├── spark-token-provider-kafka.jar
│   └── commons-pool2.jar
│
├── Dockerfile                    # Container image for src/ code
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

---

## Prerequisites

### Local machine
- Docker Desktop (running, for Minikube driver and Docker Compose)
- [Minikube](https://minikube.sigs.k8s.io/docs/start/) (`~/bin/minikube` or in `$PATH`)
- kubectl
- Python 3.9+
- Apache Spark 3.4+ with `spark-submit` in `$PATH` (only needed for Docker Compose mode)

### AWS (for cloud experiments)
- AWS CLI configured (`aws configure`) with region `ap-south-1`
- IAM user with: EC2, EMR, DynamoDB, S3, Lambda, CloudWatch, Step Functions, Glue, IAM permissions
- Terraform >= 1.5 (`terraform` in `$PATH`)
- EC2 key pair named `ridesharing-key` in `ap-south-1`

---

## Step-by-Step Setup

### Step 1 — Clone and install Python dependencies

```bash
git clone https://github.com/amityadav23112000/ridesharing-pipeline.git
cd ridesharing-pipeline

python3 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> `requirements.txt` includes all runtime dependencies: PySpark, Kafka, boto3, Prometheus client,
> Faker, matplotlib, seaborn, and pandas.

---

### Step 2 — Provision AWS Infrastructure (Terraform)

Run this once before any cloud experiment. It creates all 31 AWS resources.

```bash
cd terraform/
terraform init
terraform apply -auto-approve
cd ..
```

**What gets created:**
- S3 bucket `ridesharing-pipeline-h20250060` (versioned, AES-256 encrypted, Glacier lifecycle)
- DynamoDB tables: `surge_pricing`, `driver_status`, `zone_demand`
- IAM roles for Lambda, Glue, EC2/Spark
- Lambda function `surge-alert` + DynamoDB stream trigger
- SNS topic `ridesharing-surge-alerts`
- CloudWatch alarms (high latency > 10s, low throughput < 10 EPS)
- Step Functions state machine `ridesharing-batch-pipeline`
- AWS Glue job `ridesharing-batch-etl`
- EventBridge cron rule

> **Cost**: ~$0 until you actually run a Glue job or EMR cluster. DynamoDB is on-demand billing.

---

### Step 3 — Run Experiments (Interactive Menu)

```bash
bash scripts/run_experiment.sh
```

The menu offers 8 options:

```
======================================
 RIDESHARING PIPELINE — EXPERIMENT RUNNER
======================================
  1. Setup AWS Infrastructure (Terraform)
  2. Scale 1 — Docker Compose Laptop (5K drivers)
  3. Scale 1 — Kubernetes Laptop (5K drivers)
  4. Scale 1 — Kubernetes EC2 (5K drivers)
  5. Scale 2 — Kubernetes EC2 (50K drivers)
  6. Scale 3 — EMR Distributed (50K drivers)
  7. View Results & Graphs
  8. Stop All Services
======================================
```

---

#### Option 2 — Scale 1: Docker Compose (Laptop, 5K drivers)

**What it does:**
1. Starts Zookeeper + 3 Kafka brokers + Prometheus + Grafana via `config/docker-compose.yml`
2. Waits 45 s for Kafka to be ready
3. Creates 3 Kafka topics (`gps-critical`, `gps-surge`, `gps-normal`) with 10 partitions, replication-factor 3

**After the script, open two terminals:**

Terminal 1 — Start Spark streaming job:
```bash
source venv/bin/activate
export SCALE_LEVEL=5K WINDOW_SECONDS=5
spark-submit --master local[4] --driver-memory 2g \
  --jars jars/spark-sql-kafka.jar,jars/kafka-clients.jar,\
jars/spark-token-provider-kafka.jar,jars/commons-pool2.jar \
  src/spark_streaming_job.py
```

Terminal 2 — Start GPS simulator:
```bash
source venv/bin/activate
python src/gps_simulator.py --drivers 5000
```

**What to watch:** Spark logs print per-batch surge zone counts and latency. Prometheus metrics at `http://localhost:9090`. Grafana at `http://localhost:3000` (admin/admin).

---

#### Option 3 — Scale 1: Kubernetes on Laptop (Minikube, 5K drivers)

**What it does:**
1. Starts Minikube with 4 CPUs and 6 GB RAM
2. Applies all K8s manifests from `k8s/` (namespace, configmap, Zookeeper, Kafka, Spark, GPS simulator, Prometheus, Grafana, HPA, batch CronJob)
3. Waits until all pods are Ready (up to 5 min)

**Prerequisites before running:**
```bash
# Create the aws-credentials secret (required by Spark and batch-uploader pods)
kubectl create namespace ridesharing 2>/dev/null || true
kubectl create secret generic aws-credentials \
  --from-literal=access-key-id="$(aws configure get aws_access_key_id)" \
  --from-literal=secret-access-key="$(aws configure get aws_secret_access_key)" \
  -n ridesharing

# Build the Docker image inside Minikube's Docker daemon
eval $(minikube docker-env)
docker build -t ridesharing-pipeline:latest .
```

**Monitor pods:**
```bash
kubectl get pods -n ridesharing -w
kubectl logs -f deployment/spark-streaming -n ridesharing
kubectl logs -f deployment/gps-simulator -n ridesharing
```

**Access UIs:**
```bash
kubectl port-forward svc/grafana -n ridesharing 3000:3000   # http://localhost:3000
kubectl port-forward svc/prometheus -n ridesharing 9090:9090 # http://localhost:9090
minikube service spark-ui -n ridesharing                     # Spark UI
```

---

#### Option 4 — Scale 1: Kubernetes on EC2 (5K drivers)

This option prints SSH instructions. Perform these steps on the EC2 instance:

```bash
# 1. SSH into EC2
ssh -i ~/.ssh/ridesharing-key.pem ubuntu@<EC2_IP>

# 2. Install prerequisites on EC2 (first time only)
sudo apt-get update && sudo apt-get install -y docker.io curl
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
mkdir -p ~/bin && mv minikube-linux-amd64 ~/bin/minikube && chmod +x ~/bin/minikube
curl -LO "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
mv kubectl ~/bin/ && chmod +x ~/bin/kubectl
export PATH="$HOME/bin:$PATH"

# 3. Clone repo and set up
git clone https://github.com/amityadav23112000/ridesharing-pipeline.git
cd ridesharing-pipeline
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 4. Start Minikube (EC2 t3.xlarge has 16 GB RAM)
minikube start --cpus=4 --memory=12288 --driver=docker

# 5. Build image and create secrets
eval $(minikube docker-env)
docker build -t ridesharing-pipeline:latest .
kubectl create namespace ridesharing
kubectl create secret generic aws-credentials \
  --from-literal=access-key-id="YOUR_ACCESS_KEY" \
  --from-literal=secret-access-key="YOUR_SECRET_KEY" \
  -n ridesharing

# 6. Deploy
kubectl apply -f k8s/
kubectl wait --for=condition=ready pod --all -n ridesharing --timeout=300s
kubectl get pods -n ridesharing
```

---

#### Option 5 — Scale 2: Kubernetes on EC2 (50K drivers)

Complete Option 4 first, then scale up on the running cluster:

```bash
# On EC2, patch the ConfigMap to switch to 50K drivers
kubectl patch configmap pipeline-config -n ridesharing \
  --type merge \
  -p '{"data":{"NUM_DRIVERS":"50000","SCALE_LEVEL":"50K","WINDOW_SECONDS":"2"}}'

# Restart deployments to pick up new config
kubectl rollout restart deployment -n ridesharing
kubectl rollout status deployment/spark-streaming -n ridesharing
kubectl rollout status deployment/gps-simulator -n ridesharing
kubectl get pods -n ridesharing
```

Alternatively, use the helper script (run from repo root on EC2):
```bash
bash scripts/scale.sh 2
```

---

#### Option 6 — Scale 3: EMR Distributed Spark (50K drivers)

**Prerequisites:**
- AWS CLI configured with EMR permissions
- `venv` activated (`source venv/bin/activate`)
- Kafka must still be running on EC2 from Option 4/5 (Spark on EMR reads from it)

**What it does:** Launches a 3-node EMR cluster (`m5.xlarge` × 3) via `boto3`. The cluster ID is printed — use it to submit the Spark job.

After the cluster starts (takes ~8–10 min):
```bash
# Upload Spark script to S3
aws s3 cp src/spark_streaming_job.py \
  s3://ridesharing-pipeline-h20250060/scripts/spark_streaming_job.py

# Submit Spark job to EMR (replace CLUSTER_ID with output from Option 6)
aws emr add-steps \
  --cluster-id <CLUSTER_ID> \
  --steps Type=Spark,Name=SurgeEngine,ActionOnFailure=CONTINUE,\
Args=[--master,yarn,--deploy-mode,cluster,\
--conf,spark.sql.shuffle.partitions=30,\
s3://ridesharing-pipeline-h20250060/scripts/spark_streaming_job.py] \
  --region ap-south-1
```

Monitor in the AWS console: EMR → Clusters → Steps → View logs.

---

#### Option 7 — View Results & Graphs

```bash
bash scripts/run_experiment.sh
# choose 7
```

**What it does:**
1. Activates the venv
2. Runs `experiments/comparison_table.py` — prints the full scale comparison table to stdout
3. Runs `experiments/generate_graphs.py` — generates 6 PNG graphs in `experiments/graphs/`

**Graphs generated:**
| File | Content |
|------|---------|
| `throughput_comparison.png` | Kafka EPS across all 4 scales |
| `latency_comparison.png` | Avg + P95 latency with 60s SLA line |
| `surge_zones.png` | Active surge zones avg/max per scale |
| `cost_vs_latency.png` | Cost/hr vs avg latency scatter plot |
| `infrastructure_scaling.png` | Dual-axis: EPS bars + latency line |
| `dashboard.png` | 2×2 summary dashboard |

> **Troubleshooting Option 7:** If `generate_graphs.py` fails with `ModuleNotFoundError: No module named 'matplotlib'` or `seaborn`, run `pip install -r requirements.txt` again — both packages were added to the requirements.

---

#### Option 8 — Stop All Services

```bash
# To also stop your EC2 instance, export its ID first:
export EC2_INSTANCE_ID="i-xxxxxxxxxxxxxxxxx"   # from AWS console
bash scripts/run_experiment.sh
# choose 8
```

**What it does:**
- Stops Minikube (`minikube stop`)
- Stops Docker Compose (`docker compose down`)
- Stops the EC2 instance if `EC2_INSTANCE_ID` is set

> **Important:** After Scale 3, terminate the EMR cluster manually to avoid ongoing charges:
> ```bash
> aws emr terminate-clusters --cluster-ids <CLUSTER_ID> --region ap-south-1
> ```

---

### Step 4 — Batch Pipeline (S3 Upload + Glue)

The batch pipeline runs automatically via EventBridge every midnight, but you can trigger it manually:

**Upload synthetic trip data to S3:**
```bash
source venv/bin/activate
python src/batch_uploader.py
# Uploads 1,000 trip records (100 per city × 10 cities) to:
# s3://ridesharing-pipeline-h20250060/raw/trips/city=<X>/date=<YYYY-MM-DD>/trips.csv
```

**Trigger the Step Functions pipeline:**
```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:ap-south-1:276209672013:stateMachine:ridesharing-batch-pipeline \
  --input "{\"process_date\": \"$(date +%Y-%m-%d)\"}" \
  --region ap-south-1
```

**What Step Functions does:**
1. **CheckInputData** — lists the S3 file for today's date
2. **IsDataAvailable** — if file count > 0, proceed; otherwise skip
3. **StartGlueJob** — runs `glue_batch_job.py` which:
   - Reads CSV from `s3://.../raw/trips/city=*/date=<date>/`
   - Computes: driver earnings, zone demand heatmap, city stats, surge effectiveness
   - Writes Parquet to `s3://.../processed/`
   - Updates DynamoDB `zone_demand` table
4. **NotifySuccess / NotifyFailure** — publishes SNS notification

---

### Step 5 — Scale Switching (ConfigMap-driven)

Switch between scales without touching any code:

```bash
# Scale 1: 5K drivers, 2s window
bash scripts/scale.sh 1

# Scale 2: 50K drivers, 2s window
bash scripts/scale.sh 2
```

Or manually patch the ConfigMap:
```bash
kubectl patch configmap pipeline-config -n ridesharing \
  --type merge \
  -p '{"data":{"NUM_DRIVERS":"50000","SCALE_LEVEL":"50K","WINDOW_SECONDS":"5"}}'
kubectl rollout restart deployment -n ridesharing
```

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
- Navigate to: CloudWatch → Dashboards → `RidesharingPipeline`
- Alarms: high latency (> 10s), low throughput (< 10 EPS)
- Log groups: `/aws/lambda/surge-alert`, `/ridesharing/spark-streaming`

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
> For EMR, also run: `aws emr terminate-clusters --cluster-ids <ID> --region ap-south-1`

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
| 12 | `aws_dynamodb_table` | `surge_pricing` (PAY_PER_REQUEST, streams enabled) |
| 13 | `aws_dynamodb_table` | `zone_demand` (PAY_PER_REQUEST) |
| 14 | `aws_iam_role` | `ridesharing-pipeline-h20250060-spark-ec2-role` |
| 15 | `aws_iam_instance_profile` | EC2 instance profile for Spark |
| 16 | `aws_iam_role_policy` | DynamoDB + S3 + CloudWatch permissions |
| 17 | `aws_iam_role` | `ridesharing-pipeline-h20250060-lambda-surge-role` |
| 18 | `aws_iam_role_policy_attachment` | Lambda basic execution |
| 19 | `aws_iam_role_policy` | DynamoDB streams + SNS publish |
| 20 | `aws_lambda_function` | `surge-alert` (Python 3.11, DynamoDB stream trigger) |
| 21 | `aws_lambda_event_source_mapping` | DynamoDB streams → Lambda |
| 22 | `aws_sns_topic` | `ridesharing-surge-alerts` |
| 23 | `aws_cloudwatch_metric_alarm` | High latency (> 10s) — per scale |
| 24 | `aws_cloudwatch_metric_alarm` | Low throughput (< 10 EPS) — per scale |
| 25 | `aws_cloudwatch_log_group` | `/ridesharing/spark-streaming` (14-day retention) |
| 26 | `aws_cloudwatch_dashboard` | `RidesharingPipeline` |
| 27–31 | Additional S3, Glue, Step Functions resources | (see terraform/ files) |

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: matplotlib` or `seaborn` | Missing from venv | `pip install -r requirements.txt` |
| `JAR not found` error in Spark | Wrong `JAR_PATH` env var | Set `JAR_PATH=/path/to/jars` or use `--jars` flag |
| Kafka topics fail to create | Brokers not ready after 45s | Wait longer, then re-run: `docker exec kafka-broker-1 kafka-topics --create ...` |
| `aws-credentials` secret not found | Secret not created before deploy | Run the `kubectl create secret` command in Option 3 prerequisites |
| EMR cluster never reaches WAITING | IAM roles missing | Ensure `EMR_EC2_DefaultRole` and `EMR_DefaultRole` exist in your account |
| Option 8 skips EC2 stop | `EC2_INSTANCE_ID` not set | `export EC2_INSTANCE_ID=i-xxxx` before running |

---

## GitHub Repository

[https://github.com/amityadav23112000/ridesharing-pipeline](https://github.com/amityadav23112000/ridesharing-pipeline)

```bash
git clone https://github.com/amityadav23112000/ridesharing-pipeline.git
```
