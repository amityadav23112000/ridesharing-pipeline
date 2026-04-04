# batch_uploader.py
# Generates synthetic daily trip records for all 10 cities
# Uploads as CSV to AWS S3 partitioned by city and date
# This is the INPUT for the AWS Glue batch job (Phase 4)
#
# WHY BATCH PROCESSING EXISTS:
# Stream processing handles real-time events (< 5 seconds)
# But some insights cannot be computed from individual events:
#   - Total driver earnings for the day
#   - Which zones had highest demand between 8-10 AM
#   - Correlation between weather and surge pricing
# These require ALL of the day's data together → batch job

import os                              # environment variables
import csv                             # writing CSV files
import random                          # realistic random values
import boto3                           # AWS S3 upload
import logging                         # structured logging
from datetime import datetime, timedelta  # date handling
from faker import Faker                # realistic fake data
from io import StringIO                # in-memory CSV (no temp files)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [BATCH] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ── AWS S3 CONNECTION ──
s3 = boto3.client('s3', region_name=os.getenv('AWS_DEFAULT_REGION', 'ap-south-1'))
BUCKET = os.getenv('S3_BUCKET_NAME', 'ridesharing-pipeline-h20250060')

# ── CONFIGURATION ──
CITIES = ['MUM','DEL','BLR','HYD','CHN','PUN','KOL','AMD','JAI','SRT']
RECORDS_PER_CITY = 100       # 100 trips × 10 cities = 1000 total records
RIDE_TYPES = ['auto','cab','bike']
PAYMENT_METHODS = ['UPI','Card','Cash','Wallet']

# Base fare per km in INR per ride type
FARE_PER_KM = {'auto': 18.0, 'cab': 14.0, 'bike': 10.0}

# Distance ranges per ride type in km
DISTANCE_RANGE = {'auto': (1.5, 12.0), 'cab': (3.0, 35.0), 'bike': (1.0, 8.0)}

fake = Faker('en_IN')    # Indian locale for realistic names

def generate_trip(city_id, date_str):
    """
    Generate one complete trip record.
    Simulates what a real completed ride produces.
    
    Why we need this data:
    - Driver earnings = sum of final_fare_inr per driver per day
    - Zone heatmap = group by pickup_zone + hour, count trips
    - Surge effectiveness = compare base_fare vs final_fare
    """
    # Random hour weighted toward peak hours
    hour = random.choices(
        range(24),
        weights=[1,1,1,1,1,2,4,8,10,9,6,5,6,5,5,6,8,10,9,7,5,4,3,2]
    )[0]

    start_dt = datetime.strptime(date_str, '%Y-%m-%d').replace(
        hour=hour,
        minute=random.randint(0, 59),
        second=random.randint(0, 59)
    )
    end_dt = start_dt + timedelta(minutes=random.randint(10, 45))

    ride_type  = random.choice(RIDE_TYPES)
    dist_min, dist_max = DISTANCE_RANGE[ride_type]
    distance   = round(random.uniform(dist_min, dist_max), 2)
    base_fare  = round(distance * FARE_PER_KM[ride_type], 2)

    # Surge more likely during peak hours
    if 7 <= hour <= 10 or 17 <= hour <= 20:
        surge = random.choices([1.0,1.5,2.0,2.5], weights=[30,35,25,10])[0]
    else:
        surge = random.choices([1.0,1.5,2.0], weights=[70,20,10])[0]

    final_fare = round(base_fare * surge, 2)
    status     = random.choices(
        ['completed','cancelled'],
        weights=[85, 15]
    )[0]

    return {
        'trip_id':             f"TRIP_{city_id}_{date_str.replace('-','')}_{random.randint(10000,99999)}",
        'driver_id':           f"DRV_{str(random.randint(1,500)).zfill(4)}",
        'rider_id':            f"RDR_{random.randint(1000,9999)}",
        'city_id':             city_id,
        'pickup_zone':         f"{city_id}_Z{str(random.randint(1,20)).zfill(2)}",
        'dropoff_zone':        f"{city_id}_Z{str(random.randint(1,20)).zfill(2)}",
        'ride_type':           ride_type,
        'start_time':          start_dt.isoformat() + 'Z',
        'end_time':            end_dt.isoformat() + 'Z',
        'duration_min':        int((end_dt - start_dt).seconds / 60),
        'distance_km':         distance,
        'base_fare_inr':       base_fare,
        'surge_multiplier':    surge,
        'final_fare_inr':      final_fare,
        'driver_rating':       round(random.uniform(3.5, 5.0), 1),
        'rider_rating':        round(random.uniform(3.5, 5.0), 1),
        'payment_method':      random.choice(PAYMENT_METHODS),
        'status':              status,
        'cancellation_reason': random.choice(['driver_far','wait_long',None,None,None])
                               if status == 'cancelled' else None,
        'date':                date_str,
    }

def upload_city(city_id, date_str):
    """
    Generate all trips for one city and upload directly to S3.
    
    S3 PATH STRUCTURE:
    raw/trips/city=MUM/date=2026-04-04/trips.csv
    
    Why this partitioning:
    - Glue can read just one city: raw/trips/city=MUM/
    - Glue can read just one date: raw/trips/date=2026-04-04/
    - This avoids scanning all data — saves cost and time
    - Called "partition pruning" in data engineering
    """
    records = [generate_trip(city_id, date_str) for _ in range(RECORDS_PER_CITY)]

    # Write to in-memory string — never touches disk
    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=records[0].keys())
    writer.writeheader()
    writer.writerows(records)
    csv_content = buf.getvalue()

    # S3 key uses Hive-style partitioning (city=X/date=Y)
    s3_key = f"raw/trips/city={city_id}/date={date_str}/trips.csv"

    s3.put_object(
        Bucket=BUCKET,
        Key=s3_key,
        Body=csv_content.encode('utf-8'),
        ContentType='text/csv',
    )

    size_kb = len(csv_content.encode('utf-8')) / 1024
    logger.info(f"Uploaded: s3://{BUCKET}/{s3_key} ({size_kb:.1f} KB, {len(records)} records)")
    return s3_key

def run(date_str=None):
    """
    Upload trip data for all 10 cities.
    In production this runs at midnight via Airflow/EventBridge.
    For testing we run it manually.
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')

    logger.info(f"Starting batch upload for date: {date_str}")
    logger.info(f"Target: s3://{BUCKET}/raw/trips/")
    logger.info(f"Cities: {', '.join(CITIES)}")
    logger.info("-" * 55)

    total_records = 0
    for city_id in CITIES:
        upload_city(city_id, date_str)
        total_records += RECORDS_PER_CITY

    logger.info("-" * 55)
    logger.info(f"Done! {total_records} records uploaded across {len(CITIES)} cities")
    logger.info(f"Verify: aws s3 ls s3://{BUCKET}/raw/trips/ --recursive")

if __name__ == "__main__":
    run()
