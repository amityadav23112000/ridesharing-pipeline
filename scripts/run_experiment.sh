#!/bin/bash
# ============================================================
#  RIDESHARING PIPELINE — EXPERIMENT RUNNER
#  CSG527 Cloud Computing | BITS Pilani Hyderabad | 2025-26
#  Student: H20250060
# ============================================================
set -euo pipefail

# Resolve repo root regardless of where the script is called from
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "======================================"
echo " RIDESHARING PIPELINE — EXPERIMENT RUNNER"
echo "======================================"
echo "Select experiment to run:"
echo "  1. Setup AWS Infrastructure (Terraform)"
echo "  2. Scale 1 — Docker Compose Laptop (5K drivers)"
echo "  3. Scale 1 — Kubernetes Laptop (5K drivers)"
echo "  4. Scale 1 — Kubernetes EC2 (5K drivers)"
echo "  5. Scale 2 — Kubernetes EC2 (50K drivers)"
echo "  6. Scale 3 — EMR Distributed (50K drivers)"
echo "  7. View Results & Graphs"
echo "  8. Stop All Services"
echo "======================================"
read -rp "Enter option [1-8]: " OPTION

case "$OPTION" in

# ─────────────────────────────────────────────────────────
# 1. Terraform — Setup AWS Infrastructure
# ─────────────────────────────────────────────────────────
1)
  echo ""
  echo ">>> Setting up AWS Infrastructure with Terraform..."
  cd terraform/
  terraform init
  terraform apply -auto-approve
  cd ..
  echo ""
  echo "✓ AWS infrastructure provisioned successfully."
  ;;

# ─────────────────────────────────────────────────────────
# 2. Scale 1 — Docker Compose Laptop (5K drivers)
# ─────────────────────────────────────────────────────────
2)
  echo ""
  echo ">>> Starting Scale 1 Docker Compose (5K drivers)..."
  cd config/
  docker compose up -d
  echo "Waiting 45 seconds for services to start..."
  sleep 45

  echo "Creating Kafka topics..."
  docker exec kafka-broker-1 kafka-topics --create \
    --bootstrap-server kafka-broker-1:29092 \
    --topic gps-critical --partitions 10 --replication-factor 3 2>/dev/null || echo "gps-critical already exists"
  docker exec kafka-broker-1 kafka-topics --create \
    --bootstrap-server kafka-broker-1:29092 \
    --topic gps-surge --partitions 10 --replication-factor 3 2>/dev/null || echo "gps-surge already exists"
  docker exec kafka-broker-1 kafka-topics --create \
    --bootstrap-server kafka-broker-1:29092 \
    --topic gps-normal --partitions 10 --replication-factor 3 2>/dev/null || echo "gps-normal already exists"
  cd ..

  echo ""
  echo "✓ Docker Compose stack running. Now run in Terminal 1:"
  echo "  export SCALE_LEVEL=5K WINDOW_SECONDS=5"
  echo "  spark-submit --master local[4] --driver-memory 2g \\"
  echo "    --jars jars/spark-sql-kafka.jar,jars/kafka-clients.jar,\\"
  echo "    jars/spark-token-provider-kafka.jar,jars/commons-pool2.jar \\"
  echo "    src/spark_streaming_job.py"
  echo ""
  echo "Now run in Terminal 2:"
  echo "  python src/gps_simulator.py --drivers 5000"
  ;;

# ─────────────────────────────────────────────────────────
# 3. Scale 1 — Kubernetes Laptop (5K drivers)
# ─────────────────────────────────────────────────────────
3)
  echo ""
  echo ">>> Starting Scale 1 Kubernetes on Laptop..."
  export PATH="$HOME/bin:$PATH"
  minikube start --cpus=4 --memory=6144 --driver=docker
  kubectl apply -f k8s/
  echo "Waiting for pods to become ready..."
  kubectl wait --for=condition=ready pod \
    --all -n ridesharing --timeout=300s
  kubectl get pods -n ridesharing
  echo ""
  echo "✓ Kubernetes Scale 1 (Laptop) running."
  ;;

# ─────────────────────────────────────────────────────────
# 4. Scale 1 — Kubernetes EC2 (5K drivers)
# ─────────────────────────────────────────────────────────
4)
  echo ""
  echo ">>> Scale 1 Kubernetes on EC2 — SSH instructions:"
  echo ""
  echo "  ssh -i ~/.ssh/ridesharing-key.pem ubuntu@EC2_IP"
  echo ""
  echo "Then run on the EC2 instance:"
  echo "  git clone https://github.com/amityadav23112000/ridesharing-pipeline.git"
  echo "  cd ridesharing-pipeline"
  echo "  export PATH=\$HOME/bin:\$PATH"
  echo "  minikube start --cpus=4 --memory=12288 --driver=docker"
  echo "  kubectl apply -f k8s/"
  echo "  kubectl wait --for=condition=ready pod --all -n ridesharing --timeout=300s"
  echo "  kubectl get pods -n ridesharing"
  ;;

# ─────────────────────────────────────────────────────────
# 5. Scale 2 — Kubernetes EC2 (50K drivers)
# ─────────────────────────────────────────────────────────
5)
  echo ""
  echo ">>> Scale 2 Kubernetes on EC2 (50K drivers) — instructions:"
  echo ""
  echo "  (Complete Option 4 first to get K8s running on EC2)"
  echo ""
  echo "  Then scale up drivers and Spark on the running cluster:"
  echo "  kubectl set env deployment/gps-simulator \\"
  echo "    -n ridesharing NUM_DRIVERS=50000"
  echo "  kubectl set env deployment/spark-streaming \\"
  echo "    -n ridesharing SCALE_LEVEL=50K"
  echo "  kubectl rollout restart deployment -n ridesharing"
  echo ""
  echo "  Watch rollout:"
  echo "  kubectl rollout status deployment -n ridesharing"
  echo "  kubectl get pods -n ridesharing"
  ;;

# ─────────────────────────────────────────────────────────
# 6. Scale 3 — EMR Distributed (50K drivers)
# ─────────────────────────────────────────────────────────
6)
  echo ""
  echo ">>> Starting Scale 3 — AWS EMR Distributed Spark (50K drivers)..."
  source venv/bin/activate

  python3 - << 'PYEOF'
import boto3

emr = boto3.client('emr', region_name='ap-south-1')

response = emr.run_job_flow(
    Name='ridesharing-emr-scale3',
    ReleaseLabel='emr-6.15.0',
    Applications=[{'Name': 'Spark'}, {'Name': 'Hadoop'}],
    Instances={
        'MasterInstanceType': 'm5.xlarge',
        'SlaveInstanceType': 'm5.xlarge',
        'InstanceCount': 3,
        'KeepJobFlowAliveWhenNoSteps': True,
        'Ec2KeyName': 'ridesharing-key',
    },
    JobFlowRole='EMR_EC2_DefaultRole',
    ServiceRole='EMR_DefaultRole',
    LogUri='s3://ridesharing-pipeline-h20250060/emr-logs/',
    VisibleToAllUsers=True,
)
print(f"Cluster ID: {response['JobFlowId']}")
print("Monitor at: https://ap-south-1.console.aws.amazon.com/emr/home?region=ap-south-1#/clusters")
PYEOF
  ;;

# ─────────────────────────────────────────────────────────
# 7. View Results & Graphs
# ─────────────────────────────────────────────────────────
7)
  echo ""
  echo ">>> Generating comparison table and graphs..."
  source venv/bin/activate
  python experiments/comparison_table.py
  python experiments/generate_graphs.py
  echo ""
  echo "Graphs saved to experiments/graphs/"
  ls experiments/graphs/
  ;;

# ─────────────────────────────────────────────────────────
# 8. Stop All Services
# ─────────────────────────────────────────────────────────
8)
  echo ""
  echo ">>> Stopping all services..."
  export PATH="$HOME/bin:$PATH"
  minikube stop 2>/dev/null || true
  cd config && docker compose down 2>/dev/null || true && cd ..
  aws ec2 stop-instances \
    --instance-ids i-025a96da21c7bf6a6 \
    --region ap-south-1 2>/dev/null || true
  echo ""
  echo "✓ All services stopped."
  ;;

*)
  echo "Invalid option. Please run the script again and enter 1-8."
  exit 1
  ;;

esac
