# gps_simulator.py
# Generates fake GPS events and sends them to Kafka
# Run this FIRST before stream_processor.py

import json
import time
import random
from datetime import datetime
from faker import Faker
from confluent_kafka import Producer

fake = Faker('en_IN')   # Indian locale for realistic names

# ── CITY ZONES (20 zones represent different city areas) ──
ZONES = [f"ZONE_{str(i).zfill(2)}" for i in range(1, 21)]

# Mumbai-area GPS boundaries
LAT_MIN, LAT_MAX = 18.90, 19.25
LNG_MIN, LNG_MAX = 72.77, 73.00

# ── DEMAND SIMULATION (which zones are busy right now) ──
def get_zone_demand(zone_id):
    # Simulate peak demand in ZONE_07 and ZONE_12
    # during morning (8-10) and evening (17-20) hours
    hour = datetime.now().hour
    is_peak = 8 <= hour <= 10 or 17 <= hour <= 20
    busy_zones = ["ZONE_07", "ZONE_12", "ZONE_05"]
    if zone_id in busy_zones and is_peak:
        return random.uniform(1.8, 3.0)   # high demand
    elif zone_id in busy_zones:
        return random.uniform(1.2, 1.8)   # medium demand
    else:
        return random.uniform(0.5, 1.2)   # low demand

# ── PRIORITY ROUTER (decides which Kafka topic) ──
def get_topic(event, demand):
    if event['speed_kmh'] > 100:
        return 'gps-critical'    # safety emergency
    elif demand > 1.5:
        return 'gps-surge'       # surge pricing zone
    else:
        return 'gps-normal'      # routine update

# ── CONNECT TO KAFKA ──
def create_producer():
    for attempt in range(10):
        try:
            producer = Producer({
                'bootstrap.servers': 'localhost:9092',
                'acks': 'all'    # wait for Kafka to confirm receipt
            })
            print("Connected to Kafka successfully")
            return producer
        except Exception as e:
            print(f"Kafka not ready, retrying in 3s... (attempt {attempt+1}/10) - {e}")
            time.sleep(3)
    raise Exception("Could not connect to Kafka after 10 attempts")

# ── MAIN SIMULATOR ──
def simulate():
    producer = create_producer()
    drivers = [f"DRV_{str(i).zfill(4)}" for i in range(1, 51)]  # 50 fake drivers
    event_count = 0

    print("Starting GPS simulation... Press Ctrl+C to stop")
    print("-" * 55)

    while True:
        for driver_id in drivers:
            zone_id  = random.choice(ZONES)
            demand   = get_zone_demand(zone_id)

            # Build one GPS event
            event = {
                "driver_id":  driver_id,
                "timestamp":  datetime.utcnow().isoformat() + "Z",
                "lat":        round(random.uniform(LAT_MIN, LAT_MAX), 6),
                "lng":        round(random.uniform(LNG_MIN, LNG_MAX), 6),
                "speed_kmh":  random.choices(
                                  [random.randint(0, 80),    # normal speed
                                   random.randint(100, 130)], # overspeed
                                  weights=[97, 3]             # 3% overspeed chance
                              )[0],
                "status":     random.choices(
                                  ["available", "on_trip", "offline"],
                                  weights=[40, 50, 10]
                              )[0],
                "zone_id":    zone_id,
                "demand":     round(demand, 2)
            }

            topic = get_topic(event, demand)
            producer.produce(topic, json.dumps(event).encode('utf-8'))
            producer.flush()  # Ensure message is sent
            event_count += 1

            # Print every 50th event so terminal is readable
            if event_count % 50 == 0:
                print(f"[{topic.upper():12}] {driver_id} | "
                      f"zone={zone_id} | speed={event['speed_kmh']}kmh | "
                      f"demand={demand:.1f}x | total_sent={event_count}")

        producer.flush()   # send all buffered messages
        time.sleep(0.5)    # 50 drivers × 2 per second = 100 events/sec

if __name__ == "__main__":
    simulate()