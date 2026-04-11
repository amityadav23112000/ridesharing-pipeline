# Ridesharing Pipeline — Real-Time Surge Pricing Engine

A production-grade streaming data pipeline that processes GPS events from 5,000+ drivers in real time, detects demand surges by zone, and writes surge multipliers to DynamoDB — all within a 5-second window.

## Architecture

```
GPS Simulator (5K drivers)
        │
        ▼  (3 priority topics)
  Kafka Cluster (3 brokers)
  gps-critical / gps-surge / gps-normal
        │
        ▼
  Spark Structured Streaming
  (5s windowed aggregation per zone)
        │
        ├──▶ DynamoDB (surge_pricing table)
        ├──▶ CloudWatch Metrics (RidesharingPipeline namespace)
        └──▶ Prometheus + Grafana (real-time dashboard)
```

## Tech Stack

| Layer | Technology |
|---|---|
| Event source | Python GPS Simulator (kafka-python) |
| Message bus | Apache Kafka 3.6 (3-broker cluster) |
| Stream processing | Apache Spark 3.5.1 Structured Streaming |
| Storage | AWS DynamoDB (PAY_PER_REQUEST) |
| Monitoring | Prometheus + Grafana |
| Orchestration | Kubernetes (minikube / EKS) |
| Infrastructure | Terraform (AWS) |
| Metrics | AWS CloudWatch |

## Project Structure

```
ridesharing-pipeline/
├── src/
│   ├── gps_simulator.py         # GPS event producer (5K drivers, 3 Kafka topics)
│   ├── spark_streaming_job.py   # Spark Structured Streaming surge engine
│   ├── batch_uploader.py        # Historical batch uploader
│   └── glue_batch_job.py        # AWS Glue ETL job
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml           # Pipeline env config (WINDOW_SECONDS, KAFKA_BROKERS…)
│   ├── zookeeper-statefulset.yaml
│   ├── kafka-statefulset.yaml   # 3-broker Kafka cluster
│   ├── gps-simulator-deployment.yaml
│   ├── spark-streaming-deployment.yaml
│   └── monitoring.yaml          # Prometheus + Grafana (NodePort 30090 / 30030)
├── terraform/                   # AWS resources (DynamoDB, S3, IAM, CloudWatch)
├── config/
│   ├── docker-compose.yml       # Local dev stack
│   ├── prometheus.yml           # Prometheus scrape config
│   └── grafana_dashboard.json   # Pre-built Grafana dashboard
├── experiments/
│   └── scale1_k8s_results.py   # Scale 1 benchmark results
├── infrastructure/
│   ├── cloudwatch_dashboard.py
│   └── scale_config.sh
├── lambda/
│   └── surge_alert.py           # CloudWatch alarm → SNS Lambda
├── step_functions/
│   └── batch_pipeline.json      # AWS Step Functions definition
└── requirements.txt
```

## How to Run Locally (Docker Compose)

```bash
cd config
docker-compose up -d
# GPS simulator + Kafka + Spark all start automatically
```

## How to Run on Kubernetes (minikube)

```bash
# 1. Start minikube
minikube start --driver=docker --cpus=4 --memory=6144

# 2. Build image inside minikube's Docker daemon
eval $(minikube docker-env)
docker build -t ridesharing-pipeline:latest .

# 3. Apply manifests in order
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/zookeeper-statefulset.yaml
kubectl apply -f k8s/kafka-statefulset.yaml
kubectl apply -f k8s/gps-simulator-deployment.yaml
kubectl apply -f k8s/spark-streaming-deployment.yaml
kubectl apply -f k8s/monitoring.yaml

# 4. Wait for all pods
kubectl wait --for=condition=ready pod --all -n ridesharing --timeout=300s

# 5. Create Kafka topics (first time only)
kubectl exec -n ridesharing kafka-broker-0 -- \
  kafka-topics --bootstrap-server localhost:9092 --create \
  --topic gps-critical --partitions 3 --replication-factor 3
# repeat for gps-surge, gps-normal

# 6. Access UIs
minikube ip   # e.g. 192.168.49.2
# Grafana:    http://<ip>:30030  (admin / ridesharing123)
# Prometheus: http://<ip>:30090
# Spark UI:   http://<ip>:30404
```

## How to Run Terraform

```bash
cd terraform

# First time: import existing AWS resources
terraform init
terraform import aws_dynamodb_table.surge_pricing surge_pricing
terraform import aws_dynamodb_table.driver_status driver_status
terraform import aws_dynamodb_table.zone_demand zone_demand
terraform import aws_s3_bucket.pipeline_bucket ridesharing-pipeline-h20250060

# Plan and apply
terraform plan
terraform apply
```

## Scale Experiments Results

| Metric | Scale 1 (5K drivers, minikube) |
|---|---|
| Infrastructure | Laptop — 4 CPU, 6 GB RAM |
| Orchestration | Kubernetes (minikube) |
| Kafka EPS (avg) | **1,006.6 events/s** |
| Events per batch | ~5,033 |
| Window size | 5 seconds |
| Zones processed/batch | 148 |
| Active surge zones (avg) | 75 / 148 |
| Avg demand ratio | 1.48x |
| Avg E2E latency | 31.0s |
| P95 latency | 41.9s (max 57.6s) |
| P99 latency | 44.2s (max 66.2s) |
| Fault recovery time | **50 seconds** |
| Data loss on broker failure | **0 events** |
| Availability | 100% |
| Cost | **$0.00/hr** |

### Fault Tolerance Test (2026-04-11)

- Deleted `kafka-broker-0` pod mid-stream
- Kubernetes restarted it in **50 seconds**
- Spark continued processing via the 2 remaining brokers — **zero interruption**
- DynamoDB grew by 911 records during the 50-second outage window
- Zero data loss confirmed

## Key Design Decisions

1. **Priority topic routing** — drivers send to `gps-critical`, `gps-surge`, or `gps-normal` based on their zone demand ratio. Spark reads all three simultaneously.
2. **Env-driven window size** — `WINDOW_SECONDS` is a ConfigMap value; no code change needed to tune it.
3. **Idempotent DynamoDB writes** — each row keyed by `zone_id + unique_timestamp` to avoid double-writes on Spark retry.
4. **Prometheus sidecar** — `prometheus_client` exposes live metrics on port 8001 without a separate container.

## GitHub

[amityadav23112000/ridesharing-pipeline](https://github.com/amityadav23112000/ridesharing-pipeline)
