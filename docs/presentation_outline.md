# Presentation Outline
## CSG527 Cloud Computing — Ridesharing Pipeline
### Student: H20250060 | Presentation: April 2026

---

## Slide Structure (15 minutes total)

---

### Slide 1: Title (30s)
**Title**: Intelligent, Cost-Aware Cloud Data Pipeline for Ridesharing
**Subtitle**: Real-time Surge Pricing + Batch Analytics on AWS

Key points to mention:
- CSG527 Cloud Computing project
- Lambda Architecture: stream + batch
- 8 experiments across 3 infrastructure tiers

---

### Slide 2: Problem Statement (1 min)
**Title**: The Challenge

Diagram: GPS device → problem split
- LEFT: "< 5 seconds" — surge pricing must happen NOW
- RIGHT: "Daily analytics" — batch can wait hours

Key points:
- 50K active drivers sending GPS every ~2s
- Supply-demand imbalance → surge pricing
- Two workloads with opposite characteristics
- **One architecture to serve both**

---

### Slide 3: Architecture Overview (2 min)
**Title**: Hybrid Lambda Architecture

Show: docs/architecture_design.md ASCII diagram (screenshot or recreate in slide)

Walk through layers:
1. **Ingestion**: FastAPI REST endpoint → Kafka 3-tier topics
2. **Speed layer**: Spark Structured Streaming → DynamoDB (hot store)
3. **Batch layer**: S3 Data Lake → Glue ETL → Athena analytics
4. **Orchestration**: Step Functions (hourly) + Airflow DAG
5. **Observability**: Prometheus + Grafana + CloudWatch

Point to: architecture reflects real Uber/Ola production patterns

---

### Slide 4: Key Innovations (1.5 min)
**Title**: 3 Design Innovations

**Innovation 1: Adaptive Window Sizing**
- Formula: `WINDOW_SECONDS = max(2, drivers ÷ 1000)`
- ConfigMap-driven — live adjustment without Spark restart
- Result: **−49% latency** at 500 drivers vs fixed 5s window

**Innovation 2: Three-Tier Kafka Topics**
- gps-normal / gps-surge / gps-critical
- REST endpoint classifies at ingestion time
- Critical events never wait behind routine GPS pings

**Innovation 3: Schema Evolution + Lineage**
- v1→v2 upgrade without breaking consumers
- DynamoDB lineage table: full audit trail of schema upgrades

---

### Slide 5: Live Demo — Grafana Dashboard (3 min)
**Title**: Real-Time Metrics Demo

Run: `bash scripts/demo.sh` (pre-started before presentation)

Show in Grafana (http://localhost:3000):
1. **EPS panel**: 0 → rising after GPS simulator starts
2. **Latency panel**: < 5s SLA line at 500 drivers
3. **Surge zones panel**: heatmap lighting up as demand spikes
4. **Scale transition**: 1K → 5K drivers, adaptive window changes

Screenshots to show if live demo not available:
- SS-BASELINE-01: 500 drivers, EPS ~60, latency < 5s
- SS-SCALE2-01: 5K drivers, EPS ~470, surge zones active

---

### Slide 6: Benchmarking Results (2 min)
**Title**: Performance Across 8 Experiments

Show: experiments/graphs/02_latency_distribution.png

Key data points (from summary_statistics.csv):

| Scale | p95 Latency | SLA |
|-------|-------------|-----|
| 500 drivers | 4,328ms | ✓ PASS |
| 1K drivers | 3,813ms | ✓ PASS |
| 5K drivers (EC2) | 6,147ms | ~ NEAR |
| 50K drivers (EMR) | 132,500ms | ✗ FAIL |

Explain 50K failure: input rate (5,000 EPS) > processing rate (2,045 EPS) → Kafka backlog grows → events arrive already-old. **Fix**: scale EMR to 8+ executors.

---

### Slide 7: Cost Analysis (1.5 min)
**Title**: Cost Efficiency

Show: experiments/graphs/05_cost_efficiency.png

Key finding:
- EC2 t3.xlarge: $0.20/hr → **9,184 EPS per dollar**
- EMR 4-node: $1.25/hr → **1,637 EPS per dollar** (6× more expensive, 11% more throughput)
- **Recommendation**: Use EC2 spot ($0.04/hr) up to 50K drivers, EMR only at 200K+

Cost savings implemented:
- Conditional Glue batch skip (empty S3 → no job launch)
- DynamoDB PAY_PER_REQUEST (no idle provisioned capacity)
- Athena 10 GB scan limit (prevents runaway queries)

---

### Slide 8: Fault Tolerance Demo (1.5 min)
**Title**: Fault Recovery

Show: SS-FAULT-DEMO-01 + SS-FAULT-DEMO-02 side by side

Timeline:
1. `kill -9 $SPARK_PID` → EPS drops to 0
2. Grafana shows gap (screenshot SS-FAULT-DEMO-01)
3. Restart Spark → reads checkpoint → replays Kafka
4. EPS recovers within ~30s (local) / ~145s (EC2)
5. **Zero events lost** (Kafka 7-day retention)

Mechanism: Spark checkpoint stores last committed Kafka offsets. Restart resumes exactly where it stopped.

---

### Slide 9: Batch Analytics — Athena Dashboard (1.5 min)
**Title**: Batch Layer — Athena Analytics

Open: docs/athena_dashboard.html in browser

Walk through 6 panels:
1. Top Surge Zones — bar chart of demand_ratio by city
2. Latency Percentiles — p50/p95/p99 across experiments
3. Cost per GB — efficiency comparison
4. City Utilization Heatmap — driver on-trip rate
5. Driver Earnings (24h) — per-driver revenue analysis
6. Pipeline Health — batch run success rate

Show: Step Functions execution graph — Glue → Crawler → Athena → SNS

---

### Slide 10: Conclusions & Future Work (1 min)
**Title**: Conclusions

**Achieved**:
- Sub-5s SLA at ≤ 1K drivers on commodity hardware
- 8 experiments across 3 infrastructure tiers
- Full AWS production deployment (Terraform IaC)
- Prometheus + Grafana + CloudWatch observability
- Fault recovery < 30s with zero data loss

**Limitations**:
- 50K throughput gap (input rate > processing rate)
- EMR not cost-efficient vs EC2 at current scale

**Future work** (30 seconds):
- Continuous processing mode (500ms trigger) for < 1s latency
- Flink for surge detection hot path
- ML-based predictive surge pricing

---

### Slide 11: Q&A (live)

**Anticipated questions and answers**:

**Q: Why Spark over Flink?**
A: Unified API with batch layer (Glue is also Spark), mature PySpark, and the 5s SLA has enough budget for micro-batch. Flink would be considered if SLA < 500ms.

**Q: How does schema evolution handle breaking changes?**
A: `schema_evolution.py` versioned upgrade functions — v1 events are upgraded to v2 at read time, v2 fields derived from available v1 data. Breaking changes require a new schema version with a migration period.

**Q: What happens when Kafka goes down?**
A: FastAPI REST endpoint queues incoming requests in memory (configurable buffer). Kafka brokers have RF=3, so 2 of 3 can fail without data loss. Full Kafka outage > buffer capacity would require upstream backpressure (HTTP 503 to GPS clients).

**Q: Is this cost-effective vs managed services?**
A: Self-managed Kafka + EC2 Spot achieves ~15× lower cost than Kinesis + Lambda at 50K events/second. Trade-off: engineering overhead for Kafka cluster management.

---

## Demo Checklist (run before presentation)

```bash
# T-5 minutes before demo
docker compose -f config/docker-compose.yml up -d   # Start Kafka + Prometheus
cd monitoring && docker compose up -d                # Start Grafana

# Verify services
curl http://localhost:8080/health    # FastAPI REST endpoint
curl http://localhost:9090/-/ready   # Prometheus
# Open http://localhost:3000         # Grafana (admin/admin)

# Pre-start Spark (so it's already collecting data when demo starts)
WINDOW_SECONDS=2 DRIVER_COUNT=500 \
  spark-submit --master local[4] \
    --jars jars/spark-sql-kafka.jar,jars/kafka-clients.jar,\
jars/commons-pool2.jar,jars/spark-token-provider-kafka.jar \
    src/spark_streaming_job.py &

# Open Athena dashboard
xdg-open docs/athena_dashboard.html
```

**Backup screenshots** (if live demo fails):
- `experiments/graphs/` — all 10 benchmark graphs
- Screenshots captured during experiments (SS-BASELINE-*, SS-SCALE*, SS-FAULT-*)
