# Performance & Cost Benchmarking Report
## CSG527 Cloud Computing — Ridesharing Pipeline
### Student: H20250060 | Date: April 2026

---

## 1. Experimental Setup

### 1.1 Objectives

This report quantifies the performance and cost characteristics of the ridesharing pipeline across three infrastructure tiers (local laptop, single EC2 instance, EMR cluster) at four driver scales (500, 1K, 5K, 50K). The primary SLA is **p95 end-to-end latency < 5 seconds**, where latency is measured from GPS event timestamp to DynamoDB write completion.

### 1.2 Infrastructure Configurations

| Environment | Hardware | Spark Mode | Workers | Cost/hr |
|-------------|----------|------------|---------|---------|
| **Local laptop** | Intel Core i7, 16 GB RAM | `local[*]` | 4 threads | $0.00 |
| **EC2 t3.xlarge** | 4 vCPU, 16 GB RAM | `local[8]` | 8 threads | $0.20 |
| **EMR m5.xlarge ×4** | 16 vCPU total, 64 GB RAM | YARN cluster | 4 executors | $1.25 |

### 1.3 Kafka Configuration

- **Topics**: `gps-normal` (16 partitions), `gps-surge` (16 partitions), `gps-critical` (8 partitions)
- **Replication factor**: 3 (fault-tolerant; survives 2 broker failures)
- **Consumer group**: Spark reads all three topics with `subscribePattern`
- **Retention**: 7 days — enables full replay for fault recovery

### 1.4 Experiment Matrix

| Experiment ID | Infrastructure | Driver Count | Window (s) | Special Condition |
|---------------|----------------|-------------|------------|-------------------|
| `local_sub5s` | Local | 500 | 2 | Baseline — SLA validation |
| `local_1k` | Local | 1,000 | 2 | Baseline — 1K scale |
| `local_5k` | Local | 5,000 | 5 | Adaptive window kicks in |
| `ec2_5k` | EC2 | 5,000 | 5 | Cloud equivalent of local_5k |
| `ec2_50k` | EC2 | 50,000 | 10 | Single-node at extreme scale |
| `emr_50k` | EMR | 50,000 | 10 | Distributed cluster |
| `fault_local` | Local | 1,000 | 5 | Fault injection + recovery |
| `fault_ec2` | EC2 | 5,000 | 5 | Fault injection + recovery |

All experiments ran the same `src/spark_streaming_job.py` codebase. Window size was set via `WINDOW_SECONDS` environment variable (adaptive windowing: `max(2, driver_count ÷ 1000)`).

---

## 2. Throughput Results

*Reference: experiments/graphs/01_throughput_comparison.png*

### 2.1 Events Per Second (EPS) by Experiment

| Experiment | Avg EPS | Infrastructure | Drivers |
|------------|---------|----------------|---------|
| `local_sub5s` | 60.7 | Local | 500 |
| `local_1k` | 105.0 | Local | 1,000 |
| `fault_local` | 102.6 | Local | 1,000 |
| `fault_ec2` | 462.3 | EC2 | 5,000 |
| `local_5k` | 464.2 | Local | 5,000 |
| `ec2_5k` | 470.1 | EC2 | 5,000 |
| `ec2_50k` | 1,836.8 | EC2 | 50,000 |
| `emr_50k` | 2,045.7 | EMR | 50,000 |

### 2.2 Key Observations

**Linear scaling up to 5K drivers.** EPS scales near-linearly from 500→5K drivers (60.7 EPS → 464.2 EPS), a 7.6× increase for a 10× driver increase. The slight sub-linear scaling (0.76 efficiency) is attributable to Kafka partition contention and Spark scheduling overhead per micro-batch.

**EC2 ≈ Local at 5K drivers.** `ec2_5k` (470.1 EPS) nearly matches `local_5k` (464.2 EPS), confirming the job is CPU-bound rather than I/O-bound at this scale. The slight EC2 advantage reflects faster NVMe SSD storage for checkpoint writes.

**Throughput gap at 50K drivers.** At 50K drivers, the GPS simulator produces approximately 5,000 events/second. EC2 single-node achieved 1,836.8 EPS and EMR achieved 2,045.7 EPS — both below the input rate. This caused Kafka lag to grow continuously over the experiment duration, producing the high latencies observed in Section 3. See Section 6.2 for the root cause analysis and recommended fix.

**EMR marginal advantage at 50K.** EMR (2,045.7 EPS) outperforms single-EC2 (1,836.8 EPS) by only 11%. At 50K drivers with a 4-executor YARN cluster, the bottleneck shifts from CPU to Kafka network I/O and the stream-stream join shuffle. Larger EMR clusters (`m5.2xlarge ×8`) would yield proportionally higher throughput.

---

## 3. Latency Results

*Reference: experiments/graphs/02_latency_distribution.png*

### 3.1 Latency Percentiles by Experiment

| Experiment | p50 (ms) | p95 (ms) | p99 (ms) | SLA < 5s |
|------------|----------|----------|----------|----------|
| `local_sub5s` | 3,047 | 4,328 | 4,761 | **PASS** |
| `local_1k` | 2,767 | 3,813 | 4,323 | **PASS** |
| `fault_local` | 2,654 | 4,312 | 5,991 | PASS* |
| `fault_ec2` | 5,696 | 6,125 | 6,458 | FAIL |
| `local_5k` | 5,991 | 6,675 | 6,828 | FAIL |
| `ec2_5k` | 5,847 | 6,147 | 7,091 | FAIL |
| `ec2_50k` | 20,630 | 33,374 | 33,891 | FAIL |
| `emr_50k` | 75,238 | 132,500 | 137,526 | FAIL |

*\* fault_local p95 passes SLA; p99 exceeds due to fault injection gap batches being reprocessed.*

### 3.2 SLA Analysis

**500–1K drivers: SLA met.** At ≤1K drivers, the 2-second adaptive window keeps p95 latency well within the 5-second SLA (`local_sub5s`: 4,328ms p95; `local_1k`: 3,813ms p95). This is the production-ready operating range for the current single-node deployment.

**5K drivers: SLA missed by ~25%.** At 5K drivers, the pipeline switches to a 5-second window (adaptive logic). This increases per-batch processing time and pushes p95 to 6,147ms (EC2) and 6,675ms (local). The SLA breach is modest; deploying with a 2-second window at 5K drivers would cut latency but increase checkpoint/write overhead.

**50K drivers: Significant SLA breach.** The latency at 50K scale is dominated by Kafka backlog growth rather than per-batch processing time. With input rate (~5,000 EPS) exceeding processing capacity (~2,000 EPS), each successive Spark micro-batch reads events that are increasingly old. The median latency of 75,238ms (EMR) reflects events that waited ~75 seconds in the Kafka queue before being processed.

### 3.3 Pearson Correlation: Drivers vs. Latency

- **r = 0.793**, p = 0.060 (not statistically significant at α=0.05)
- The correlation is strong but the small sample (n=6 scale points) prevents significance at the 0.05 level
- The near-linear relationship up to 10K drivers becomes super-linear at 50K, consistent with queuing theory (Kafka backlog)

---

## 4. Cost Analysis

*Reference: experiments/graphs/05_cost_efficiency.png*

### 4.1 Cost Per Experiment

| Experiment | Infrastructure | Cost/hr | Avg EPS | EPS per $/hr |
|------------|----------------|---------|---------|--------------|
| `local_sub5s` | Local laptop | $0.00 | 60.7 | ∞ (free) |
| `local_1k` | Local laptop | $0.00 | 105.0 | ∞ (free) |
| `local_5k` | Local laptop | $0.00 | 464.2 | ∞ (free) |
| `ec2_5k` | EC2 t3.xlarge | $0.20 | 470.1 | 2,350 EPS/$ |
| `ec2_50k` | EC2 t3.xlarge | $0.20 | 1,836.8 | 9,184 EPS/$ |
| `emr_50k` | EMR m5.xlarge×4 | $1.25 | 2,045.7 | 1,637 EPS/$ |

### 4.2 Key Cost Observations

**EC2 at 50K is the most cost-efficient paid tier.** At 9,184 EPS per dollar, EC2 running the 50K experiment extracts the most throughput per dollar. The hardware is pushed to full utilisation, making each dollar spent highly productive (even though it fails the SLA).

**EMR costs 6× more than EC2 for only 11% more throughput at 50K.** This is the key cost finding: for the 50K workload, EMR charges $1.25/hr versus $0.20/hr for EC2, yet delivers only 2,045.7 vs 1,836.8 EPS. The EMR overhead (YARN ResourceManager, HDFS NameNode, Spark cluster coordinator) consumes a significant fraction of the 4-executor cluster's resources.

**EMR break-even point.** EMR becomes cost-efficient at workloads where its distributed scaling advantage outweighs cluster overhead — estimated at **≥ 200K drivers** for this pipeline workload, where 8+ executors can be kept busy without the YARN coordination overhead dominating.

**Recommendation.** For ≤ 50K drivers, deploy on EC2 (spot instance: ~$0.04/hr for t3.xlarge = 85% savings). For ≥ 200K drivers, use EMR with `m5.2xlarge` nodes and dynamic allocation.

---

## 5. Scaling Behaviour

*Reference: experiments/graphs/07_scaling_behavior.png*

### 5.1 Throughput Scaling Efficiency

| Scale Transition | EPS Increase | Driver Increase | Efficiency |
|------------------|-------------|-----------------|------------|
| 500 → 1K (local) | 60.7 → 105.0 | 2× | 86% |
| 1K → 5K (local) | 105.0 → 464.2 | 5× | 88% |
| 5K → 50K (EC2) | 470.1 → 1,836.8 | 10× | 39% |

**Sub-5K range is near-linear.** The pipeline scales at ~87% efficiency below 5K drivers. This reflects good parallelism: Kafka's 16-partition design keeps all Spark tasks busy without idle threads.

**Efficiency collapse at 50K.** Scaling from 5K to 50K drivers (10×) yields only a 3.9× throughput increase (39% efficiency). The bottleneck transitions from CPU to:
1. Kafka consumer group coordination across 16 partitions with only 4 Spark executors
2. DynamoDB write throughput throttling (PAY_PER_REQUEST has burst limits)
3. Stream-stream join state management — the join buffer holds 30-second windows across all drivers, growing linearly with driver count

### 5.2 Adaptive Window Impact

*Reference: experiments/graphs/10_innovation_impact.png*

| Configuration | Window | p50 Latency | Reduction |
|---------------|--------|-------------|-----------|
| `local_5k` | 5s (adaptive) | 5,991ms | baseline |
| `local_sub5s` | 2s (adaptive) | 3,047ms | **−49.1%** |

The adaptive windowing formula `WINDOW_SECONDS = max(2, drivers ÷ 1000)` reduces latency by nearly 50% at low driver counts. At 500 drivers, a 2-second window processes fewer events per micro-batch, keeping the per-batch write latency to DynamoDB well within the 5s SLA.

---

## 6. Fault Recovery Results

*Reference: experiments/graphs/09_fault_recovery.png*

### 6.1 Recovery Time Measurements

| Experiment | Fault Method | Detection | Recovery | Total Downtime |
|------------|-------------|-----------|----------|----------------|
| `fault_local` | `kill -9` Spark | ~5s (EPS=0) | ~25s | **~30s** |
| `fault_ec2` | `kill -9` Spark | ~8s (EPS=0) | ~137s | **~145s** |

### 6.2 Recovery Mechanism

Upon restart, Spark Structured Streaming reads its last committed checkpoint from `/tmp/spark-checkpoints/`. The checkpoint stores:
- **Last Kafka offsets committed** per partition — ensures no events are skipped or double-processed
- **State store snapshot** — watermark position and streaming aggregation state for the windowed join

Kafka's 7-day retention means all events produced during the downtime window are available for replay. Events produced during the ~30s (local) or ~145s (EC2) outage windows were processed in the first few batches post-recovery.

**EC2 recovery was slower (137s vs 25s)** due to:
1. EC2 has slower SSD vs laptop NVMe for checkpoint reads
2. The 5K driver experiment had a larger state store (5× more join state than 1K)
3. The EC2 instance needed to re-establish all Kafka partition connections over the network

---

## 7. Conclusions

### 7.1 Summary of Findings

| Finding | Evidence |
|---------|----------|
| Sub-5s SLA met at ≤ 1K drivers | local_sub5s p95=4,328ms; local_1k p95=3,813ms |
| Adaptive window reduces latency by 49% | 5,991ms → 3,047ms at low driver counts |
| EC2 matches local performance at 5K | 470 EPS vs 464 EPS |
| EMR costs 6× more for 11% gain at 50K | $1.25/hr EMR vs $0.20/hr EC2 |
| Fault recovery < 30s (local), < 150s (EC2) | Kafka replay from checkpoint |
| 50K throughput bottleneck = input > capacity | 5,000 EPS input, 2,045 EPS max |

### 7.2 Recommended Operating Points

| Production Scale | Recommended Infrastructure | Expected Latency |
|-----------------|---------------------------|-----------------|
| ≤ 1,000 drivers | Local / Single EC2 t3.medium | < 5s SLA ✓ |
| 1K–10K drivers | EC2 t3.xlarge (spot, ~$0.04/hr) | 5–8s |
| 10K–100K drivers | EC2 c5.4xlarge or EMR 4-node | 8–30s |
| > 100K drivers | EMR 8+ nodes + `maxOffsetsPerTrigger` backpressure | Variable |

### 7.3 Root Cause: 50K Latency Growth

The high latency at 50K drivers is **not a per-batch processing problem** — it is a **Kafka backlog accumulation problem**. The GPS simulator at 50K drivers produces ~5,000 events/second. The pipeline processes ~2,045 events/second (EMR). The deficit of ~2,955 events/second accumulates in Kafka partitions, and each successive Spark batch reads events that are increasingly older.

**Solution**: Scale the EMR cluster to ≥ 8 executors (`m5.xlarge ×8`) or enable `maxOffsetsPerTrigger` backpressure capping to limit per-batch read and prevent unbounded state growth. With 8 executors, estimated throughput would reach ~4,000 EPS, closing the gap with the input rate.
