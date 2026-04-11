# gps_simulator.py
# Scale-configurable GPS simulator
# Usage:
#   python gps_simulator.py                    # default 500 drivers
#   python gps_simulator.py --drivers 5000     # Scale 1
#   python gps_simulator.py --drivers 50000    # Scale 2
#   python gps_simulator.py --drivers 500000   # Scale 3

import json
import time
import random
import logging
import argparse
import threading
from datetime import datetime
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
from prometheus_client import Counter, Gauge, start_http_server

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SIM] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ── PROMETHEUS METRICS ──
events_sent   = Counter('gps_events_sent_total', 'Total GPS events', ['topic','city'])
events_failed = Counter('gps_events_failed_total', 'Failed events', ['reason'])
active_drivers= Gauge('active_drivers_count', 'Active drivers')
event_rate    = Gauge('events_per_minute', 'Events per minute')

# ── 10 INDIAN CITIES ──
CITIES = {
    'MUM': {'lat': (18.90,19.25), 'lng': (72.77,73.00), 'zones': 20},
    'DEL': {'lat': (28.40,28.88), 'lng': (76.84,77.35), 'zones': 25},
    'BLR': {'lat': (12.83,13.14), 'lng': (77.46,77.78), 'zones': 18},
    'HYD': {'lat': (17.27,17.56), 'lng': (78.31,78.63), 'zones': 16},
    'CHN': {'lat': (12.90,13.18), 'lng': (80.12,80.30), 'zones': 15},
    'PUN': {'lat': (18.43,18.62), 'lng': (73.79,73.98), 'zones': 12},
    'KOL': {'lat': (22.45,22.65), 'lng': (88.30,88.45), 'zones': 14},
    'AMD': {'lat': (22.97,23.10), 'lng': (72.53,72.67), 'zones': 10},
    'JAI': {'lat': (26.83,26.96), 'lng': (75.77,75.90), 'zones': 10},
    'SRT': {'lat': (21.12,21.24), 'lng': (72.79,72.90), 'zones':  8},
}

DEMAND_PATTERN = {
    0:0.2,1:0.1,2:0.1,3:0.1,4:0.2,5:0.4,
    6:0.7,7:1.2,8:2.0,9:2.5,10:1.5,11:1.0,
    12:1.2,13:1.0,14:0.8,15:0.9,16:1.3,17:2.0,
    18:2.8,19:2.5,20:1.8,21:1.5,22:1.0,23:0.5,
}

def get_demand(zone_num):
    hour = datetime.now().hour
    base = DEMAND_PATTERN.get(hour, 1.0)
    if zone_num in [5,7,12]:
        base *= 1.5
    return round(base * random.uniform(0.7,1.3), 2)

def classify(event, demand):
    """Innovation 2: 3-tier priority routing."""
    if event['speed_kmh'] > 100 or event['battery_pct'] < 10:
        return 'gps-critical'
    if demand > 1.5:
        return 'gps-surge'
    return 'gps-normal'

def make_event(driver_id, city_id, zone_num):
    city   = CITIES[city_id]
    lat    = round(random.uniform(*city['lat']), 6)
    lng    = round(random.uniform(*city['lng']), 6)
    status = random.choices(
        ['available','on_trip','offline'],
        weights=[40,50,10]
    )[0]
    speed  = (random.randint(10,80) if status=='on_trip'
              else random.randint(0,40) if status=='available'
              else 0)
    if random.random() < 0.03:
        speed = random.randint(101,130)
    return {
        'event_id':          f"EVT_{city_id}_{int(time.time()*1000)}_{driver_id}",
        'event_type':        'gps_ping',
        'driver_id':         driver_id,
        'city_id':           city_id,
        'timestamp':         datetime.utcnow().isoformat()+'Z',
        'lat':               lat,
        'lng':               lng,
        'speed_kmh':         speed,
        'heading':           random.choice(['N','NE','E','SE','S','SW','W','NW']),
        'status':            status,
        'zone_id':           f"{city_id}_Z{str(zone_num).zfill(2)}",
        'battery_pct':       random.randint(8,100),
        'network_type':      random.choice(['4G','4G','4G','3G']),
        'app_version':       '4.2.1',
    }

def create_producer():
    import os
    brokers_env = os.getenv('KAFKA_BROKERS', 'localhost:9092,localhost:9093,localhost:9094')
    brokers = brokers_env.split(',')
    for attempt in range(10):
        try:
            p = KafkaProducer(
                bootstrap_servers=brokers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8'),
                acks='all',
                retries=5,
                linger_ms=5,
                batch_size=32768,
            )
            logger.info(f"Connected to Kafka: {brokers}")
            return p
        except NoBrokersAvailable:
            logger.warning(f"Kafka not ready, attempt {attempt+1}/10...")
            time.sleep(3)
    raise Exception("Cannot connect to Kafka")

def run_city_simulator(city_id, drivers, producer, stats):
    """
    Simulate all drivers for ONE city.
    Runs in its own thread.
    This allows all 10 cities to run in parallel.
    """
    cycle      = 0
    city_events= 0

    while True:
        cycle    += 1
        cycle_start = time.time()
        sent     = 0
        errors   = 0

        for driver in drivers:
            if random.random() < 0.1:
                driver['zone'] = random.randint(
                    1, CITIES[city_id]['zones']
                )

            demand = get_demand(driver['zone'])
            event  = make_event(driver['id'], city_id, driver['zone'])
            topic  = classify(event, demand)
            event['zone_demand_ratio'] = demand

            try:
                producer.send(topic, key=city_id, value=event)
                sent       += 1
                city_events+= 1
                events_sent.labels(topic=topic, city=city_id).inc()
            except Exception as e:
                errors += 1
                events_failed.labels(reason=type(e).__name__).inc()

        producer.flush()

        # Update shared stats
        with stats['lock']:
            stats['total_sent']   += sent
            stats['total_errors'] += errors

        # Log every 10 cycles
        if cycle % 10 == 0:
            logger.info(
                f"[{city_id}] cycle={cycle} sent={sent} "
                f"errors={errors} total={city_events}"
            )

        # Sleep remainder of 10 second cycle
        elapsed = time.time() - cycle_start
        time.sleep(max(0, 10 - elapsed))

def run(num_drivers):
    """
    Main entry point.
    Distributes drivers across cities.
    Starts one thread per city for parallel simulation.
    """
    # Start Prometheus metrics
    start_http_server(8000)
    logger.info("Metrics at http://localhost:8000")

    producer = create_producer()

    # Distribute drivers evenly across cities
    drivers_per_city = max(1, num_drivers // len(CITIES))
    city_list        = list(CITIES.keys())

    logger.info(f"{'='*55}")
    logger.info(f"SCALE: {num_drivers:,} drivers")
    logger.info(f"Cities: {len(CITIES)}")
    logger.info(f"Drivers per city: {drivers_per_city:,}")
    logger.info(f"Target event rate: {num_drivers//10:,}/sec")
    logger.info(f"{'='*55}")

    # Shared stats across all city threads
    stats = {
        'total_sent':   0,
        'total_errors': 0,
        'lock':         threading.Lock(),
    }

    active_drivers.set(num_drivers)

    # Build driver roster per city
    all_threads = []
    driver_num  = 0

    for city_id in city_list:
        city_drivers = []
        for i in range(drivers_per_city):
            driver_num += 1
            city_drivers.append({
                'id':   f"DRV_{str(driver_num).zfill(6)}",
                'zone': random.randint(1, CITIES[city_id]['zones'])
            })

        # Each city runs in its own thread
        t = threading.Thread(
            target=run_city_simulator,
            args=(city_id, city_drivers, producer, stats),
            daemon=True,
            name=f"sim-{city_id}"
        )
        all_threads.append(t)
        t.start()
        logger.info(f"Started simulator for {city_id} "
                    f"({drivers_per_city:,} drivers)")

    logger.info(f"All {len(CITIES)} city simulators running.")
    logger.info("Press Ctrl+C to stop.")
    logger.info(f"{'='*55}")

    # Main thread: print summary every 30 seconds
    last_sent = 0
    while True:
        time.sleep(30)
        with stats['lock']:
            sent_now = stats['total_sent']
            rate     = (sent_now - last_sent) / 30
            last_sent= sent_now
            event_rate.set(rate * 60)

        logger.info(
            f"SUMMARY | total_sent={sent_now:,} | "
            f"rate={rate:.0f}/sec | "
            f"errors={stats['total_errors']}"
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='GPS Simulator for ride-sharing pipeline'
    )
    parser.add_argument(
        '--drivers',
        type=int,
        default=500,
        help='Number of drivers to simulate (default: 500)'
    )
    args = parser.parse_args()
    run(args.drivers)
