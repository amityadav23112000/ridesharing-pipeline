#!/bin/bash
# demo.sh — End-to-end pipeline demo (DEL5)
# Shows: data ingestion → real-time metrics → scaling → fault → recovery → batch analytics
set -euo pipefail

# Always run from project root (works whether called from scripts/ or root)
cd "$(dirname "$0")/.."

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[DEMO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()  { echo -e "${YELLOW}[WAIT]${NC} $*"; }
pause() { warn "$1 — press ENTER to continue..."; read -r; }

echo ""
echo "================================================================"
echo "  RIDESHARING PIPELINE — LIVE DEMO"
echo "  Intelligent, Scalable, Cost-Aware Cloud Data Pipeline"
echo "  Student: H20250060 | CSG527 Cloud Computing"
echo "================================================================"
echo ""

# ── STEP 1: Start infrastructure ─────────────────────────────────────────────
info "Step 1/7: Starting Kafka + Grafana + Prometheus stack..."
docker compose -f config/docker-compose.yml up -d 2>/dev/null || \
  (cd monitoring && docker compose up -d)

info "Waiting 35s for Kafka brokers to initialise..."
sleep 35

# Create Kafka topics (KAFKA_AUTO_CREATE_TOPICS_ENABLE=false, so must be explicit)
info "Creating Kafka topics..."
for TOPIC in gps-critical gps-surge gps-normal; do
  docker exec kafka-broker-1 kafka-topics \
    --bootstrap-server localhost:9092 \
    --create --if-not-exists \
    --topic "$TOPIC" \
    --partitions 3 \
    --replication-factor 3 2>/dev/null && ok "Topic $TOPIC ready" || warn "Topic $TOPIC may already exist"
done
ok "Infrastructure ready"
echo ""

# ── STEP 2: Open Grafana ──────────────────────────────────────────────────────
info "Step 2/7: Grafana dashboard"
echo "  URL:   http://localhost:3000"
echo "  Login: admin / admin"
echo "  Panel: 'Kafka Events per Second' — should be 0 now"
pause "Open Grafana in browser"

# ── STEP 3: 1K drivers — show baseline ───────────────────────────────────────
info "Step 3/7: Starting 1K driver simulation..."
KAFKA_BROKERS=localhost:9092 python3 src/gps_simulator.py --drivers 1000 --duration 600 &
SIM_PID=$!
ok "GPS simulator started (PID $SIM_PID)"

# Start Spark streaming
WINDOW_SECONDS=2 SCALE_LEVEL=local_1k DRIVER_COUNT=1000 \
  spark-submit --master local[4] \
    --jars jars/spark-sql-kafka.jar,jars/kafka-clients.jar,jars/commons-pool2.jar,jars/spark-token-provider-kafka.jar \
    src/spark_streaming_job.py > /tmp/spark_demo.log 2>&1 &
SPARK_PID=$!
ok "Spark streaming started (PID $SPARK_PID)"

sleep 20
echo "  Expected: ~100 EPS, latency < 3000ms"
pause "Observe Grafana — EPS rising and latency < 5s SLA line"

# ── STEP 4: Scale to 5K drivers ───────────────────────────────────────────────
info "Step 4/7: Scaling to 5K drivers (watch surge zones appear)..."
kill $SIM_PID 2>/dev/null || true
KAFKA_BROKERS=localhost:9092 python3 src/gps_simulator.py --drivers 5000 --duration 600 &
SIM_PID=$!

# Restart Spark with 5s window
kill $SPARK_PID 2>/dev/null || true
sleep 3
WINDOW_SECONDS=5 SCALE_LEVEL=ec2_5k DRIVER_COUNT=5000 \
  spark-submit --master local[8] \
    --jars jars/spark-sql-kafka.jar,jars/kafka-clients.jar,jars/commons-pool2.jar,jars/spark-token-provider-kafka.jar \
    src/spark_streaming_job.py > /tmp/spark_demo.log 2>&1 &
SPARK_PID=$!

sleep 20
echo "  Expected: ~470 EPS, surge zones > 30, adaptive window = 5s"
pause "Watch surge zones panel — multi-city surge visible"

# ── STEP 5: Fault injection ───────────────────────────────────────────────────
info "Step 5/7: Injecting fault (kill -9 Spark driver)..."
echo "  FAULT INJECTED at: $(date)"
kill -9 $SPARK_PID 2>/dev/null || true

echo "  Expected: EPS drops to 0, Grafana shows gap"
pause "Confirm EPS = 0 in Grafana — take screenshot SS-FAULT-DEMO-01"

# ── STEP 6: Recovery ─────────────────────────────────────────────────────────
info "Step 6/7: Recovering — restarting Spark from checkpoint..."
WINDOW_SECONDS=5 SCALE_LEVEL=ec2_5k DRIVER_COUNT=5000 \
  spark-submit --master local[8] \
    --jars jars/spark-sql-kafka.jar,jars/kafka-clients.jar,jars/commons-pool2.jar,jars/spark-token-provider-kafka.jar \
    src/spark_streaming_job.py > /tmp/spark_demo.log 2>&1 &
SPARK_PID=$!

echo "  Expected: EPS recovers within ~30s (from Kafka replay)"
pause "Confirm recovery in Grafana — take screenshot SS-FAULT-DEMO-02"

# ── STEP 7: Batch analytics dashboard ────────────────────────────────────────
info "Step 7/7: Athena batch analytics dashboard"
if command -v open &>/dev/null; then
  open docs/athena_dashboard.html
elif command -v xdg-open &>/dev/null; then
  xdg-open docs/athena_dashboard.html
else
  echo "  Manually open: docs/athena_dashboard.html"
fi
pause "Walk through the 6 Athena panels — take screenshot SS-A3"

# ── CLEANUP ───────────────────────────────────────────────────────────────────
info "Cleaning up..."
kill $SIM_PID $SPARK_PID 2>/dev/null || true

echo ""
echo "================================================================"
ok "DEMO COMPLETE"
echo ""
echo "  Key results shown:"
echo "  1. Sub-5s latency at 500-1K drivers (NFR2 satisfied)"
echo "  2. Adaptive window: 2s → 5s as drivers scale 1K → 5K"
echo "  3. Surge zones detected across 10 cities"
echo "  4. Fault recovery in < 30s (Kafka replay)"
echo "  5. Batch analytics: 6 Athena panels with real data"
echo "================================================================"
