# spark_streaming_job.py
# Apache Spark Structured Streaming — Surge Pricing Engine
# Scale 1: spark-submit --master local[4]
# Scale 2: spark-submit --master local[8]  (EC2)
# Scale 3: spark-submit --master yarn      (EMR)

import os
import sys
import json
import boto3
import logging
from decimal import Decimal
from datetime import datetime
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    from_json, col, window, count, when
)
from pyspark.sql.types import (
    StructType, StructField, StringType,
    IntegerType, DoubleType
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SPARK] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ── CONFIGURATION FROM ENVIRONMENT VARIABLES ──
# Change these to scale up — ZERO code change needed
KAFKA_BROKERS  = os.getenv('KAFKA_BROKERS',
                 'localhost:9092,localhost:9093,localhost:9094')
KAFKA_TOPICS   = os.getenv('KAFKA_TOPICS',
                 'gps-critical,gps-surge,gps-normal')
WINDOW_SECONDS = int(os.getenv('WINDOW_SECONDS', '10'))
AWS_REGION     = os.getenv('AWS_DEFAULT_REGION', 'ap-south-1')
SCALE_LEVEL    = os.getenv('SCALE_LEVEL', '5K')
CHECKPOINT_DIR = os.getenv('CHECKPOINT_DIR',
                 '/tmp/spark-checkpoints/surge')
JAR_PATH       = os.getenv('JAR_PATH',
                 '/home/amit-ydav/ridesharing-pipeline/jars')

# ── GPS EVENT SCHEMA ──
GPS_SCHEMA = StructType([
    StructField("event_id",          StringType()),
    StructField("driver_id",         StringType()),
    StructField("city_id",           StringType()),
    StructField("zone_id",           StringType()),
    StructField("timestamp",         StringType()),
    StructField("lat",               DoubleType()),
    StructField("lng",               DoubleType()),
    StructField("speed_kmh",         IntegerType()),
    StructField("status",            StringType()),
    StructField("battery_pct",       IntegerType()),
    StructField("zone_demand_ratio", DoubleType()),
])

# ── SURGE RULES ──
SURGE_RULES = [
    (4.0, 3.0),
    (3.0, 2.5),
    (2.0, 2.0),
    (1.5, 1.5),
    (0.0, 1.0),
]

def get_surge_multiplier(demand_ratio):
    if demand_ratio is None:
        return 1.0
    for threshold, multiplier in SURGE_RULES:
        if demand_ratio >= threshold:
            return multiplier
    return 1.0

def write_batch_to_dynamodb(batch_df, batch_id):
    """
    Called by Spark for every micro-batch.
    Writes surge results to DynamoDB in parallel.

    batch_df: Spark DataFrame with aggregated zone results
    batch_id: unique ID for this micro-batch (for dedup)
    """
    count = batch_df.count()
    if count == 0:
        logger.info(f"Batch {batch_id}: empty, skipping")
        return

    logger.info(f"Batch {batch_id}: processing {count} zones")

    # Convert to Python list for DynamoDB write
    rows     = batch_df.collect()
    now      = datetime.utcnow().isoformat() + 'Z'
    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    table    = dynamodb.Table('surge_pricing')
    surge_count = 0

    # DynamoDB batch_writer sends 25 items per API call
    # Much faster than individual put_item calls
    with table.batch_writer() as batch:
        for row in rows:
            on_trip   = int(row.on_trip_count   or 0)
            available = int(row.available_count or 0)
            demand_ratio = on_trip / max(available, 1)
            multiplier   = get_surge_multiplier(demand_ratio)

            batch.put_item(Item={
                'zone_id':               row.zone_id,
                'timestamp':             now,
                'city_id':               row.city_id,
                'surge_multiplier':      Decimal(str(round(multiplier,  2))),
                'waiting_riders':        on_trip,
                'available_drivers':     available,
                'demand_ratio':          Decimal(str(round(demand_ratio, 4))),
                'window_size_sec':       WINDOW_SECONDS,
                'scale_level':           SCALE_LEVEL,
                'batch_id':              batch_id,
                'computed_at':           now,
            })

            if multiplier > 1.0:
                surge_count += 1
                logger.info(
                    f"SURGE {multiplier}x | {row.zone_id} | "
                    f"waiting={on_trip} available={available} | "
                    f"demand={demand_ratio:.2f}"
                )

    logger.info(
        f"Batch {batch_id} done | "
        f"zones={count} surge_zones={surge_count} | "
        f"scale={SCALE_LEVEL} window={WINDOW_SECONDS}s"
    )

    # Publish to CloudWatch
    try:
        sys.path.insert(0, '/home/amit-ydav/ridesharing-pipeline/src')
        from cloudwatch_metrics import publish
        publish(
            events_per_sec = count / WINDOW_SECONDS,
            latency_ms     = WINDOW_SECONDS * 1000,
            surge_zones    = surge_count,
            window_sec     = WINDOW_SECONDS,
            flush_ms       = 0,
            total_events   = count,
            scale_level    = SCALE_LEVEL
        )
    except Exception as e:
        logger.error(f"CloudWatch error: {e}")

def create_spark_session():
    """
    Create SparkSession with Kafka connector JARs.
    Master is set via spark-submit --master flag.
    """
    jars = ','.join([
        f"{JAR_PATH}/spark-sql-kafka.jar",
        f"{JAR_PATH}/kafka-clients.jar",
        f"{JAR_PATH}/spark-token-provider-kafka.jar",
        f"{JAR_PATH}/commons-pool2.jar",
    ])

    spark = (SparkSession.builder
        .appName(f"RidesharingSurge-{SCALE_LEVEL}")
        .config("spark.jars", jars)
        .config("spark.sql.streaming.checkpointLocation",
                CHECKPOINT_DIR)
        .config("spark.streaming.backpressure.enabled", "true")
        .config("spark.sql.shuffle.partitions", "10")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark

def run():
    """Main Spark Structured Streaming job."""
    logger.info("=" * 60)
    logger.info("SPARK STRUCTURED STREAMING — SURGE ENGINE")
    logger.info(f"Scale:    {SCALE_LEVEL}")
    logger.info(f"Kafka:    {KAFKA_BROKERS}")
    logger.info(f"Topics:   {KAFKA_TOPICS}")
    logger.info(f"Window:   {WINDOW_SECONDS} seconds")
    logger.info(f"Checkpoint: {CHECKPOINT_DIR}")
    logger.info("=" * 60)

    spark = create_spark_session()

    logger.info(f"Spark master: {spark.sparkContext.master}")
    logger.info(f"Spark UI: http://localhost:4040")

    # ── STEP 1: READ FROM KAFKA ──
    # Spark reads all 3 topics simultaneously
    # Each Kafka partition becomes one Spark task
    raw_stream = (spark
        .readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKERS)
        .option("subscribe", KAFKA_TOPICS)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .option("maxOffsetsPerTrigger", 10000)
        .load()
    )

    # ── STEP 2: PARSE JSON ──
    parsed = (raw_stream
        .select(
            from_json(
                col("value").cast("string"),
                GPS_SCHEMA
            ).alias("d"),
            col("timestamp").alias("kafka_ts")
        )
        .select("d.*", "kafka_ts")
        .filter(col("zone_id").isNotNull())
        .filter(col("status").isNotNull())
    )

    # ── STEP 3: WINDOW AGGREGATION ──
    # Groups events by zone + time window
    # Counts on_trip (demand) vs available (supply)
    # Innovation 1: WINDOW_SECONDS is env variable
    # Change without touching code:
    #   WINDOW_SECONDS=5  → faster surge detection at peak
    #   WINDOW_SECONDS=120 → less CPU at off-peak
    surge_agg = (parsed
        .withWatermark("kafka_ts", "30 seconds")
        .groupBy(
            col("zone_id"),
            col("city_id"),
            window(col("kafka_ts"),
                   f"{WINDOW_SECONDS} seconds")
        )
        .agg(
            count(when(col("status") == "on_trip",
                       1)).alias("on_trip_count"),
            count(when(col("status") == "available",
                       1)).alias("available_count"),
            count("*").alias("total_events")
        )
    )

    # ── STEP 4: WRITE TO DYNAMODB ──
    # foreachBatch writes each micro-batch to DynamoDB
    # processingTime = how often Spark triggers
    query = (surge_agg
        .writeStream
        .foreachBatch(write_batch_to_dynamodb)
        .outputMode("update")
        .trigger(processingTime=f"{WINDOW_SECONDS} seconds")
        .start()
    )

    logger.info("Streaming query started successfully")
    logger.info("Waiting for GPS events from Kafka...")

    try:
        query.awaitTermination()
    except KeyboardInterrupt:
        logger.info("Stopping Spark job...")
        query.stop()
        spark.stop()
        logger.info("Stopped cleanly.")

if __name__ == "__main__":
    run()
