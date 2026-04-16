# Architecture & Design Document
## CSG527 Cloud Computing — Ridesharing Pipeline
### Student: H20250060 | Date: April 2026

---

## 1. Problem Statement

Ridesharing companies such as Ola and Uber receive continuous GPS location updates from thousands of active drivers. The business must respond to supply-demand imbalances within seconds: when many riders request a ride in one zone but few drivers are nearby, surge pricing must activate immediately. If the system is slow, drivers go to the wrong zones, riders wait longer, and revenue is lost.

At the same time, the company needs daily batch analytics — how much did drivers earn, which cities had the most surge events, what does the cost-per-trip look like — to support finance, operations, and product decisions.

The challenge is that these two needs have opposite characteristics: the real-time pipeline must be fast (< 5 seconds end-to-end), while the batch pipeline prioritises completeness and cost over speed. A single system trying to serve both usually fails at one or both.

---

## 2. Success Metrics

| # | Metric | Target | How measured |
|---|--------|--------|--------------|
| 1 | **Data processing delay** | < 5 seconds end-to-end (sub-5s SLA) | p95 latency from GPS event timestamp to DynamoDB write |
| 2 | **Traffic spike resilience** | Handle 10× driver increase without data loss | Kafka offset lag stays bounded; no DLQ messages |
| 3 | **Cost efficiency** | Cost per GB processed decreases with optimisation | CloudWatch cost metrics; conditional batch skip at low load |

---

## 3. Architecture Decision: Hybrid Lambda Architecture

### Why Hybrid (stream + batch)?

- GPS events need instant decisions → **stream processing**
- Daily earnings / analytics can wait hours → **batch processing**
- Both are needed → **Hybrid Lambda Architecture** (coined by Nathan Marz)

The Lambda Architecture separates concerns cleanly: the speed layer handles latency-sensitive workloads, the batch layer handles completeness and cost. A serving layer (DynamoDB) merges both views for downstream consumers.

### Architecture Diagram

```
                          ┌─────────────────────────────────────────────────┐
GPS Devices               │  INGESTION LAYER                                │
(50K drivers)  ─────────► │  ┌─────────────┐  ┌──────────────────────────┐ │
                          │  │ REST/IoT    │  │  Kafka 3-tier Topics     │ │
REST clients   ─────────► │  │ Endpoint    │─►│  gps-normal  (16 part.)  │ │
(FR1.3)                   │  │ :8080       │  │  gps-surge   (16 part.)  │ │
                          │  └─────────────┘  │  gps-critical (8 part.)  │ │
                          └──────────────────────────────────────────────┬──┘
                                                                         │
                    ┌────────────────────────────────────────────────────┼──────────────────┐
                    │  SPEED LAYER (< 5s SLA)                            │                  │
                    │  ┌─────────────────────────────────┐               │                  │
                    │  │  Spark Structured Streaming     │◄──────────────┘                  │
                    │  │  • Adaptive window (2s–10s)     │                                  │
                    │  │  • Stream-stream join           │                                  │
                    │  │  • Watermark / late data        │                                  │
                    │  │  • K8s local[*] + HPA           │                                  │
                    │  └────────────────┬────────────────┘                                  │
                    │                   │                                                    │
                    │        ┌──────────┴──────────┐                                        │
                    │        ▼                     ▼                                        │
                    │  ┌──────────────┐    ┌──────────────┐                                 │
                    │  │  DynamoDB    │    │  S3 Raw      │                                 │
                    │  │  surge-      │    │  Data Lake   │─────────────────────────────────►
                    │  │  pricing     │    │  (Parquet)   │    BATCH LAYER                  │
                    │  │  (hot store) │    └──────────────┘    ┌─────────────────────────┐  │
                    │  └──────┬───────┘                        │  AWS Glue ETL Job       │  │
                    │         │ DynamoDB Stream                │  (glue_batch_job.py)    │  │
                    │         ▼                                │  • Parquet output       │  │
                    │  ┌──────────────┐                        │  • Aggregations         │  │
                    │  │  Lambda      │                        └─────────┬───────────────┘  │
                    │  │  surge_alert │                                  │ Glue Crawler      │
                    │  │  → SNS       │                                  ▼                  │
                    │  └──────────────┘                        ┌─────────────────────────┐  │
                    └────────────────────────────────────────► │  Athena + Data Catalog  │  │
                                                               │  6 analytical queries   │  │
                                                               │  HTML dashboard         │  │
                                                               └─────────────────────────┘  │
                                                                                             │
                    ┌────────────────────────────────────────────────────────────────────────┘
                    │  ORCHESTRATION / OBSERVABILITY
                    │  • Step Functions — hourly batch trigger
                    │  • Airflow DAG — alternative orchestration (MWAA)
                    │  • Terraform — full IaC for all resources
                    │  • Prometheus + Grafana — real-time metrics
                    │  • CloudWatch — AWS-native metrics + dashboard
                    └───────────────────────────────────────────
```

---

## 4. Technology Stack Decisions

| Layer | Tool | Why chosen | Alternative considered |
|-------|------|-----------|----------------------|
| **Ingestion REST** | FastAPI | Async, OpenAPI docs, low latency | Flask (slower), Kong (overkill) |
| **Message Queue** | Kafka 3.5.0 | High throughput, replay, 3-tier priority | Kinesis ($$ at scale), RabbitMQ (no replay) |
| **Stream Processing** | Spark Structured Streaming | Unified batch+stream API, mature | Flink (harder ops), Kafka Streams (JVM only) |
| **Batch ETL** | AWS Glue | Serverless, managed, native S3/Catalog | EMR (overkill for batch), Databricks (cost) |
| **Hot Storage** | DynamoDB | Single-digit ms reads, auto-scale | Redis (no persistence), Aurora (too slow) |
| **Cold Storage** | S3 + Parquet | Cheap ($0.023/GB), durable, columnar | GCS (not on AWS), EFS (10× more expensive) |
| **Analytics** | Athena | Pay-per-scan, no servers, SQL | Redshift (provisioned cost), BigQuery (not AWS) |
| **Orchestration** | Step Functions + Airflow DAG | Managed state, visual monitoring | Cron (no retry/alerting) |
| **Container Scaling** | Kubernetes HPA | CPU-based auto-scale, declarative | ECS (less portable), manual scaling |
| **IaC** | Terraform | Multi-resource, state management, modules | CloudFormation (verbose), CDK (Python-heavy) |
| **Monitoring** | Prometheus + Grafana | Custom metrics, visual dashboards | CloudWatch only (less flexible) |

---

## 5. Data Flow (Step by Step)

| Step | Component | Action |
|------|-----------|--------|
| 1 | GPS Simulator / REST endpoint | Produces events `{driver_id, lat, lon, speed, status}` to Kafka |
| 2 | Kafka classifier | Routes events to `gps-normal`, `gps-surge`, or `gps-critical` based on demand |
| 3 | Spark reads all 3 topics | Subscribed with `KAFKA_TOPICS` env var; reads in parallel |
| 4 | Schema evolution | v1 events upgraded to v2 (`zone_id`, `vehicle_type`, `event_time`) |
| 5 | Adaptive windowing | `WINDOW_SECONDS = max(2, drivers÷1000)` — small window at low load |
| 6 | Stream-stream join | GPS events joined with driver-status-updates on `driver_id` ± 30s |
| 7 | Windowed aggregation | Counts waiting/available per zone, computes `demand_ratio` |
| 8 | Surge detection | If `demand_ratio ≥ 1.5`, emit surge event with multiplier |
| 9 | DynamoDB write | Surge pricing record written (hot path, < 5s from GPS event) |
| 10 | S3 write | Raw + processed events written to S3 data lake (cold path) |
| 11 | Lambda trigger | DynamoDB Stream → Lambda detects `surge_multiplier ≥ 2.0` → SNS alert |
| 12 | Glue batch job | Hourly: reads S3, aggregates, writes Parquet to `s3://.../processed/` |
| 13 | Glue Crawler | Updates Data Catalog schema after each Glue run |
| 14 | Athena queries | Business analysts run SQL queries on Parquet (no servers needed) |
| 15 | Step Functions | Orchestrates steps 12–14 on schedule; SNS on success/failure |

---

## 6. Non-Functional Design Decisions

### Scalability
- **HPA**: Kubernetes Horizontal Pod Autoscaler scales Spark pods 1→8 on CPU ≥ 70%
- **EMR dynamic allocation**: For 50K+ drivers, `--num-executors` scales automatically with YARN
- **Kafka partitions**: 16 per topic → supports 16 parallel consumers without rebalancing

### Latency
- **Adaptive window**: 2s window at 500 drivers → 10s window at 50K drivers
  - Eliminates unnecessary micro-batch overhead at small scale
  - Prevents unbounded latency growth at large scale
- **maxOffsetsPerTrigger**: Caps Kafka read per batch to prevent memory spikes

### Reliability
- **Kafka replication factor = 3**: Survives 2 broker failures without data loss
- **Spark checkpoints**: `/tmp/spark-checkpoints/` — restart resumes from last committed offset
- **DLQ (Dead Letter Queue)**: Malformed events routed to `gps-dead-letters` topic
- **Lambda retries**: 3 retries with exponential backoff for DynamoDB Stream processing

### Cost
- **Conditional batch skip**: Glue job skips processing if S3 input < 1MB (no new data)
- **Spot instances**: EMR core nodes use Spot for 60-80% cost reduction
- **DynamoDB PAY_PER_REQUEST**: No provisioned capacity waste at variable load
- **Athena**: Only pay for bytes scanned; 10 GB cutoff per query prevents accidents

---

## 7. Security Considerations

- **IAM roles** per service (Lambda, Glue, Spark EC2) — principle of least privilege
- **S3 bucket policy**: Denies public access; KMS encryption at rest
- **DynamoDB encryption**: AWS-managed keys (SSE)
- **VPC**: Kafka and Spark run in private subnet; only bastion host has public IP
- **Secrets**: No hardcoded credentials; all via environment variables or IAM roles
