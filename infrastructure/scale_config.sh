#!/bin/bash
# Usage:
#   source infrastructure/scale_config.sh local
#   source infrastructure/scale_config.sh ec2
#   source infrastructure/scale_config.sh emr

SCALE=$1

if [ "$SCALE" = "local" ]; then
    echo "Configuring Scale 1 - Local Laptop (5K drivers)"
    export SPARK_MASTER="local[4]"
    export SPARK_EXECUTOR_MEMORY="2g"
    export KAFKA_BROKERS="localhost:9092,localhost:9093,localhost:9094"
    export WINDOW_SECONDS="10"
    export SCALE_LEVEL="5K"
    export NUM_DRIVERS="5000"
    export CHECKPOINT_DIR="/tmp/spark-checkpoints/surge"

elif [ "$SCALE" = "ec2" ]; then
    echo "Configuring Scale 2 - EC2 t3.large (50K drivers)"
    export SPARK_MASTER="local[8]"
    export SPARK_EXECUTOR_MEMORY="4g"
    export KAFKA_BROKERS="${EC2_IP}:9092,${EC2_IP}:9093,${EC2_IP}:9094"
    export WINDOW_SECONDS="5"
    export SCALE_LEVEL="50K"
    export NUM_DRIVERS="50000"
    export CHECKPOINT_DIR="s3://ridesharing-pipeline-h20250060/checkpoints/ec2/"

elif [ "$SCALE" = "emr" ]; then
    echo "Configuring Scale 3 - AWS EMR (500K drivers)"
    export SPARK_MASTER="yarn"
    export SPARK_EXECUTOR_MEMORY="8g"
    export SPARK_NUM_EXECUTORS="12"
    export KAFKA_BROKERS="${KAFKA_EC2_IP}:9092,${KAFKA_EC2_IP}:9093,${KAFKA_EC2_IP}:9094"
    export WINDOW_SECONDS="5"
    export SCALE_LEVEL="500K"
    export NUM_DRIVERS="500000"
    export CHECKPOINT_DIR="s3://ridesharing-pipeline-h20250060/checkpoints/emr/"

else
    echo "Usage: source scale_config.sh [local|ec2|emr]"
fi

echo "Scale: $SCALE_LEVEL | Drivers: $NUM_DRIVERS | Window: ${WINDOW_SECONDS}s"
