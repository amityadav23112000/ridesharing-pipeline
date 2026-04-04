# gps_simulator.py
# Simulates 500 ride-sharing drivers across 10 Indian cities
# Sends GPS events to Kafka every 10 seconds per driver
# Implements Innovation 2: 3-tier priority routing

import json                    # converts Python dict to JSON string for Kafka
import time                    # for sleep between sending events
import random                  # generates realistic random values
import logging                 # prints structured log messages
from datetime import datetime  # for generating timestamps
from faker import Faker        # generates realistic Indian locale data
from kafka import KafkaProducer             # sends messages to Kafka
from kafka.errors import NoBrokersAvailable # error if Kafka is down
from prometheus_client import Counter, Gauge, start_http_server  # metrics

# ── LOGGING SETUP ──
# Shows timestamp + level + message in every log line
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ── PROMETHEUS METRICS ──
# These numbers are exposed at localhost:8000
# Grafana reads them every 15 seconds via Prometheus
events_sent = Counter(
    'gps_events_sent_total',           # metric name in Prometheus
    'Total GPS events sent to Kafka',  # description
    ['topic', 'city']                  # labels — filter by topic or city
)
events_failed = Counter(
    'gps_events_failed_total',
    'Total GPS events that failed',
    ['reason']
)
active_drivers = Gauge(
    'active_drivers_count',
    'Number of drivers being simulated'
)
current_event_rate = Gauge(
    'events_per_minute',
    'Current event generation rate'
)

# ── 10 INDIAN CITIES WITH GPS BOUNDARIES ──
# lat and lng define the bounding box for each city
# zones = number of zones the city is divided into
CITIES = {
    'MUM': {'name': 'Mumbai',    'lat': (18.90, 19.25), 'lng': (72.77, 73.00), 'zones': 20},
    'DEL': {'name': 'Delhi',     'lat': (28.40, 28.88), 'lng': (76.84, 77.35), 'zones': 25},
    'BLR': {'name': 'Bangalore', 'lat': (12.83, 13.14), 'lng': (77.46, 77.78), 'zones': 18},
    'HYD': {'name': 'Hyderabad', 'lat': (17.27, 17.56), 'lng': (78.31, 78.63), 'zones': 16},
    'CHN': {'name': 'Chennai',   'lat': (12.90, 13.18), 'lng': (80.12, 80.30), 'zones': 15},
    'PUN': {'name': 'Pune',      'lat': (18.43, 18.62), 'lng': (73.79, 73.98), 'zones': 12},
    'KOL': {'name': 'Kolkata',   'lat': (22.45, 22.65), 'lng': (88.30, 88.45), 'zones': 14},
    'AMD': {'name': 'Ahmedabad', 'lat': (22.97, 23.10), 'lng': (72.53, 72.67), 'zones': 10},
    'JAI': {'name': 'Jaipur',    'lat': (26.83, 26.96), 'lng': (75.77, 75.90), 'zones': 10},
    'SRT': {'name': 'Surat',     'lat': (21.12, 21.24), 'lng': (72.79, 72.90), 'zones': 8 },
}

# ── DEMAND PATTERN BY HOUR ──
# Simulates realistic ride demand throughout the day
# Higher value = more riders requesting rides = potential surge
DEMAND_PATTERN = {
    0: 0.2, 1: 0.1, 2: 0.1, 3: 0.1, 4: 0.2, 5: 0.4,
    6: 0.7, 7: 1.2, 8: 2.0, 9: 2.5, 10: 1.5, 11: 1.0,
    12: 1.2, 13: 1.0, 14: 0.8, 15: 0.9, 16: 1.3, 17: 2.0,
    18: 2.8, 19: 2.5, 20: 1.8, 21: 1.5, 22: 1.0, 23: 0.5,
}

def get_zone_demand(zone_num, city_id):
    """
    Calculate demand ratio for a zone at current hour.
    Returns float — higher means more riders than drivers.
    Used to decide if this event should go to gps-surge topic.
    """
    hour = datetime.now().hour              # current hour 0-23
    base = DEMAND_PATTERN.get(hour, 1.0)   # base demand for this hour

    # Zones 5, 7, 12 are hotspots (airport, railway station areas)
    if zone_num in [5, 7, 12]:
        base *= 1.5                         # 50% more demand in hotspots

    # Add random variation to make it realistic
    variation = random.uniform(0.7, 1.3)
    return round(base * variation, 2)

def classify_event(event, demand):
    """
    INNOVATION 2: 3-tier priority routing.
    Decides which Kafka topic this event belongs to.
    This runs at the PRODUCER level — before Kafka stores it.
    
    Why this matters: Critical safety events get their own
    dedicated topic so they are NEVER delayed by routine pings.
    """
    # TIER 1 — Critical (processed first, <1 second SLA)
    if event['speed_kmh'] > 100:       # driver overspeeding
        return 'gps-critical'
    if event['battery_pct'] < 10:      # phone about to die
        return 'gps-critical'

    # TIER 2 — Surge (processed second, <5 second SLA)
    if demand > 1.5:                   # high demand zone
        return 'gps-surge'

    # TIER 3 — Normal (processed when capacity available)
    return 'gps-normal'

def generate_event(driver_id, city_id, zone_num):
    """
    Generate one GPS ping event as a Python dictionary.
    This becomes a JSON message sent to Kafka.
    """
    city = CITIES[city_id]

    # Random coordinates within city boundaries
    lat = round(random.uniform(city['lat'][0], city['lat'][1]), 6)
    lng = round(random.uniform(city['lng'][0], city['lng'][1]), 6)

    # Driver status with realistic distribution
    status = random.choices(
        ['available', 'on_trip', 'offline'],
        weights=[40, 50, 10]   # 40% waiting, 50% carrying passenger, 10% offline
    )[0]

    # Speed based on status
    if status == 'on_trip':
        speed = random.randint(10, 80)    # driving with passenger
    elif status == 'available':
        speed = random.randint(0, 40)     # slowly looking for rides
    else:
        speed = 0                          # offline = parked

    # 3% chance of overspeed to trigger critical alerts during demo
    if random.random() < 0.03:
        speed = random.randint(101, 130)

    return {
        'event_id':           f"EVT_{city_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{driver_id}",
        'event_type':         'gps_ping',
        'driver_id':          driver_id,
        'city_id':            city_id,
        'timestamp':          datetime.utcnow().isoformat() + 'Z',
        'lat':                lat,
        'lng':                lng,
        'speed_kmh':          speed,
        'heading':            random.choice(['N','NE','E','SE','S','SW','W','NW']),
        'status':             status,
        'zone_id':            f"{city_id}_Z{str(zone_num).zfill(2)}",
        'battery_pct':        random.randint(8, 100),
        'network_type':       random.choice(['4G','4G','4G','3G']),
        'app_version':        '4.2.1'
    }

def create_producer():
    """
    Connect to Kafka cluster.
    Lists all 3 brokers so if one is down, others work.
    Retries 10 times with 3 second gaps.
    """
    brokers = ['localhost:9092', 'localhost:9093', 'localhost:9094']

    for attempt in range(1, 11):
        try:
            producer = KafkaProducer(
                bootstrap_servers=brokers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8'),
                acks='all',          # wait for all 3 replicas to confirm
                retries=5,           # retry failed sends
                linger_ms=5,         # small delay to batch messages
                batch_size=16384,    # max batch size in bytes
            )
            logger.info(f"Connected to Kafka: {brokers}")
            return producer
        except NoBrokersAvailable:
            logger.warning(f"Kafka not ready, attempt {attempt}/10, retrying in 3s...")
            time.sleep(3)

    raise ConnectionError("Could not connect to Kafka after 10 attempts")

def run():
    """
    Main loop — runs forever until Ctrl+C.
    Sends one GPS event per driver every 10 seconds.
    """
    # Start Prometheus metrics server
    start_http_server(8000)
    logger.info("Metrics available at http://localhost:8000")

    producer = create_producer()

    # Build driver list — distribute evenly across cities
    drivers = []
    drivers_per_city = 500 // len(CITIES)   # 50 drivers per city
    for city_id in CITIES:
        num_zones = CITIES[city_id]['zones']
        for i in range(drivers_per_city):
            drivers.append({
                'driver_id': f"DRV_{str(len(drivers)+1).zfill(4)}",
                'city_id':   city_id,
                'zone_num':  random.randint(1, num_zones)
            })

    active_drivers.set(len(drivers))
    logger.info(f"Simulating {len(drivers)} drivers across {len(CITIES)} cities")
    logger.info("Sending events every 10 seconds. Press Ctrl+C to stop.")
    logger.info("-" * 60)

    cycle = 0
    events_this_minute = 0
    minute_start = time.time()

    while True:
        cycle += 1
        cycle_start = time.time()
        sent = 0
        errors = 0

        for driver in drivers:
            # 10% chance driver moves to new zone each cycle
            if random.random() < 0.1:
                num_zones = CITIES[driver['city_id']]['zones']
                driver['zone_num'] = random.randint(1, num_zones)

            demand = get_zone_demand(driver['zone_num'], driver['city_id'])
            event  = generate_event(driver['driver_id'], driver['city_id'], driver['zone_num'])
            topic  = classify_event(event, demand)

            # Add demand ratio to event so Flink can use it
            event['zone_demand_ratio'] = demand

            try:
                producer.send(topic, key=driver['city_id'], value=event)
                sent += 1
                events_this_minute += 1
                events_sent.labels(topic=topic, city=driver['city_id']).inc()
            except Exception as e:
                errors += 1
                events_failed.labels(reason=type(e).__name__).inc()

        producer.flush()   # push all buffered messages to Kafka now

        # Update rate metric every minute
        if time.time() - minute_start >= 60:
            rate = events_this_minute
            current_event_rate.set(rate)
            events_this_minute = 0
            minute_start = time.time()

        # Print summary every 5 cycles
        if cycle % 5 == 0:
            logger.info(f"Cycle {cycle:4d} | Sent: {sent} | Errors: {errors}")

        # Sleep for remainder of 10 second cycle
        elapsed = time.time() - cycle_start
        time.sleep(max(0, 10 - elapsed))

if __name__ == "__main__":
    run()
