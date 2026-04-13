#!/bin/bash
# Usage: ./scripts/scale.sh 1  (5K drivers)
#        ./scripts/scale.sh 2  (50K drivers)
#        ./scripts/scale.sh 3  (500K drivers — requires EMR/larger node)
set -euo pipefail

SCALE=${1:-}

case $SCALE in
  1)
    echo "Switching to Scale 1 (5K drivers)..."
    kubectl patch configmap pipeline-config -n ridesharing \
      --type merge \
      -p '{"data":{"NUM_DRIVERS":"5000","SCALE_LEVEL":"5K","WINDOW_SECONDS":"2"}}'
    ;;
  2)
    echo "Switching to Scale 2 (50K drivers)..."
    kubectl patch configmap pipeline-config -n ridesharing \
      --type merge \
      -p '{"data":{"NUM_DRIVERS":"50000","SCALE_LEVEL":"50K","WINDOW_SECONDS":"2"}}'
    ;;
  3)
    echo "Switching to Scale 3 (500K drivers)..."
    kubectl patch configmap pipeline-config -n ridesharing \
      --type merge \
      -p '{"data":{"NUM_DRIVERS":"500000","SCALE_LEVEL":"500K","WINDOW_SECONDS":"2"}}'
    ;;
  *)
    echo "Usage: $0 [1|2|3]"
    echo "  1 →  5K drivers  (Scale 1, local Spark, t3.xlarge)"
    echo "  2 → 50K drivers  (Scale 2, local Spark, t3.xlarge)"
    echo "  3 → 500K drivers (Scale 3, requires EMR)"
    exit 1
    ;;
esac

kubectl rollout restart deployment -n ridesharing
echo "Waiting for pods to roll out..."
kubectl rollout status deployment/spark-streaming -n ridesharing
kubectl rollout status deployment/gps-simulator -n ridesharing
echo ""
kubectl get pods -n ridesharing
