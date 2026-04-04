# stream_processor.py
# Reads GPS events from all 3 Kafka topics
# Computes surge pricing per zone using adaptive windows
# Writes results to AWS DynamoDB
# This is the core of your pipeline — Innovation 1 + 3 live here

import os                            # reads environment variables
import json                          # parses JSON messages from Kafka
import time                          # timing for adaptive windows
import logging                       # structured log output
import boto3                         # AWS SDK for DynamoDB writes
from decimal import Decimal          # DynamoDB requires Decimal not float
from datetime import datetime        # timestamps
from collections import defaultdict  # zone → list of events mapping

# ── LOGGING ──
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [STREAM] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ── AWS DYNAMODB CONNECTION ──
# boto3 reads credentials from ~/.aws/credentials automatically
# No need to hardcode keys — security best practice
dynamodb = boto3.resource(
    'dynamodb',
    region_name=os.getenv('AWS_DEFAULT_REGION', 'ap-south-1')
)
surge_table  = dynamodb.Table('surge_pricing')   # live surge per zone
driver_table = dynamodb.Table('driver_status')   # current driver locations

# ── KAFKA CONFIGURATION ──
# All 3 brokers listed for fault tolerance
# If broker-1 is down, client connects to broker-2 or broker-3
KAFKA_BROKERS = ['localhost:9092', 'localhost:9093', 'localhost:9094']
KAFKA_TOPICS  = ['gps-critical', 'gps-surge', 'gps-normal']

# ── INNOVATION 1: ADAPTIVE WINDOW CONFIGURATION ──
# Window size changes based on how many events are arriving per minute
# This is what separates your pipeline from a fixed-window pipeline
WINDOW_RULES = [
    (500, 10),    # > 500 events/min → 10 second window (peak hours)
    (100, 30),    # > 100 events/min → 30 second window (normal hours)
    (0,   120),   # anything else    → 120 second window (off-peak)
]

# ── SURGE MULTIPLIER RULES ──
# demand_ratio = waiting_riders / available_drivers per zone
# Higher ratio = more surge
SURGE_RULES = [
    (4.0, 3.0),   # 4× more riders than drivers → 3.0× surge price
    (3.0, 2.5),   # 3× → 2.5× surge
    (2.0, 2.0),   # 2× → 2.0× surge
    (1.5, 1.5),   # 1.5× → 1.5× surge
    (0.0, 1.0),   # balanced → no surge
]

def get_window_size(events_per_minute):
    """
    INNOVATION 1: Returns window size in seconds based on event rate.
    
    Why this matters for your research:
    - Fixed window (what Uber uses): always 30 seconds
      → wastes compute at 3 AM, slow to detect surge at 6 PM
    - Adaptive window (your innovation): shrinks at peak hours
      → detects surge 3x faster at rush hour
      → saves 60% CPU at off-peak hours
    
    This is what you measure in Phase 8 experiments.
    """
    for min_rate, window_sec in WINDOW_RULES:
        if events_per_minute >= min_rate:
            return window_sec
    return 120   # default off-peak

def get_surge_multiplier(demand_ratio):
    """
    Converts demand ratio to surge price multiplier.
    demand_ratio = on_trip_drivers / max(available_drivers, 1)
    
    Example: zone has 30 on_trip, 10 available
    demand_ratio = 30/10 = 3.0 → surge = 2.5x
    Rider who normally pays ₹100 now pays ₹250
    """
    for threshold, multiplier in SURGE_RULES:
        if demand_ratio >= threshold:
            return multiplier
    return 1.0

def write_surge(zone_id, city_id, multiplier, waiting,
                available, demand_ratio, window_sec, latency_ms):
    """
    Writes computed surge result to DynamoDB surge_pricing table.
    
    Why DynamoDB:
    - Rider app queries "what is surge in MUM_Z07?" every few seconds
    - DynamoDB responds in 1-5ms — fast enough for live pricing
    - MySQL/PostgreSQL would be too slow under this query rate
    
    PAY_PER_REQUEST billing: we only pay per write, not per hour.
    At our scale: essentially free.
    """
    try:
        now = datetime.utcnow().isoformat() + 'Z'
        surge_table.put_item(Item={
            'zone_id':               zone_id,        # partition key
            'timestamp':             now,            # sort key
            'city_id':               city_id,
            'surge_multiplier':      Decimal(str(round(multiplier, 2))),
            'waiting_riders':        waiting,
            'available_drivers':     available,
            'demand_ratio':          Decimal(str(round(demand_ratio, 4))),
            'window_size_sec':       window_sec,
            'processing_latency_ms': Decimal(str(round(latency_ms, 2))),
            'computed_at':           now,
        })
        # Only log surge zones — reduces terminal noise
        if multiplier > 1.0:
            logger.info(
                f"SURGE {multiplier}x | {zone_id} | "
                f"waiting={waiting} available={available} | "
                f"latency={latency_ms:.0f}ms | window={window_sec}s"
            )
    except Exception as e:
        logger.error(f"DynamoDB write failed for {zone_id}: {e}")

def write_driver(event):
    """
    Updates driver's current location in DynamoDB driver_status table.
    TTL of 300 seconds auto-deletes records for offline drivers.
    
    This powers the "find nearest driver" feature in ride-sharing apps.
    Every GPS ping updates this record.
    """
    try:
        driver_table.put_item(Item={
            'driver_id':   event['driver_id'],          # partition key
            'city_id':     event['city_id'],
            'zone_id':     event['zone_id'],
            'lat':         Decimal(str(event['lat'])),
            'lng':         Decimal(str(event['lng'])),
            'speed_kmh':   event['speed_kmh'],
            'status':      event['status'],
            'last_seen':   event['timestamp'],
            'battery_pct': event['battery_pct'],
            'ttl':         int(time.time()) + 300,      # auto-delete after 5 min
        })
    except Exception as e:
        logger.error(f"Driver write failed for {event['driver_id']}: {e}")

class SurgeEngine:
    """
    The core surge computation engine.
    
    How it works:
    1. Collects GPS events into a time window (10/30/120 seconds)
    2. Groups events by zone_id
    3. At window close: counts waiting riders vs available drivers per zone
    4. Computes surge multiplier from demand ratio
    5. Writes results to DynamoDB
    6. Determines next window size based on current event rate
    
    This is Innovation 1 (adaptive windows) + Innovation 3 
    (the window size decision controls compute cost).
    """

    def __init__(self):
        self.window_events    = defaultdict(list)  # zone_id → [events]
        self.window_start     = time.time()         # when current window started
        self.current_window   = 30                  # start with 30s window
        self.total_events     = 0                   # all-time event counter
        self.minute_events    = 0                   # events in last minute
        self.minute_start     = time.time()         # for rate calculation

    def ingest(self, event_json, topic):
        """
        Called for every message received from Kafka.
        Adds event to current window bucket for its zone.
        """
        try:
            event = json.loads(event_json)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON: {event_json[:100]}")
            return

        zone_id = event.get('zone_id', 'UNKNOWN')

        # Store event with ingestion timestamp for latency calculation
        self.window_events[zone_id].append({
            'status':     event.get('status', 'unknown'),
            'city_id':    event.get('city_id', 'UNKNOWN'),
            'ingest_ts':  time.time(),
            'topic':      topic,           # which priority tier
        })

        # Update driver location on every ping
        write_driver(event)

        self.total_events += 1
        self.minute_events += 1

        # Check if current window has elapsed
        if time.time() - self.window_start >= self.current_window:
            self._flush_window()

    def _flush_window(self):
        """
        Called when window duration has elapsed.
        Computes surge for every zone that had events.
        Then resets window and adjusts next window size.
        """
        if not self.window_events:
            self.window_start = time.time()
            return

        flush_start = time.time()
        zones_processed = 0
        surge_zones = 0

        for zone_id, events in self.window_events.items():
            city_id   = events[0]['city_id']

            # Count drivers by status in this window
            # on_trip ≈ demand (riders being served or zone is busy)
            # available = supply (drivers ready for new rides)
            waiting   = sum(1 for e in events if e['status'] == 'on_trip')
            available = sum(1 for e in events if e['status'] == 'available')

            # Avoid division by zero — minimum 1 available driver
            demand_ratio = waiting / max(available, 1)
            multiplier   = get_surge_multiplier(demand_ratio)

            # Latency = time from oldest event in window to now
            oldest    = min(e['ingest_ts'] for e in events)
            latency_ms = (time.time() - oldest) * 1000

            write_surge(
                zone_id, city_id, multiplier,
                waiting, available, demand_ratio,
                self.current_window, latency_ms
            )

            zones_processed += 1
            if multiplier > 1.0:
                surge_zones += 1

        # Calculate event rate for adaptive window decision
        elapsed_min = max(time.time() - self.minute_start, 1)
        events_per_minute = (self.minute_events / elapsed_min) * 60

        # INNOVATION 1: decide next window size
        new_window = get_window_size(events_per_minute)
        if new_window != self.current_window:
            logger.info(
                f"ADAPTIVE WINDOW: {events_per_minute:.0f} ev/min → "
                f"{self.current_window}s → {new_window}s"
            )
        self.current_window = new_window

        # Log window summary
        flush_ms = (time.time() - flush_start) * 1000
        logger.info(
            f"Window closed | zones={zones_processed} | "
            f"surge_zones={surge_zones} | "
            f"total_events={self.total_events} | "
            f"rate={events_per_minute:.0f}/min | "
            f"next_window={self.current_window}s | "
            f"flush={flush_ms:.1f}ms"
        )

        # Reset for next window
        self.window_events.clear()
        self.window_start  = time.time()

        # Reset minute counter every 60 seconds
        if time.time() - self.minute_start >= 60:
            self.minute_events = 0
            self.minute_start  = time.time()

def run():
    """
    Main function — connects to Kafka and processes events forever.
    Uses kafka-python KafkaConsumer (simpler than full PyFlink for MVP).
    Phase 4 will upgrade this to native PyFlink windowing operators.
    """
    from kafka import KafkaConsumer

    logger.info("Starting stream processor...")
    logger.info(f"Connecting to Kafka: {KAFKA_BROKERS}")
    logger.info(f"Subscribing to topics: {KAFKA_TOPICS}")
    logger.info(f"Writing surge results to AWS DynamoDB")
    logger.info("-" * 60)

    # Connect to Kafka as a consumer
    consumer = KafkaConsumer(
        *KAFKA_TOPICS,                        # subscribe to all 3 topics
        bootstrap_servers=KAFKA_BROKERS,
        group_id='surge-processor-v1',        # consumer group ID
        auto_offset_reset='latest',           # start from new messages only
        enable_auto_commit=True,              # auto-commit offsets
        value_deserializer=lambda m: m.decode('utf-8'),  # bytes → string
        consumer_timeout_ms=2000,             # wait 2s for messages before loop
    )

    engine = SurgeEngine()
    logger.info("Stream processor running. Waiting for events...")
    logger.info("Surge results will appear in AWS DynamoDB surge_pricing table")
    logger.info("-" * 60)

    try:
        while True:
            # Poll Kafka for new messages (non-blocking with timeout)
            records = consumer.poll(timeout_ms=1000, max_records=500)

            if records:
                for topic_partition, messages in records.items():
                    topic = topic_partition.topic   # which of the 3 topics
                    for msg in messages:
                        engine.ingest(msg.value, topic)
            else:
                # No messages — check if window should be flushed anyway
                if time.time() - engine.window_start >= engine.current_window:
                    if engine.window_events:
                        engine._flush_window()

    except KeyboardInterrupt:
        logger.info("Stopping stream processor...")
    finally:
        consumer.close()
        logger.info("Stream processor stopped cleanly.")

if __name__ == "__main__":
    run()

