#!/usr/bin/env python3
"""
rest_ingestor.py — FastAPI REST/IoT ingestion endpoint (FR1.3)

Accepts GPS events via HTTP and forwards to Kafka.
Exposes /health and /metrics (Prometheus text format).

Usage:
    pip install fastapi uvicorn kafka-python
    KAFKA_BOOTSTRAP=localhost:9092 uvicorn src.rest_ingestor:app --host 0.0.0.0 --port 8080

Endpoints:
    POST /events        — single GPS event
    POST /events/batch  — list of GPS events
    GET  /health        — liveness check
    GET  /metrics       — Prometheus text metrics
"""

import json
import os
import time
import uuid
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

# ── CONFIG ──────────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
DEFAULT_TOPIC   = os.environ.get("KAFKA_TOPIC",     "gps-normal")

# ── METRICS STATE ────────────────────────────────────────────────────────────
_counters: Dict[str, int] = {
    "events_accepted_total":  0,
    "events_rejected_total":  0,
    "batch_requests_total":   0,
}
_start_time = time.time()

# ── KAFKA PRODUCER ───────────────────────────────────────────────────────────
def _make_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",
        retries=3,
    )

try:
    _producer = _make_producer()
    _kafka_connected = True
except NoBrokersAvailable:
    _producer = None
    _kafka_connected = False

# ── APP ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Ridesharing GPS Ingestor",
    description="REST/IoT ingestion endpoint — forwards events to Kafka (FR1.3)",
    version="1.0.0",
)

# ── HELPERS ──────────────────────────────────────────────────────────────────
_REQUIRED_FIELDS = {"driver_id", "lat", "lon", "status"}

def _validate_and_enrich(event: Dict[str, Any]) -> Dict[str, Any]:
    """Validate required fields, add ingestion_id and schema_version."""
    missing = _REQUIRED_FIELDS - event.keys()
    if missing:
        raise HTTPException(status_code=422, detail=f"Missing fields: {missing}")
    event["ingestion_id"]    = str(uuid.uuid4())
    event["ingestion_ts"]    = time.time()
    event.setdefault("schema_version", 1)
    return event

def _send(event: Dict[str, Any]) -> None:
    global _producer, _kafka_connected
    if _producer is None:
        try:
            _producer = _make_producer()
            _kafka_connected = True
        except NoBrokersAvailable:
            _kafka_connected = False
            _counters["events_rejected_total"] += 1
            raise HTTPException(status_code=503, detail="Kafka unavailable")
    _producer.send(DEFAULT_TOPIC, value=event)
    _counters["events_accepted_total"] += 1

# ── ROUTES ───────────────────────────────────────────────────────────────────
@app.post("/events", status_code=202)
def ingest_event(event: Dict[str, Any]):
    """Accept a single GPS event and forward to Kafka."""
    event = _validate_and_enrich(event)
    _send(event)
    return {"status": "accepted", "ingestion_id": event["ingestion_id"]}


@app.post("/events/batch", status_code=202)
def ingest_batch(events: List[Dict[str, Any]]):
    """Accept a list of GPS events and bulk-produce to Kafka."""
    if not events:
        raise HTTPException(status_code=422, detail="Empty batch")
    if len(events) > 10_000:
        raise HTTPException(status_code=413, detail="Batch too large (max 10000)")

    _counters["batch_requests_total"] += 1
    results = []
    for ev in events:
        try:
            ev = _validate_and_enrich(ev)
            _send(ev)
            results.append({"ingestion_id": ev["ingestion_id"], "status": "accepted"})
        except HTTPException as e:
            results.append({"status": "rejected", "reason": e.detail})

    return {"accepted": _counters["events_accepted_total"], "results": results}


@app.get("/health")
def health():
    """Liveness check."""
    global _producer, _kafka_connected
    if not _kafka_connected:
        try:
            _producer = _make_producer()
            _kafka_connected = True
        except NoBrokersAvailable:
            _kafka_connected = False
    return {
        "status": "ok",
        "kafka": "connected" if _kafka_connected else "disconnected",
        "uptime_s": round(time.time() - _start_time, 1),
    }


@app.get("/metrics")
def prometheus_metrics():
    """Prometheus text format metrics."""
    lines = [
        "# HELP rest_ingestor_events_accepted_total Total events accepted",
        "# TYPE rest_ingestor_events_accepted_total counter",
        f"rest_ingestor_events_accepted_total {_counters['events_accepted_total']}",
        "# HELP rest_ingestor_events_rejected_total Total events rejected",
        "# TYPE rest_ingestor_events_rejected_total counter",
        f"rest_ingestor_events_rejected_total {_counters['events_rejected_total']}",
        "# HELP rest_ingestor_batch_requests_total Total batch requests",
        "# TYPE rest_ingestor_batch_requests_total counter",
        f"rest_ingestor_batch_requests_total {_counters['batch_requests_total']}",
        "# HELP rest_ingestor_uptime_seconds Service uptime",
        "# TYPE rest_ingestor_uptime_seconds gauge",
        f"rest_ingestor_uptime_seconds {round(time.time() - _start_time, 1)}",
    ]
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.rest_ingestor:app", host="0.0.0.0", port=8080, reload=False)
