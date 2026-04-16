#!/bin/bash
# download_real_dataset.sh — Download NYC Taxi real dataset (EVAL requirement)
set -euo pipefail

echo "Downloading NYC Taxi trip data (real dataset for batch processing)"
mkdir -p data/real/

PARQUET_URL="https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2024-01.parquet"
PARQUET_FILE="data/real/nyc_taxi_jan2024.parquet"

if [ -f "$PARQUET_FILE" ]; then
  echo "Parquet already downloaded: $PARQUET_FILE"
else
  echo "Downloading from NYC TLC (public domain)..."
  curl -L --progress-bar "$PARQUET_URL" -o "$PARQUET_FILE"
  echo "Downloaded: $(du -h $PARQUET_FILE | cut -f1)"
fi

echo "Converting to ridesharing schema CSV (100K sample)..."
python3 - <<'PYEOF'
import pandas as pd, os

src = "data/real/nyc_taxi_jan2024.parquet"
dst = "data/real/nyc_taxi_sample_100k.csv"

df = pd.read_parquet(src)
sample = df.sample(n=min(100_000, len(df)), random_state=42)[[
    "tpep_pickup_datetime", "PULocationID", "DOLocationID",
    "trip_distance", "fare_amount", "passenger_count"
]].rename(columns={
    "tpep_pickup_datetime": "event_time",
    "PULocationID":         "zone_id",
    "DOLocationID":         "dest_zone_id",
    "trip_distance":        "distance_km",
    "fare_amount":          "fare_usd",
    "passenger_count":      "passenger_count",
})
sample["schema_version"] = 1
sample["data_source"]     = "nyc_taxi_real"
sample["driver_id"]       = ["D" + str(i % 5000).zfill(5) for i in range(len(sample))]
sample["status"]          = "on_trip"
sample.to_csv(dst, index=False)
print(f"Saved {len(sample)} real records to {dst}")
print(sample.head(3).to_string())
PYEOF

# Upload to S3 if env available
if [ -f ".experiment_env" ]; then
  source .experiment_env
  echo "Uploading to S3..."
  aws s3 cp data/real/nyc_taxi_sample_100k.csv \
    "s3://${S3_BUCKET}/raw/real/nyc_taxi_sample_100k.csv"
  echo "Uploaded to s3://${S3_BUCKET}/raw/real/nyc_taxi_sample_100k.csv"
else
  echo "Skipping S3 upload (.experiment_env not found)"
fi

echo "Real dataset ready: data/real/nyc_taxi_sample_100k.csv"
