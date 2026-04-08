# glue_batch_job.py
# AWS Glue PySpark Batch Job
# Runs daily at midnight via Step Functions
# Reads trip CSV from S3 → computes analytics → writes Parquet
#
# HOW TO DEPLOY:
#   Upload this file to S3
#   Create Glue job pointing to this script
#   Step Functions triggers it at midnight
#
# Innovation 3: Conditional execution
#   Only runs if input data > 1MB
#   Saves Glue compute cost on empty days

import sys
import os
import boto3
from datetime import datetime, timedelta
from decimal import Decimal
from pyspark.context import SparkContext
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, sum, avg, count, max, min,
    round as spark_round, when, lit,
    date_format, hour
)
from awsglue.context import GlueContext
from awsglue.utils import getResolvedOptions
from awsglue.job import Job

# ── GET JOB PARAMETERS ──
# These are passed by Step Functions when it triggers the job
args = getResolvedOptions(sys.argv, [
    'JOB_NAME',
    'input_path',    # S3 path to raw CSV files
    'output_path',   # S3 path for Parquet output
    'process_date',  # which date to process (YYYY-MM-DD)
    'min_file_size', # Innovation 3: minimum file size in bytes
])

# ── INITIALIZE GLUE CONTEXT ──
sc      = SparkContext()
glue    = GlueContext(sc)
spark   = glue.spark_session
job     = Job(glue)
job.init(args['JOB_NAME'], args)

# Configuration
INPUT_PATH    = args['input_path']
OUTPUT_PATH   = args['output_path']
PROCESS_DATE  = args['process_date']
MIN_FILE_SIZE = int(args.get('min_file_size', 1048576))  # 1MB default
AWS_REGION    = 'ap-south-1'
BUCKET        = 'ridesharing-pipeline-h20250060'

print(f"=" * 60)
print(f"GLUE BATCH JOB STARTING")
print(f"Date:        {PROCESS_DATE}")
print(f"Input:       {INPUT_PATH}")
print(f"Output:      {OUTPUT_PATH}")
print(f"Min size:    {MIN_FILE_SIZE} bytes")
print(f"=" * 60)

# ── INNOVATION 3: CHECK FILE SIZE BEFORE PROCESSING ──
# Only run expensive Spark job if data is worth processing
# Empty days (< 1MB) are skipped — saves compute cost
def check_input_size():
    s3     = boto3.client('s3', region_name=AWS_REGION)
    # Files stored as city=X/date=Y/ — scan all cities
    prefix = f"raw/trips/"
    total  = 0
    try:
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
            for obj in page.get('Contents', []):
                # Only count files matching our process date
                if f"date={PROCESS_DATE}" in obj['Key']:
                    total += obj['Size']
    except Exception as e:
        print(f"Error checking size: {e}")
        return 0
    print(f"Input data size for {PROCESS_DATE}: {total} bytes ({total/1024:.1f} KB)")
    return total

input_size = check_input_size()
if input_size < MIN_FILE_SIZE:
    print(f"SKIPPING: Input size {input_size} < {MIN_FILE_SIZE} minimum")
    print(f"Innovation 3: Conditional execution — no data to process")
    job.commit()
    sys.exit(0)

print(f"Input size OK: {input_size} bytes — proceeding with job")

# ── READ CSV DATA FROM S3 ──
# Reads ALL cities for the given date
# Hive partitioning: city=X/date=Y automatically filtered
# Our S3 structure is city=X/date=Y/
# Read all cities by using wildcard path
input_data_path = f"{INPUT_PATH}/city=*/date={PROCESS_DATE}/"

print(f"Reading from: {input_data_path}")

trips_df = (spark.read
    .option("header", "true")
    .option("inferSchema", "true")
    .csv(input_data_path)
)

total_records = trips_df.count()
print(f"Total records loaded: {total_records:,}")

if total_records == 0:
    print("No records found — exiting")
    job.commit()
    sys.exit(0)

# ── ANALYTICS 1: DRIVER EARNINGS PER DAY ──
# Answers: How much did each driver earn today?
# Used for: driver payouts, performance ranking
print("Computing driver earnings...")

driver_earnings = (trips_df
    .filter(col("status") == "completed")
    .groupBy("driver_id", "city_id", "date")
    .agg(
        count("trip_id").alias("total_trips"),
        spark_round(sum("final_fare_inr"), 2).alias("total_earnings_inr"),
        spark_round(avg("final_fare_inr"), 2).alias("avg_fare_inr"),
        spark_round(avg("surge_multiplier"), 2).alias("avg_surge"),
        spark_round(sum("distance_km"), 2).alias("total_distance_km"),
        spark_round(avg("driver_rating"), 2).alias("avg_rating"),
    )
    .orderBy(col("total_earnings_inr").desc())
)

print(f"Driver earnings computed: {driver_earnings.count():,} drivers")

# ── ANALYTICS 2: ZONE DEMAND HEATMAP ──
# Answers: Which zones are busiest at which hours?
# Used for: driver positioning, surge prediction
print("Computing zone demand heatmap...")

zone_heatmap = (trips_df
    .withColumn("pickup_hour", hour(col("start_time")))
    .groupBy("pickup_zone", "city_id", "pickup_hour", "date")
    .agg(
        count("trip_id").alias("trip_count"),
        spark_round(avg("surge_multiplier"), 2).alias("avg_surge"),
        spark_round(avg("final_fare_inr"), 2).alias("avg_fare_inr"),
        spark_round(sum("final_fare_inr"), 2).alias("total_revenue_inr"),
        count(when(col("status") == "cancelled", 1))
                .alias("cancellation_count"),
    )
    .orderBy("city_id", "pickup_hour", col("trip_count").desc())
)

print(f"Zone heatmap computed: {zone_heatmap.count():,} zone-hour combinations")

# ── ANALYTICS 3: CITY LEVEL STATISTICS ──
# Answers: How did each city perform today?
# Used for: city manager reports, business intelligence
print("Computing city statistics...")

city_stats = (trips_df
    .groupBy("city_id", "date")
    .agg(
        count("trip_id").alias("total_trips"),
        count(when(col("status") == "completed", 1))
                .alias("completed_trips"),
        count(when(col("status") == "cancelled", 1))
                .alias("cancelled_trips"),
        spark_round(sum("final_fare_inr"), 2).alias("total_revenue_inr"),
        spark_round(avg("final_fare_inr"), 2).alias("avg_fare_inr"),
        spark_round(avg("surge_multiplier"), 2).alias("avg_surge"),
        spark_round(avg("distance_km"), 2).alias("avg_distance_km"),
        spark_round(avg("driver_rating"), 2).alias("avg_driver_rating"),
    )
    .withColumn(
        "completion_rate_pct",
        spark_round(
            col("completed_trips") / col("total_trips") * 100, 2
        )
    )
    .orderBy(col("total_revenue_inr").desc())
)

print(f"City stats computed: {city_stats.count()} cities")

# ── ANALYTICS 4: SURGE EFFECTIVENESS ──
# Answers: Did surge pricing reduce demand as intended?
# Used for: pricing team, research analysis
print("Computing surge effectiveness...")

surge_analysis = (trips_df
    .groupBy("city_id", "date",
             spark_round(col("surge_multiplier"), 1)
             .alias("surge_bucket"))
    .agg(
        count("trip_id").alias("trip_count"),
        spark_round(avg("final_fare_inr"), 2).alias("avg_fare"),
        spark_round(
            count(when(col("status") == "cancelled", 1)) /
            count("trip_id") * 100, 2
        ).alias("cancellation_rate_pct")
    )
    .orderBy("city_id", "surge_bucket")
)

# ── WRITE RESULTS TO S3 AS PARQUET ──
# Parquet is columnar format — 70% smaller than CSV
# Much faster for analytics queries
# Partitioned by city for efficient reads
print("Writing results to S3 Parquet...")

(driver_earnings.write
    .mode("overwrite")
    .partitionBy("city_id", "date")
    .parquet(f"{OUTPUT_PATH}/driver_earnings/")
)
print("  driver_earnings written")

(zone_heatmap.write
    .mode("overwrite")
    .partitionBy("city_id", "date")
    .parquet(f"{OUTPUT_PATH}/zone_heatmap/")
)
print("  zone_heatmap written")

(city_stats.write
    .mode("overwrite")
    .partitionBy("date")
    .parquet(f"{OUTPUT_PATH}/city_stats/")
)
print("  city_stats written")

(surge_analysis.write
    .mode("overwrite")
    .partitionBy("city_id", "date")
    .parquet(f"{OUTPUT_PATH}/surge_analysis/")
)
print("  surge_analysis written")

# ── UPDATE DYNAMODB ZONE_DEMAND TABLE ──
# Stream processor can read this for surge prediction
print("Updating DynamoDB zone_demand table...")

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
zone_table = dynamodb.Table('zone_demand')

zone_rows = zone_heatmap.collect()
with zone_table.batch_writer() as batch:
    for row in zone_rows:
        batch.put_item(Item={
            'zone_id':       row.pickup_zone,
            'hour_bucket':   f"{PROCESS_DATE}T{str(row.pickup_hour).zfill(2)}",
            'city_id':       row.city_id,
            'trip_count':    row.trip_count,
            'avg_surge':     Decimal(str(row.avg_surge or 0)),
            'avg_fare_inr':  Decimal(str(row.avg_fare_inr or 0)),
            'processed_at':  datetime.utcnow().isoformat() + 'Z',
        })

print(f"DynamoDB updated: {len(zone_rows)} zone-hour records")

# ── SEND COMPLETION NOTIFICATION ──
print("Sending completion notification...")
try:
    sns = boto3.client('sns', region_name='us-east-1')
    sns.publish(
        TopicArn='arn:aws:sns:us-east-1:276209672013:billing-alerts',
        Subject=f'Glue Batch Job Completed - {PROCESS_DATE}',
        Message=f"""
Glue Batch Job Completed Successfully

Date:           {PROCESS_DATE}
Total records:  {total_records:,}
Input size:     {input_size/1024:.1f} KB

Results written to:
  {OUTPUT_PATH}/driver_earnings/
  {OUTPUT_PATH}/zone_heatmap/
  {OUTPUT_PATH}/city_stats/
  {OUTPUT_PATH}/surge_analysis/

DynamoDB zone_demand updated: {len(zone_rows)} records
        """
    )
    print("SNS notification sent")
except Exception as e:
    print(f"SNS error (non-critical): {e}")

print("=" * 60)
print("GLUE BATCH JOB COMPLETED SUCCESSFULLY")
print(f"Records processed: {total_records:,}")
print(f"Output: {OUTPUT_PATH}")
print("=" * 60)

job.commit()
