#!/usr/bin/env python3
"""
schema_evolution.py — GPS event schema v1 → v2 migration (FR1.4)

v1 schema: {driver_id, lat, lon, speed, status, timestamp}
v2 schema: adds vehicle_type, battery_level, schema_version=2,
           renames timestamp → event_time (ISO-8601),
           adds zone_id derived from lat/lon grid.

Usage:
    from src.schema_evolution import upgrade_event, SCHEMA_V2
    v2_event = upgrade_event(v1_event)
"""

import hashlib
import math
from datetime import datetime, timezone
from typing import Any, Dict

# ── SCHEMA DEFINITIONS ────────────────────────────────────────────────────────
SCHEMA_V1 = {
    "version": 1,
    "required": {"driver_id", "lat", "lon", "status"},
    "optional": {"speed", "timestamp"},
}

SCHEMA_V2 = {
    "version": 2,
    "required": {"driver_id", "lat", "lon", "status", "event_time", "schema_version"},
    "optional": {"speed", "vehicle_type", "battery_level", "zone_id", "ingestion_id"},
}

# ── ZONE DERIVATION ───────────────────────────────────────────────────────────
# Simple 0.5-degree grid cell → zone_id (deterministic, no DB needed)
_ZONE_GRID_DEG = 0.5

def _derive_zone_id(lat: float, lon: float) -> str:
    """Map lat/lon to a 0.5° grid zone identifier."""
    grid_lat = math.floor(lat / _ZONE_GRID_DEG) * _ZONE_GRID_DEG
    grid_lon = math.floor(lon / _ZONE_GRID_DEG) * _ZONE_GRID_DEG
    raw = f"{grid_lat:.1f}_{grid_lon:.1f}"
    short = hashlib.md5(raw.encode()).hexdigest()[:6].upper()
    return f"Z_{short}"

# ── UPGRADE FUNCTIONS ─────────────────────────────────────────────────────────
def _v1_to_v2(event: Dict[str, Any]) -> Dict[str, Any]:
    """Upgrade a v1 event to v2."""
    v2 = dict(event)

    # Rename timestamp → event_time (ISO-8601)
    if "timestamp" in v2:
        ts = v2.pop("timestamp")
        if isinstance(ts, (int, float)):
            v2["event_time"] = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        else:
            v2["event_time"] = str(ts)
    else:
        v2["event_time"] = datetime.now(tz=timezone.utc).isoformat()

    # Add new fields with sensible defaults
    v2.setdefault("vehicle_type", "unknown")
    v2.setdefault("battery_level", -1)          # -1 = not reported
    v2.setdefault("zone_id", _derive_zone_id(float(v2["lat"]), float(v2["lon"])))
    v2["schema_version"] = 2
    return v2


_UPGRADERS = {
    (1, 2): _v1_to_v2,
}

# ── PUBLIC API ────────────────────────────────────────────────────────────────
def upgrade_event(event: Dict[str, Any], target_version: int = 2) -> Dict[str, Any]:
    """
    Upgrade an event from its current schema_version to target_version.
    Idempotent: already-at-target events are returned unchanged.
    """
    src_version = int(event.get("schema_version", 1))
    if src_version == target_version:
        return event

    current = dict(event)
    while current.get("schema_version", 1) < target_version:
        v = int(current.get("schema_version", 1))
        key = (v, v + 1)
        if key not in _UPGRADERS:
            raise ValueError(f"No upgrader for schema v{v} → v{v+1}")
        current = _UPGRADERS[key](current)
    return current


def validate_event(event: Dict[str, Any], version: int = 2) -> bool:
    """Return True if event satisfies the given schema version's required fields."""
    schema = SCHEMA_V1 if version == 1 else SCHEMA_V2
    return schema["required"].issubset(event.keys())


def downgrade_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Downgrade v2 → v1 (for backward-compatibility testing)."""
    v1 = {k: v for k, v in event.items()
          if k not in {"vehicle_type", "battery_level", "zone_id", "schema_version", "event_time"}}
    if "event_time" in event:
        v1["timestamp"] = event["event_time"]
    v1["schema_version"] = 1
    return v1


# ── CLI SMOKE TEST ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    v1 = {
        "driver_id": "D001",
        "lat": 28.61,
        "lon": 77.23,
        "speed": 42.5,
        "status": "on_trip",
        "timestamp": 1744800000,
        "schema_version": 1,
    }
    v2 = upgrade_event(v1)
    print("v1 →", json.dumps(v1, indent=2))
    print("v2 →", json.dumps(v2, indent=2))
    assert validate_event(v2, version=2), "v2 validation failed"
    print("schema_evolution: OK")
