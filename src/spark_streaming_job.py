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
    from_json, col, window, count, when,
    min as spark_min,
)
from pyspark.sql.types import (
    StructType, StructField, StringType,
    IntegerType, DoubleType
)
from prometheus_client import Counter, Gauge, start_http_server

# ── PROMETHEUS METRICS (exposed on port 8001) ──
prom_events_processed    = Counter('spark_events_processed_total',
                                   'Total GPS events processed by Spark')
prom_active_surge_zones  = Gauge('spark_active_surge_zones',
                                 'Number of active surge zones in last batch')
prom_batch_latency_ms    = Gauge('spark_batch_latency_ms',
                                 'Average E2E latency of last batch in ms')
prom_kafka_eps           = Gauge('spark_kafka_events_per_second',
                                 'Kafka events per second in last batch')

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

def _parse_event_ts(ts_str):
    """Parse GPS event timestamp (ISO 8601 with Z suffix) to datetime."""
    if not ts_str:
        return None
    try:
        clean = ts_str.rstrip('Z')
        if '.' in clean:
            return datetime.strptime(clean, '%Y-%m-%dT%H:%M:%S.%f')
        return datetime.strptime(clean, '%Y-%m-%dT%H:%M:%S')
    except Exception:
        return None

def _percentile(sorted_vals, pct):
    """Compute percentile from a sorted list."""
    if not sorted_vals:
        return 0.0
    idx = min(int(len(sorted_vals) * pct / 100), len(sorted_vals) - 1)
    return sorted_vals[idx]

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

    # Deduplicate rows by zone_id
    seen_zones = {}
    for row in rows:
        zone = row.zone_id
        on_trip = int(row.on_trip_count or 0)
        if zone not in seen_zones or on_trip > int(seen_zones[zone].on_trip_count or 0):
            seen_zones[zone] = row
    deduped_rows = list(seen_zones.values())

    latencies = []
    for i, row in enumerate(deduped_rows):
        on_trip   = int(row.on_trip_count   or 0)
        available = int(row.available_count or 0)
        demand_ratio = on_trip / max(available, 1)
        multiplier   = get_surge_multiplier(demand_ratio)
        unique_ts = f"{now}_{batch_id}_{i}_{row.zone_id}"

        # ── E2E LATENCY: event creation → DynamoDB write ──
        event_ts   = _parse_event_ts(getattr(row, 'min_event_ts', None))
        latency_ms = (datetime.utcnow() - event_ts).total_seconds() * 1000 \
                     if event_ts else 0.0
        latencies.append(latency_ms)

        table.put_item(Item={
            'zone_id':               row.zone_id,
            'timestamp':             unique_ts,
            'city_id':               row.city_id,
            'surge_multiplier':      Decimal(str(round(multiplier,  2))),
            'waiting_riders':        on_trip,
            'available_drivers':     available,
            'demand_ratio':          Decimal(str(round(demand_ratio, 4))),
            'window_size_sec':       WINDOW_SECONDS,
            'scale_level':           SCALE_LEVEL,
            'batch_id':              batch_id,
            'computed_at':           now,
            'e2e_latency_ms':        Decimal(str(round(latency_ms, 2))),
        })
        if multiplier > 1.0:
            surge_count += 1
            logger.info(
                f"SURGE {multiplier}x | {row.zone_id} | "
                f"waiting={on_trip} available={available} | "
                f"demand={demand_ratio:.2f} | latency={latency_ms:.0f}ms"
            )

    sorted_lat = sorted(latencies)
    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
    p95_lat = _percentile(sorted_lat, 95)
    p99_lat = _percentile(sorted_lat, 99)

    logger.info(
        f"Batch {batch_id} done | "
        f"zones={count} surge_zones={surge_count} | "
        f"scale={SCALE_LEVEL} window={WINDOW_SECONDS}s | "
        f"latency avg={avg_lat:.0f}ms p95={p95_lat:.0f}ms p99={p99_lat:.0f}ms"
    )

    # ── UPDATE PROMETHEUS METRICS ──
    kafka_events_in_batch = sum(int(r.total_events or 0) for r in deduped_rows)
    prom_events_processed.inc(kafka_events_in_batch)
    prom_active_surge_zones.set(surge_count)
    prom_batch_latency_ms.set(round(avg_lat, 2))
    prom_kafka_eps.set(round(kafka_events_in_batch / max(WINDOW_SECONDS, 1), 2))

    # Publish BETTER metrics to CloudWatch
    try:
        import boto3 as cw_boto3
        from datetime import datetime as cw_dt
        cw  = cw_boto3.client('cloudwatch', region_name=AWS_REGION)
        now_cw = cw_dt.utcnow()
        total_waiting   = sum(int(r.on_trip_count or 0) for r in deduped_rows)
        total_available = sum(int(r.available_count or 0) for r in deduped_rows)
        avg_demand      = total_waiting / max(total_available, 1)
        kafka_events    = sum(int(r.total_events or 0) for r in deduped_rows)
        dims = [{'Name': 'Scale', 'Value': SCALE_LEVEL}]
        cw.put_metric_data(
            Namespace='RidesharingPipeline',
            MetricData=[
                {'MetricName':'KafkaEventsPerBatch',  'Value':kafka_events,                        'Unit':'Count',         'Timestamp':now_cw,'Dimensions':dims},
                {'MetricName':'KafkaEventsPerSecond', 'Value':kafka_events/max(WINDOW_SECONDS,1),  'Unit':'Count/Second',  'Timestamp':now_cw,'Dimensions':dims},
                {'MetricName':'ZonesProcessedPerBatch','Value':len(deduped_rows),                  'Unit':'Count',         'Timestamp':now_cw,'Dimensions':dims},
                {'MetricName':'ActiveSurgeZones',     'Value':surge_count,                         'Unit':'Count',         'Timestamp':now_cw,'Dimensions':dims},
                {'MetricName':'AvgDemandRatio',       'Value':round(avg_demand,4),                 'Unit':'None',          'Timestamp':now_cw,'Dimensions':dims},
                {'MetricName':'TotalWaitingRiders',   'Value':total_waiting,                       'Unit':'Count',         'Timestamp':now_cw,'Dimensions':dims},
                {'MetricName':'WindowSizeSeconds',    'Value':WINDOW_SECONDS,                      'Unit':'Seconds',       'Timestamp':now_cw,'Dimensions':dims},
                {'MetricName':'AvgLatencyMs',         'Value':round(avg_lat, 2),                   'Unit':'Milliseconds',  'Timestamp':now_cw,'Dimensions':dims},
                {'MetricName':'P95LatencyMs',         'Value':round(p95_lat, 2),                   'Unit':'Milliseconds',  'Timestamp':now_cw,'Dimensions':dims},
                {'MetricName':'P99LatencyMs',         'Value':round(p99_lat, 2),                   'Unit':'Milliseconds',  'Timestamp':now_cw,'Dimensions':dims},
            ]
        )
        logger.info(
            f"CW | scale={SCALE_LEVEL} | kafka_eps={kafka_events/max(WINDOW_SECONDS,1):.1f} | "
            f"zones={len(deduped_rows)} | surge={surge_count} | demand={avg_demand:.2f} | "
            f"waiting={total_waiting} | latency avg={avg_lat:.0f}ms p95={p95_lat:.0f}ms"
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
    # Start Prometheus HTTP server on port 8001 (GPS simulator uses 8000)
    try:
        start_http_server(8001)
        logger.info("Prometheus metrics server started on port 8001")
    except Exception as e:
        logger.warning(f"Could not start Prometheus server: {e}")

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
            count("*").alias("total_events"),
            spark_min(col("timestamp")).alias("min_event_ts"),
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
